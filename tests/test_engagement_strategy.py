from engagement_strategy import BLOGGER_URL, blog_cta_comment, blog_cta_due, choose_comment_count, comment_schedule_offsets, find_cta_event, normalize_comment


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
    assert "قراءة" in facebook and "اقرأ" in linkedin
    assert "مزيد من المعلومات" in linkedin
    assert facebook != linkedin


def test_blog_cta_is_due_for_every_published_post():
    assert all(blog_cta_due(rank) for rank in range(1, 100))
    assert not blog_cta_due(0)
    assert not blog_cta_due("not-a-rank")
