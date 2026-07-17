"""Autonomy policy — decides whether a device action may run unattended.

A single **pure, deterministic** function, :func:`evaluate_device_action`, maps a
resolved catalog entry plus a set of guardrail signals to one of three
decisions:

* ``AUTONOMOUS``    — the agent may execute now, no human in the loop;
* ``HUMAN_APPROVAL``— hold as a proposed action for an IT lead to approve;
* ``DENY``          — never execute (and never even hold).

Because it is pure it is trivially unit-tested and cannot be talked out of a
decision by anything in a conversation — the LLM's text is *input data*, not a
control signal.

Guardrails encoded (defense in depth; any one can force approval or denial):

1. **Global kill-switch.** If autonomous execution is disabled by config, every
   action degrades to human approval (never denied — a human can still act).
2. **Catalog membership.** ``entry is None`` (off-catalog) ⇒ DENY. There is no
   path to run something the catalog doesn't list.
3. **Risk tier.** ``HIGH`` ⇒ never autonomous (approval at best). ``MEDIUM``
   autonomous only when config opts medium in; ``LOW`` autonomous by default.
4. **Prompt-injection signal.** If the free-text justification trips the injection
   scanner, the action is forced to human approval regardless of risk — the text
   never changes *what* runs (that's catalog-bound), but a suspicious request is
   surfaced to a human.
5. **Target integrity.** A missing/blank device id, or a device that failed its
   eligibility/compliance precheck, ⇒ DENY.
6. **Consent.** Device execution requires a live consent record for the target
   employee; absent ⇒ DENY.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from app.services.agents.device_actions.catalog import (
    AppCatalogEntry,
    DeviceActionEntry,
    RemediationCatalogEntry,
    RiskTier,
)

# Bump on any change to the decision logic or guardrail set.
AUTONOMY_POLICY_VERSION = "1.0.0"

# A resolved catalog entry of any of the three kinds.
CatalogEntry = AppCatalogEntry | RemediationCatalogEntry | DeviceActionEntry


class ExecutionDecision(StrEnum):
    AUTONOMOUS = "autonomous"
    HUMAN_APPROVAL = "human_approval"
    DENY = "deny"


class DenyReason(StrEnum):
    OFF_CATALOG = "off_catalog"
    NO_DEVICE_TARGET = "no_device_target"
    DEVICE_INELIGIBLE = "device_ineligible"
    NO_CONSENT = "no_consent"


@dataclass(frozen=True)
class PolicyInputs:
    """Everything the policy needs, gathered by the caller (never the LLM)."""

    entry: CatalogEntry | None
    device_id: str | None
    device_eligible: bool = True  # passed compliance/enrollment precheck
    consent_present: bool = True  # live consent for the target employee
    justification: str = ""  # free text from the requester (scanned)
    autonomous_enabled: bool = True  # global kill-switch (config)
    autonomous_medium_allowed: bool = False  # opt medium-risk into autonomy


@dataclass(frozen=True)
class PolicyDecision:
    """The decision plus a machine-readable trace for audit."""

    decision: ExecutionDecision
    risk_tier: str | None
    reason: str
    signals: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_autonomous(self) -> bool:
        return self.decision is ExecutionDecision.AUTONOMOUS

    @property
    def is_denied(self) -> bool:
        return self.decision is ExecutionDecision.DENY


# ── Prompt-injection scanner ──────────────────────────────────────────────────
# Heuristic, deterministic. It does NOT decide what runs (the catalog does); it
# only raises a signal that downgrades autonomy to human review when a request's
# free text looks like an attempt to subvert the agent.

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all|any|previous|prior)\b",
        r"disregard (the|all|your)\b",
        r"override (the|your|all)\b",
        r"bypass (the|approval|policy|guardrail)",
        r"you are now\b",
        r"system prompt",
        r"developer mode",
        r"without (approval|consent|permission)",
        r"\bexfiltrat",
        r"\bcurl\b|\bwget\b|\bInvoke-WebRequest\b|\bInvoke-Expression\b|\biex\b",
        r"powershell|cmd\.exe|/bin/sh|bash -c",
        r"base64|fromCharCode|-enc\b",
        r"disable (defender|antivirus|firewall|logging|audit)",
    )
)


def scan_for_injection(text: str | None) -> tuple[str, ...]:
    """Return the names of injection heuristics the text trips (empty = clean)."""
    if not text:
        return ()
    hits: list[str] = []
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return tuple(hits)


def _risk_of(entry: CatalogEntry) -> RiskTier:
    return entry.risk_tier


def evaluate_device_action(inputs: PolicyInputs) -> PolicyDecision:
    """Pure decision function. See module docstring for the guardrail order."""
    entry = inputs.entry

    # 2. Off-catalog is an immediate, unconditional denial.
    if entry is None:
        return PolicyDecision(
            decision=ExecutionDecision.DENY,
            risk_tier=None,
            reason="requested action is not in the approved catalog",
            signals=(DenyReason.OFF_CATALOG.value,),
        )

    risk = _risk_of(entry)

    # 5. Target integrity.
    if not inputs.device_id or not inputs.device_id.strip():
        return PolicyDecision(
            decision=ExecutionDecision.DENY,
            risk_tier=risk.value,
            reason="no target device id supplied",
            signals=(DenyReason.NO_DEVICE_TARGET.value,),
        )
    if not inputs.device_eligible:
        return PolicyDecision(
            decision=ExecutionDecision.DENY,
            risk_tier=risk.value,
            reason="target device failed the eligibility/compliance precheck",
            signals=(DenyReason.DEVICE_INELIGIBLE.value,),
        )

    # 6. Consent.
    if not inputs.consent_present:
        return PolicyDecision(
            decision=ExecutionDecision.DENY,
            risk_tier=risk.value,
            reason="no active consent for the target employee",
            signals=(DenyReason.NO_CONSENT.value,),
        )

    injection = scan_for_injection(inputs.justification)

    # 1. Global kill-switch: everything routes to human approval.
    if not inputs.autonomous_enabled:
        return PolicyDecision(
            decision=ExecutionDecision.HUMAN_APPROVAL,
            risk_tier=risk.value,
            reason="autonomous execution disabled by policy; awaiting human approval",
            signals=("autonomy_disabled", *injection),
        )

    # 4. Injection signal forces human review (never denies on text alone, since
    #    the catalog already bounds what can run — but a human should look).
    if injection:
        return PolicyDecision(
            decision=ExecutionDecision.HUMAN_APPROVAL,
            risk_tier=risk.value,
            reason="request text tripped injection heuristics; routed to human approval",
            signals=("prompt_injection_suspected", *injection),
        )

    # 3. Risk tier.
    if risk is RiskTier.HIGH:
        return PolicyDecision(
            decision=ExecutionDecision.HUMAN_APPROVAL,
            risk_tier=risk.value,
            reason="high-risk action is never autonomous; awaiting human approval",
            signals=("risk_high",),
        )
    if risk is RiskTier.MEDIUM and not inputs.autonomous_medium_allowed:
        return PolicyDecision(
            decision=ExecutionDecision.HUMAN_APPROVAL,
            risk_tier=risk.value,
            reason="medium-risk action requires human approval under current policy",
            signals=("risk_medium_requires_approval",),
        )

    return PolicyDecision(
        decision=ExecutionDecision.AUTONOMOUS,
        risk_tier=risk.value,
        reason="approved catalog action within autonomous risk threshold",
        signals=("autonomous_ok",),
    )


__all__ = [
    "AUTONOMY_POLICY_VERSION",
    "CatalogEntry",
    "DenyReason",
    "ExecutionDecision",
    "PolicyDecision",
    "PolicyInputs",
    "evaluate_device_action",
    "scan_for_injection",
]
