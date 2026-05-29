from __future__ import annotations

from app.services.scene_budget import build_scene_budget_plan


def test_auto_budget_groups_four_beats_into_two_scenes_for_short_chapter():
    plan = build_scene_budget_plan(
        target_words=2600,
        scene_beats=["开场危机", "父亲托付", "乱葬坡逃亡", "陷阱反击"],
        pacing_type="rising",
        emotion_intensity=4,
    )

    assert plan.scene_count == 2
    assert plan.scene_target_words == (1300, 1300)
    assert [len(group.beats) for group in plan.beat_groups] == [2, 2]
    assert plan.beat_groups[0].range_label == "beat 1-2"
    assert plan.beat_groups[1].range_label == "beat 3-4"
    assignment = plan.assignment_for_scene(2)
    assert assignment.target_words == 1300
    assert assignment.beat_start == 3
    assert assignment.beat_end == 4
    assert assignment.beat_group_summary == "beat 3-4：乱葬坡逃亡；陷阱反击"


def test_climax_can_add_scene_only_when_word_budget_is_safe():
    short_plan = build_scene_budget_plan(
        target_words=2600,
        scene_beats=["冲突", "反转", "爆发"],
        pacing_type="climax",
        emotion_intensity=5,
    )
    long_plan = build_scene_budget_plan(
        target_words=4200,
        scene_beats=["入局", "对抗", "揭示", "反击"],
        pacing_type="climax",
        emotion_intensity=5,
    )

    assert short_plan.scene_count == 2
    assert long_plan.scene_count == 4
    assert min(long_plan.scene_target_words) >= 1000


def test_manual_scene_count_is_respected():
    plan = build_scene_budget_plan(
        target_words=2600,
        scene_beats=["开场", "推进", "转折", "钩子"],
        requested_scene_count=4,
    )

    assert plan.mode == "manual"
    assert plan.scene_count == 4
    assert plan.scene_target_words == (650, 650, 650, 650)


def test_forced_existing_scene_count_uses_current_rows_for_budget_display():
    plan = build_scene_budget_plan(
        target_words=2600,
        scene_beats=["开场", "推进", "转折", "钩子"],
        forced_scene_count=3,
    )

    assert plan.mode == "forced"
    assert plan.scene_count == 3
    assert sum(plan.scene_target_words) == 2600
    assert [group.range_label for group in plan.beat_groups] == [
        "beat 1-2",
        "beat 3",
        "beat 4",
    ]
