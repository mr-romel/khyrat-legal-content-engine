from engagement_strategy import choose_comment_count, comment_schedule_offsets, normalize_comment


def test_shared_count_is_3_to_7_and_varies():
    counts = {choose_comment_count(f"post-{i}") for i in range(500)}
    assert counts == set(range(3, 8))


def test_shared_schedule_is_15_minutes_apart():
    assert comment_schedule_offsets(3) == [0, 15, 30]
    assert comment_schedule_offsets(7)[-1] == 90


def test_comment_normalization_removes_final_period():
    assert normalize_comment("جملة طبيعية.") == "جملة طبيعية"
    assert normalize_comment("جملة طبيعية") == "جملة طبيعية"
