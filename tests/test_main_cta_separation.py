from engagement_strategy import BLOGGER_URL
from main import _keep_variable_comments_separate


def test_fixed_blogger_cta_does_not_replace_variable_comments():
    facebook = ["تعليق فيسبوك أول", "تعليق فيسبوك ثانٍ", "تعليق فيسبوك ثالث"]
    linkedin = ["تعليق لينكدإن أول", "تعليق لينكدإن ثانٍ", "تعليق لينكدإن ثالث"]
    editorial = {
        "facebook_comments": list(facebook),
        "linkedin_comments": list(linkedin),
    }

    result = _keep_variable_comments_separate(editorial)

    assert result["facebook_comments"] == facebook
    assert result["linkedin_comments"] == linkedin
    assert len(result["facebook_comments"]) == 3
    assert len(result["linkedin_comments"]) == 3
    assert all(BLOGGER_URL not in item for item in result["facebook_comments"])
    assert all(BLOGGER_URL not in item for item in result["linkedin_comments"])
