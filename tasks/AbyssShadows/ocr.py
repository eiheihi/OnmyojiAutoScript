"""Keep dev's color-filtered OCR local to AbyssShadows on the main runtime."""

import cv2
import numpy as np

from module.atom.ocr import RuleOcr as BaseRuleOcr


class RuleOcr(BaseRuleOcr):
    def __init__(self, *, method="Default", **kwargs):
        self.color_filter = None
        if method.startswith(("CF_RGB(", "CF_HSV(")):
            self.color_filter = method[:6]
            bounds = method[7:-1].split(',')
            self.color_bounds = [np.array([int(value[i:i + 2], 16)
                                          for i in (0, 2, 4)]) for value in bounds]
            method = "Default"
        super().__init__(method=method, **kwargs)

    def pre_process(self, image):
        if self.color_filter is None:
            return image
        if self.color_filter == "CF_HSV":
            image = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(image, *self.color_bounds)
        image = cv2.bitwise_and(image, image, mask=mask)
        if self.color_filter == "CF_HSV":
            image = cv2.cvtColor(image, cv2.COLOR_HSV2RGB)
        return image
