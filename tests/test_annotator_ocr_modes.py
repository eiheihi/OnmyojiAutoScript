import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from dev_tools.assets_test import detect_ocr_detail
from module.atom.ocr import RuleOcr


class FakeModel:
    def __init__(self, text="", score=0.99, detections=None):
        self.text = text
        self.score = score
        self.detections = detections or []
        self.line_calls = 0
        self.detection_calls = 0

    def ocr_single_line(self, image):
        self.line_calls += 1
        return self.text, self.score

    def detect_and_ocr(self, image):
        self.detection_calls += 1
        return deepcopy(self.detections)


def boxed(text, score, x=5):
    return SimpleNamespace(
        ocr_text=text, score=score,
        box=np.array([[x, 5], [x + 40, 5], [x + 40, 25], [x, 25]], dtype=np.float32),
    )


class AnnotatorOcrModesTest(unittest.TestCase):
    def run_rule(self, mode, model, keyword=""):
        rule = RuleOcr(name="test", mode=mode, method="Default",
                       roi=(10, 20, 200, 100), area=(1, 2, 3, 4), keyword=keyword)
        rule.model = model
        with patch("dev_tools.assets_test.load_image", return_value=np.zeros((200, 300, 3), dtype=np.uint8)):
            detail = detect_ocr_detail("unused.png", rule)
        # Runtime may update its own area. Testing must preserve the source rule.
        self.assertEqual(rule.roi, [10, 20, 200, 100])
        self.assertEqual(rule.area, [1, 2, 3, 4])
        self.assertEqual(detail["roiFront"], "10,20,200,100")
        self.assertEqual(detail["roiBack"], "1,2,3,4")
        json.dumps(detail)  # numpy scalars and durations must be JSON-safe.
        return detail

    def test_full_returns_every_detection_without_claiming_keyword_match(self):
        model = FakeModel(detections=[boxed("nickname", 0.91), boxed("4 days ago", 0.999, 60)])
        detail = self.run_rule("Full", model)
        self.assertEqual([r["text"] for r in detail["results"]], ["nickname", "4 days ago"])
        self.assertEqual(detail["results"][0]["roi"], "15,25,40,20")
        self.assertEqual(detail["results"][0]["confidence"], 0.91)
        self.assertIsNone(detail["matched"])
        self.assertNotIn("similarity", detail)
        self.assertTrue(detail["recognized"])
        self.assertEqual(model.detection_calls, 1)
        self.assertEqual(model.line_calls, 0)

    def test_full_keyword_uses_runtime_filter_and_keeps_all_results(self):
        model = FakeModel(detections=[boxed("nickname", 0.91), boxed("other", 0.999, 60)])
        detail = self.run_rule("Full", model, "nickname")
        self.assertTrue(detail["matched"])
        self.assertEqual(detail["match_roi"], "15,25,40,20")
        self.assertEqual(len(detail["results"]), 2)
        detail = self.run_rule("Full", model, "zzz")
        self.assertFalse(detail["matched"])
        self.assertIsNone(detail["match_roi"])

    def test_single_uses_line_recognition_and_reports_confidence(self):
        model = FakeModel("nickname")
        detail = self.run_rule("Single", model, "nickname")
        self.assertEqual(detail["value"], "nickname")
        self.assertEqual(detail["confidence"], 0.99)
        self.assertTrue(detail["matched"])
        self.assertEqual(model.line_calls, 1)
        self.assertEqual(model.detection_calls, 0)

    def test_single_keeps_vertical_fallback(self):
        model = FakeModel("", detections=[boxed("vertical", 0.99)])
        detail = self.run_rule("Single", model)
        self.assertEqual(detail["value"], "vertical")
        self.assertEqual(model.line_calls, 1)
        self.assertEqual(model.detection_calls, 1)

    def test_typed_modes_return_actual_processed_values(self):
        for mode, text, value in [
            ("Digit", "42", 42),
            ("DigitCounter", "14/15", [14, 1, 15]),
            ("Duration", "01:02:03", {"duration": "1:02:03", "total_seconds": 3723.0}),
        ]:
            with self.subTest(mode=mode):
                model = FakeModel(text)
                detail = self.run_rule(mode, model)
                self.assertEqual(detail["value"], value)
                self.assertIsNone(detail["matched"])
                self.assertEqual(model.line_calls, 1)
                self.assertEqual(model.detection_calls, 0)

    def test_quantity_uses_detection_and_quantity_conversion(self):
        model = FakeModel(detections=[boxed("1.2万", 0.99)])
        detail = self.run_rule("Quantity", model)
        self.assertEqual(detail["value"], 12000)
        self.assertEqual(model.line_calls, 0)
        self.assertEqual(model.detection_calls, 1)

    def test_zero_is_not_confused_with_no_recognition(self):
        zero = self.run_rule("Digit", FakeModel("0"))
        empty = self.run_rule("Digit", FakeModel("", score=0.1))
        self.assertEqual(zero["value"], 0)
        self.assertEqual(empty["value"], 0)
        self.assertTrue(zero["recognized"])
        self.assertFalse(empty["recognized"])

    def test_empty_full_does_not_match(self):
        detail = self.run_rule("Full", FakeModel(), "nickname")
        self.assertEqual(detail["results"], [])
        self.assertFalse(detail["matched"])
        self.assertFalse(detail["recognized"])


if __name__ == "__main__":
    unittest.main()
