from __future__ import annotations

import json
import os
from pathlib import Path

from manim import *


class FreeArabicReelScene(Scene):
    def construct(self):
        spec_path = Path(os.environ["REEL_PILOT_SCENE_JSON"])
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        config.pixel_width = 1080
        config.pixel_height = 1920
        config.frame_width = 9
        config.frame_height = 16
        slides = spec["slides"]
        durations = spec["durations"]
        for index, (slide_path, duration) in enumerate(zip(slides, durations)):
            image = ImageMobject(slide_path)
            image.set_width(9)
            image.set_height(16)
            if index == 0:
                self.play(FadeIn(image), run_time=0.45)
            else:
                self.play(FadeIn(image), run_time=0.25)
            self.wait(max(0.5, float(duration)))
            self.play(FadeOut(image), run_time=0.25)
