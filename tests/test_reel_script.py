import unittest

from reel_script import FIXED_SLOGAN, validate_reel_script


class ReelScriptValidationTests(unittest.TestCase):
    def test_fixed_order_and_slogan_are_enforced(self):
        data = {
            "hook": "ممكن تخسر حقك بسبب رسالة واحدة؟",
            "problem": "ناس بتعتمد على اتفاق شفهي من غير ما تحتفظ بدليل.",
            "solution": "احتفظ بالمراسلات والمستندات، وراجع أثرها القانوني قبل اتخاذ خطوة.",
            "cta": "اكتب سؤالك العام في التعليقات.",
            "end_slogan": "أي كلام قديم",
            "full_script": "ignored",
            "estimated_seconds": 35,
        }
        result = validate_reel_script(data)
        self.assertEqual(result["end_slogan"], FIXED_SLOGAN)
        self.assertEqual(
            result["full_script"].split("\n\n"),
            [data["hook"], data["problem"], data["solution"], data["cta"], FIXED_SLOGAN],
        )

    def test_missing_section_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_reel_script({
                "hook": "هوك",
                "problem": "مشكلة",
                "solution": "حل",
                "cta": "",
                "end_slogan": FIXED_SLOGAN,
                "full_script": "نص",
            })


if __name__ == "__main__":
    unittest.main()
