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


def test_blog_cta_is_relevant_and_varies_by_post():
    facebook = blog_cta_comment("facebook", topic="قانون العمل", post_text="الفصل من العمل", post_key="post-1")
    linkedin = blog_cta_comment("linkedin", topic="العقود", post_text="مراجعة العقد", post_key="post-2")
    other = blog_cta_comment("facebook", topic="قانون العمل", post_text="الفصل من العمل", post_key="post-3")
    assert BLOGGER_URL in facebook and BLOGGER_URL in linkedin
    assert len(facebook) < 180 and len(linkedin) < 200
    assert "شارك" not in facebook and "مشاركة" not in linkedin
    assert "قانون العمل" in facebook
    assert facebook != linkedin
    assert facebook != other


def test_blog_cta_is_due_for_every_published_post():
    assert all(blog_cta_due(rank) for rank in range(1, 100))
    assert not blog_cta_due(0)
    assert not blog_cta_due("not-a-rank")


def test_variable_comment_with_blog_url_does_not_replace_fixed_cta_event():
    variable_comment = {
        "event_id": "COMMENT_BUNDLE:post-123:1",
        "action": "COMMENT",
        "comment_text": f"Read more: {BLOGGER_URL}",
    }
    assert find_cta_event([variable_comment], "COMMENT_BLOG_CTA:post-123") is None


def test_find_cta_event_requires_exact_id_and_comment_action():
    reaction = {"event_id": "COMMENT_BLOG_CTA:post-123", "action": "REACTION"}
    fixed_cta = {
        "event_id": "COMMENT_BLOG_CTA:post-123",
        "action": "COMMENT",
        "comment_text": blog_cta_comment("facebook"),
    }
    assert find_cta_event([reaction, fixed_cta], "COMMENT_BLOG_CTA:post-123") is fixed_cta


def test_remove_blogger_link_from_replies_and_contextual_comments():
    from engagement_strategy import remove_blogger_link

    assert remove_blogger_link("اقرأ التفاصيل https://askmahmoudkhyrat.blogspot.com/2026/10/post.html") == "اقرأ التفاصيل"
    assert remove_blogger_link("الرابط askmahmoudkhyrat.blogspot.com/") == "الرابط"
    assert "askmahmoudkhyrat.blogspot.com" not in remove_blogger_link("شرح إضافي: https://www.askmahmoudkhyrat.blogspot.com/")
