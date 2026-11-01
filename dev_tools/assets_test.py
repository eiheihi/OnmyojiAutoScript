import cv2
import numpy as np
from copy import copy
from datetime import timedelta

from numpy import float32, int32, uint8, fromfile
from pathlib import Path

from module.logger import logger
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.ocr.base_ocr import OcrMode


def load_image(file: str, strict_size: bool = True):
    file = Path(file)
    img = cv2.imdecode(fromfile(file, dtype=uint8), -1)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    height, width, channels = img.shape
    if strict_size and (height != 720 or width != 1280):
        logger.error(f'Image size is {height}x{width}, not 720x1280')
        return None
    return img


def detect_image(file: str, targe: RuleImage) -> bool:
    img = load_image(file)
    result = targe.test_match(img)
    logger.info(f'[{targe.name}]: {result}')
    return result


def detect_ocr(file: str, target: RuleOcr):
    img = load_image(file)
    return target.ocr(img)


def _roi_to_text(roi: list | tuple) -> str:
    x, y, w, h = roi
    return f"{int(round(x))},{int(round(y))},{int(round(w))},{int(round(h))}"


def detect_image_detail(file: str, target: RuleImage) -> dict:
    img = load_image(file, strict_size=False)
    if img is None:
        return {
            "matched": False,
            "similarity": 0.0,
            "roiFront": _roi_to_text(target.roi_front),
            "roiBack": _roi_to_text(target.roi_back),
            "message": "image_load_failed",
        }

    similarity = 0.0
    matched = False
    message = "not_match"

    if target.is_template_match:
        source = target.corp(img)
        mat = target.image
        if source.shape[0] < mat.shape[0] or source.shape[1] < mat.shape[1]:
            return {
                "matched": False,
                "similarity": 0.0,
                "roiFront": _roi_to_text(target.roi_front),
                "roiBack": _roi_to_text(target.roi_back),
                "message": "roi_back_too_small",
            }
        res = cv2.matchTemplate(source, mat, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        similarity = float(max_val)
        matched = similarity >= target.threshold
        target.roi_front[0] = int(max_loc[0] + target.roi_back[0])
        target.roi_front[1] = int(max_loc[1] + target.roi_back[1])
        target.roi_front[2] = int(mat.shape[1])
        target.roi_front[3] = int(mat.shape[0])
        message = "match" if matched else "not_match"
    else:
        # 掩码 / 多尺度 / SIFT 走本地 test_match
        try:
            matched = bool(target.test_match(img))
            # 优先取匹配过程记录的真实分数; SIFT 等未记录分数的方法退回 0/1
            similarity = float(getattr(target, "last_score", -1.0))
            if similarity < 0:
                similarity = 1.0 if matched else 0.0
            message = "match" if matched else "not_match"
            # 多尺度命中时带回最高分档的缩放倍数
            scale = getattr(target, "last_scale", None)
            if matched and scale is not None:
                message += f" scale={float(scale):.2f}"
        except Exception as e:
            message = f"match_error:{e}"

    return {
        "matched": matched,
        "similarity": round(similarity, 4),
        "roiFront": _roi_to_text(target.roi_front),
        "roiBack": _roi_to_text(target.roi_back),
        "message": message,
    }


def detect_ocr_detail(file: str, target: RuleOcr) -> dict:
    # Use a private rule so runtime updates to area cannot alter the editor rule.
    target = copy(target)
    roi_front = _roi_to_text(target.roi)
    roi_back = _roi_to_text(target.area)
    img = load_image(file, strict_size=False)
    if img is None:
        return {
            "mode": target.mode.name,
            "matched": None,
            "confidence": None,
            "recognized": False,
            "text": "",
            "results": [],
            "roiFront": roi_front,
            "roiBack": roi_back,
            "message": "image_load_failed",
        }

    # Capture diagnostics during the real mode-specific call, without running
    # recognition a second time (which can produce a different OCR result).
    lines = []
    boxed = []
    model = target.model

    class ModelProbe:
        def __getattr__(self, name):
            return getattr(model, name)

        def ocr_single_line(self, image):
            text, score = model.ocr_single_line(image)
            lines.append({"text": str(text), "confidence": round(float(score), 4)})
            return text, score

    target.model = ModelProbe()
    detect = target.detect_and_ocr

    def capture_detection(image, logDisplay=True):
        results = detect(image, logDisplay=logDisplay)
        boxed.extend(results)
        return results

    target.detect_and_ocr = capture_detection
    value = target.ocr(img)
    results = []
    for item in boxed:
        box = item.box
        x0 = int(np.min(box[:, 0])) + int(target.roi[0])
        y0 = int(np.min(box[:, 1])) + int(target.roi[1])
        x1 = int(np.max(box[:, 0])) + int(target.roi[0])
        y1 = int(np.max(box[:, 1])) + int(target.roi[1])
        results.append({
            "text": str(item.ocr_text),
            "confidence": round(float(item.score), 4),
            "roi": _roi_to_text((x0, y0, max(1, x1 - x0), max(1, y1 - y0))),
        })

    is_full = target.mode == OcrMode.FULL
    text = "\n".join(item["text"] for item in results) if is_full else str(value)
    # Numeric zero and zero-duration are legitimate values, as well as runtime
    # fallbacks. Report the actual value and recognition evidence separately.
    recognized = bool(results) or any(
        line["text"] and (
            line["confidence"] >= target.score
            or (target.mode in (OcrMode.DIGIT, OcrMode.DIGITCOUNTER, OcrMode.QUANTITY)
                and line["confidence"] >= target.min_score
                and any(char.isdigit() for char in line["text"]))
        ) for line in lines
    )
    matched = None
    if target.keyword:
        matched = recognized and (bool(any(value)) if is_full else target.match(text, included=True))
    if isinstance(value, timedelta):
        value = {"duration": str(value), "total_seconds": value.total_seconds()}
    elif isinstance(value, (tuple, list)):
        value = [item.item() if isinstance(item, np.generic) else item for item in value]
    elif isinstance(value, np.generic):
        value = value.item()

    return {
        "mode": target.mode.name,
        "matched": matched,
        "recognized": recognized,
        "confidence": lines[0]["confidence"] if lines and not boxed else None,
        "text": text,
        "value": value,
        "results": results,
        "raw_lines": lines,
        "keyword": target.keyword,
        "roiFront": roi_front,
        "roiBack": roi_back,
        "match_roi": _roi_to_text(value) if is_full and matched else None,
        "message": ("match" if matched else "not_match") if target.keyword else (
            "recognized_without_keyword" if recognized else "no_text_detected"
        ),
    }


# 图片文件路径 可以是相对路径
IMAGE_FILE = r"C:\Users\Ryland\Desktop\ScreenShot_2026-05-30_141821_235.png"
if __name__ == '__main__':
    from tasks.Exploration.script_task import ScriptTask
    targe = ScriptTask.I_TREASURE_BOX_CLICK
    print(detect_image(IMAGE_FILE, targe))

    # ocr demo
    # from tasks.KekkaiActivation.assets import KekkaiActivationAssets
    # target = KekkaiActivationAssets.O_CARD_ALL_TIME
    # print(detect_ocr(IMAGE_FILE, target))
