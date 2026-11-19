from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))



def test_catch_up_detects_swallowed_image_qa_failure():
    import run_main

    before = {"الحالة": "READY", "Facebook Post ID": "", "LinkedIn Post ID": ""}
    after = {
        "الحالة": "FAILED",
        "آخر خطأ": "IMAGE_QA_BLOCKED: no image passed semantic QA",
        "Facebook Post ID": "",
        "LinkedIn Post ID": "",
    }
    assert run_main._catch_up_row_failure(before, after) == "IMAGE_QA_BLOCKED: no image passed semantic QA"


def test_catch_up_detects_return_without_new_social_post_id():
    import run_main

    before = {"الحالة": "READY", "Facebook Post ID": "", "LinkedIn Post ID": ""}
    after = {"الحالة": "PROCESSING", "Facebook Post ID": "", "LinkedIn Post ID": ""}
    assert "without a newly confirmed" in run_main._catch_up_row_failure(before, after)


def test_catch_up_accepts_only_new_social_post_ids():
    import run_main

    before = {"Facebook Post ID": "old-fb", "LinkedIn Post ID": ""}
    after = {"Facebook Post ID": "old-fb", "LinkedIn Post ID": "new-li"}
    assert run_main._new_social_post_ids(before, after) == {"new-li"}
    assert run_main._catch_up_row_failure(
        {"الحالة": "READY", "Facebook Post ID": "", "LinkedIn Post ID": ""},
        {"الحالة": "PUBLISHED", "Facebook Post ID": "new-fb", "LinkedIn Post ID": ""},
    ) == ""

