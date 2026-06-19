"""Specialist agent implementations.

Each specialist module exports a single ``Specialist`` class implementing the
:class:`app.services.agents.specialists.base.SpecialistAgent` protocol. The
supervisor (:mod:`app.services.agents.supervisor`) decides *which* specialist
to invoke based on the agent registry; this package provides the *how*.

Phase 1 scope: the Outlook specialist is fully implemented as the
proof-of-pattern. Other specialists ship as stubs that declare their scope in
the registry but delegate to the legacy resolution node — they will be
fleshed out in Phase 2 (see ``docs/development/rollout-plan-multi-agent.md``).
"""
