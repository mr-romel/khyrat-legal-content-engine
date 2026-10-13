from engagement_strategy import BLOGGER_URL, blog_cta_comment, choose_comment_count, comment_schedule_offsets, normalize_comment


def test_shared_count_is_3_to_7_and_varies():
    counts = {choose_comment_count(f"post-{i}") for i in range(500)}
    assert counts == set(range(3, 8))


def test_shared_schedule_is_15_minutes_apart():
    assert comment_schedule_offsets(3) == [0, 15, 30]
    assert comment_schedule_offsets(7)[-1] == 90


def test_comment_normalization_removes_final_period():
    assert normalize_comment("جملة طبيعية.") == "جملة طبيعية"
    assert normalize_comment("جملة طبيعية") == "جملة طبيعية"


def test_blog_cta_is_clear_and_platform_specific():
    facebook = blog_cta_comment("facebook")
    linkedin = blog_cta_comment("linkedin")
    assert BLOGGER_URL in facebook and BLOGGER_URL in linkedin
    assert "شارك" in facebook and "شارك" in linkedin
    assert "قراءة المزيد" in facebook and "قراءة المزيد" in linkedin
    assert facebook != linkedin
