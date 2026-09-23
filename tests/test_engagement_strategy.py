from engagement_strategy import choose_comment_count, comment_schedule_offsets, normalize_comment


def test_shared_count_is_5_to_10_and_varies():
    counts = {choose_comment_count(f"post-{i}") for i in range(500)}
    assert counts == set(range(5, 11))


def test_shared_schedule_is_15_minutes_apart():
    assert comment_schedule_offsets(5) == [0, 15, 30, 45, 60]
    assert comment_schedule_offsets(10)[-1] == 135


def test_comment_normalization_removes_final_period():
    assert normalize_comment("جملة طبيعية.") == "جملة طبيعية"
    assert normalize_comment("جملة طبيعية") == "جملة طبيعية"
