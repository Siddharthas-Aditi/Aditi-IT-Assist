"""Autonomous device-execution capability (Phase 9).

Lets an agent *act on a managed endpoint* — install an approved app, run an
approved remediation, or take a benign device action — through Microsoft Intune,
governed by the same :class:`~app.services.agents.tools.runtime.AgentToolRuntime`
as every other tool.

The safety model has three independent layers, each in its own pure module so it
is unit-testable without Graph, an LLM, or a database:

* **Action catalog** (:mod:`.catalog`) — a versioned allow-list of exactly which
  apps / remediations / device actions may ever run, each mapped to a
  pre-published Intune object and tagged with a risk tier. The agent selects a
  catalog *id*; it can never author a payload, script, or installer. This is the
  single most important guardrail against prompt injection: there is no free-form
  execution surface for an attacker's text to reach.
* **Autonomy policy** (:mod:`.policy`) — a pure decision function mapping
  (catalog entry, guardrail signals, config) → autonomous / human-approval / deny.
  High-risk actions and anything off-catalog can never auto-execute.
* **Execution tools** (:mod:`.tools`) — typed :class:`ToolSpec` write tools whose
  ``run`` enforces catalog membership + policy before it will touch Intune,
  degrading to a typed non-executing result otherwise.

See ``docs/architecture/device-execution-decision.md``.
"""

from __future__ import annotations
