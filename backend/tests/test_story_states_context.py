"""ContextBuilder story_states ranking tests."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.context_builder import ContextBuilder


def _state(
    name: str,
    *,
    state_type: str,
    chapter_id: str,
    priority: int,
    entity_type: str = "plot_thread",
    hard: bool = False,
):
    return SimpleNamespace(
        id=f"state_{name}",
        entity_type=entity_type,
        name=name,
        state_type=state_type,
        priority=priority,
        is_hard_constraint=hard,
        source_chapter_id=chapter_id,
        updated_in_chapter_id=chapter_id,
        updated_at=None,
        created_at=None,
    )


def test_story_state_selection_prioritizes_recent_and_preserves_hard_constraints():
    ranked = ContextBuilder._select_story_state_items(
        [
            _state(
                "黑棺异动",
                state_type="foreshadow",
                chapter_id="ch5",
                priority=68,
            ),
            _state(
                "天道反噬上限",
                state_type="oath",
                chapter_id="ch5",
                priority=55,
                entity_type="world_rule",
                hard=True,
            ),
            _state(
                "林渊·因果感知",
                state_type="skill",
                chapter_id="ch38",
                priority=70,
                entity_type="character",
            ),
        ],
        current_chapter_index=40,
        chapter_index_by_id={"ch5": 5, "ch38": 38},
        focus_names={"林渊·因果感知"},
        limit=10,
    )

    names = [item.name for item in ranked]
    assert "天道反噬上限" in names
    assert names.index("林渊·因果感知") < names.index("黑棺异动")


def test_story_state_selection_enforces_state_type_quota():
    rows = [
        _state(f"伏笔{i}", state_type="foreshadow", chapter_id="ch22", priority=100 - i)
        for i in range(1, 6)
    ]
    rows.extend(
        [
            _state("身份1", state_type="identity", chapter_id="ch22", priority=60),
            _state("身份2", state_type="identity", chapter_id="ch22", priority=59),
        ]
    )

    ranked = ContextBuilder._select_story_state_items(
        rows,
        current_chapter_index=22,
        chapter_index_by_id={"ch22": 22},
        focus_names=set(),
        limit=7,
    )

    foreshadow_count = sum(1 for item in ranked if item.state_type == "foreshadow")
    names = [item.name for item in ranked]
    assert foreshadow_count == 3
    assert "身份1" in names
    assert "身份2" in names
