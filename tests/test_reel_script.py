import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from reel_script import FIXED_SLOGAN, validate_reel_script


class ReelScriptValidationTests(unittest.TestCase):
    def valid_script(self):
        return {
            "hook": "ممكن تخسر حقك بسبب رسالة واحدة؟",
            "answer": "احتفظ بالمراسلات كدليل، وما تمضيش على إقرار قبل ما تفهم أثره القانوني.",
            "cta": "اكتب سؤالك في التعليقات.",
            "end_slogan": "سلوجن قديم",
            "full_script": "ignored",
            "estimated_seconds": 18,
        }

    def test_exact_order_and_fixed_slogan(self):
        data = self.valid_script()
        result = validate_reel_script(data)
        self.assertEqual(result["end_slogan"], FIXED_SLOGAN)
        self.assertEqual(
            result["full_script"].split("\\n\\n"),
            [data["hook"], data["answer"], data["cta"], FIXED_SLOGAN],
        )

    def test_hook_must_be_a_question(self):
        data = self.valid_script()
        data["hook"] = "خلي بالك من حقك"
        with self.assertRaisesRegex(ValueError, "must be a question"):
            validate_reel_script(data)

    def test_long_answer_is_rejected(self):
        data = self.valid_script()
        data["answer"] = " ".join(["كلمة"] * 41)
        with self.assertRaisesRegex(ValueError, "too long"):
            validate_reel_script(data)

    def test_unspecified_post_reference_is_rejected(self):
        data = self.valid_script()
        data["cta"] = "ارجع للمنشور عشان تعرف التفاصيل."
        with self.assertRaisesRegex(ValueError, "unspecified post"):
            validate_reel_script(data)

    def test_missing_cta_is_rejected(self):
        data = self.valid_script()
        data["cta"] = ""
        with self.assertRaisesRegex(ValueError, "cta"):
            validate_reel_script(data)


if __name__ == "__main__":
    unittest.main()
