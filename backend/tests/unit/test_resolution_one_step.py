"""B1: the resolver presents one step per turn and advances on the next turn."""

import pytest

from app.services.agents.diagnostic_state import DiagnosticContext
from app.workflows.nodes import resolution as R  # noqa: N812


def _kb():
    return [
        {
            "title": "Laptop Keyboard Not Working",
            "category": "hardware/laptop",
            "subcategory": "keyboard-not-working",
            "resolution_steps": [
                {
                    "step_number": 1,
                    "instruction": "Check for physical obstructions",
                    "details": "Remove dust or debris; ensure no key is stuck.",
                },
                {
                    "step_number": 2,
                    "instruction": "Restart the laptop",
                    "details": "Restart and test the keyboard again.",
                },
                {
                    "step_number": 3,
                    "instruction": "Test with the On-Screen Keyboard",
                    "details": "Settings -> Accessibility -> Keyboard.",
                },
            ],
        }
    ]


def _ctx():
    ctx = DiagnosticContext()
    ctx.issue_category = "hardware/laptop"
    ctx.issue_subtype = "keyboard-not-working"
    ctx.symptom = "keyboard not working"
    return ctx


@pytest.mark.asyncio
async def test_presents_single_step_first_turn():
    ctx = _ctx()
    state = {"knowledge_results": _kb(), "diagnostic_context": ctx.to_dict()}
    result = await R.resolution_node(state)
    assert len(result["resolution_steps"]) == 1
    assert result["resolution_steps"][0]["instruction"] == "Check for physical obstructions"


@pytest.mark.asyncio
async def test_advances_to_next_step_after_failure():
    ctx = _ctx()
    # Simulate step 1 already suggested and failed.
    ctx.record_suggested_steps(["Check for physical obstructions"])
    ctx.mark_last_batch_failed()
    state = {"knowledge_results": _kb(), "diagnostic_context": ctx.to_dict()}
    result = await R.resolution_node(state)
    assert len(result["resolution_steps"]) == 1
    assert result["resolution_steps"][0]["instruction"] == "Restart the laptop"


def test_fallback_prose_single_step_has_no_below_pointer():
    steps = [
        {"step_number": 1, "instruction": "Restart the laptop", "details": "Settings -> Update."}
    ]
    ctx = _ctx()
    prose = R._format_concise_response(steps, _kb()[0], 0.7, ctx)
    assert "just below" not in prose.lower()
    assert "laid out" not in prose.lower()


@pytest.mark.asyncio
async def test_normal_step_turn_includes_quick_replies():
    ctx = _ctx()
    state = {"knowledge_results": _kb(), "diagnostic_context": ctx.to_dict()}
    result = await R.resolution_node(state)
    assert result["quick_replies"] == [
        {"label": "That worked", "value": "that worked"},
        {"label": "Still not working", "value": "still not working"},
        {"label": "Talk to a specialist", "value": "talk to a specialist"},
    ]


@pytest.mark.asyncio
async def test_escalation_turn_has_no_quick_replies():
    ctx = _ctx()
    ctx.record_suggested_steps(
        [
            "Check for physical obstructions",
            "Restart the laptop",
            "Test with the On-Screen Keyboard",
        ]
    )
    ctx.mark_last_batch_failed()
    kb = _kb()
    kb[0]["resolution_steps"].append(
        {
            "step_number": 4,
            "instruction": "Check the keyboard language",
            "details": "Settings -> Time & Language.",
        }
    )
    state = {"knowledge_results": kb, "diagnostic_context": ctx.to_dict()}
    result = await R.resolution_node(state)
    assert result["conversation_phase"] == "escalating"
    assert not result.get("quick_replies")


@pytest.mark.asyncio
async def test_escalates_after_threshold_misses_even_with_steps_left():
    ctx = _ctx()
    # 3 distinct steps already tried and failed (threshold default = 3),
    # but the article still has more steps available.
    ctx.record_suggested_steps(
        [
            "Check for physical obstructions",
            "Restart the laptop",
            "Test with the On-Screen Keyboard",
        ]
    )
    ctx.mark_last_batch_failed()
    kb = _kb()
    kb[0]["resolution_steps"].append(
        {
            "step_number": 4,
            "instruction": "Check the keyboard language",
            "details": "Settings -> Time & Language.",
        }
    )
    state = {"knowledge_results": kb, "diagnostic_context": ctx.to_dict()}
    result = await R.resolution_node(state)
    # Routed to escalation: no steps presented, phase escalating.
    assert result["resolution_steps"] == []
    assert result["conversation_phase"] == "escalating"
