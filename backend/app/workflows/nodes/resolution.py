"""Resolution Agent Node — concise, grounded troubleshooting guidance.

This upgraded resolution node:
1. Generates focused responses based on diagnostic context
2. Provides next-step guidance (not full KB dumps)
3. Asks whether the step resolved the issue
4. Uses progressive disclosure — fewer steps at a time
"""

from langchain_core.messages import AIMessage

from app.core.config import settings
from app.core.logging import get_logger
from app.services.agents.confidence import compute_resolution_confidence
from app.services.agents.diagnostic_state import DiagnosticContext, DiagnosticPhase
from app.services.agents.playbooks import get_playbook
from app.services.llm_service import get_llm_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)

RESOLUTION_SYSTEM_PROMPT = (
    "You are a friendly, human IT Support Specialist at Aditi Consulting's internal help desk. "
    "You talk to employees in natural, warm, conversational language — like a helpful "
    "colleague sitting next to them, NOT a manual or a numbered checklist.\n\n"
    "IMPORTANT RULES:\n"
    "- Write 2-4 short sentences of natural prose. Do NOT output a numbered or bulleted list.\n"
    "- READ the approved steps and EXPLAIN what to do in your own words, conversationally.\n"
    "- You may only act on the approved steps provided — never invent new fixes or mention\n"
    "  anything not in them (no passwords, Windows Update, etc. unless listed).\n"
    "- Briefly acknowledge the problem in plain language (no internal codes/slugs).\n"
    "- End by asking, warmly, whether that helped.\n"
    "- If unsure, say so and offer to bring in the IT team.\n"
    "- Include the concrete actions (e.g. the exact menu path like Settings > "
    "Accessibility > Keyboard) naturally inside your sentences — the user does NOT "
    "see a separate steps list, so the how-to must live in your reply.\n"
    "- Focus on the SINGLE next step; do not preview later steps.\n"
    "- TONE ADAPTATION: If the user is frustrated, lead with empathy. "
    "If urgent, prioritize speed over detail.\n"
    "  If confused, simplify and clarify."
)

RESOLUTION_PROMPT = """An employee needs help. \
Reply to them directly in natural, conversational language.

What we understand about their issue (for your context — do NOT echo these labels back):
- Plain-English problem: {problem_description}
{additional_context}

The approved next step you may rely on (explain it naturally in your own words,
including the exact click-path/actions, and do NOT add any step that is not here.
The user does NOT see a separate list — put the how-to in your reply):
{knowledge_articles}

Write a short, friendly reply (2-4 sentences) that:
1. Acknowledges their problem in plain English (never use internal codes like "mailbox-full").
2. Explains, conversationally, what to try — referencing the approved steps in your own words.
3. Ends by asking whether that sorted it, and offers to escalate to IT if not.

Reply now (natural prose only, no numbered list):"""


def _get_steps(article: dict) -> list:
    """Extract steps from an article dict, supporting both DB and YAML field names."""
    return (
        article.get("resolution_steps")
        or article.get("troubleshooting_steps")
        or article.get("steps")
        or []
    )


def _step_text(step) -> tuple[str, str | None]:
    """Normalize a step (dict or str) into (instruction, details)."""
    if isinstance(step, dict):
        instruction = step.get("instruction") or step.get("step") or str(step)
        details = step.get("details") or step.get("expected_outcome")
        return instruction, details
    return str(step), None


def _build_progression(
    knowledge_results: list[dict], diag_ctx: DiagnosticContext
) -> tuple[list[dict], list[dict]]:
    """Build the ordered step plan and the remaining (not-yet-tried) steps.

    Steps are collected from the grounded articles in rank order (the
    subtype-matching article ranks first), de-duplicated, and then filtered to
    drop anything already suggested or marked failed. This is what makes the
    agent *advance* instead of repeating the same first-N steps every turn.
    """
    # Playbook enforcement: if we have a confident subtype AND a KB article that
    # matches it, draw steps ONLY from the subtype-matching article(s). Once those
    # are exhausted we escalate rather than bleeding into other same-family
    # articles whose steps don't fit the subtype (e.g. "Work Offline" for a
    # mailbox-full issue). Without a subtype match, use all grounded articles.
    subtype = (diag_ctx.issue_subtype or "").replace("_", "-").lower()

    def _matches_subtype(art: dict) -> bool:
        sc = (
            (art.get("subcategory") or art.get("subtype") or art.get("issue_type") or "")
            .replace("_", "-")
            .lower()
        )
        return bool(subtype) and sc == subtype

    matched = [a for a in knowledge_results if _matches_subtype(a)]
    source_articles = matched if matched else knowledge_results

    ordered: list[dict] = []
    seen: set[str] = set()
    for art in source_articles:
        for raw in _get_steps(art):
            instruction, details = _step_text(raw)
            key = DiagnosticContext._norm_step(instruction)
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(
                {
                    "instruction": instruction,
                    "details": details,
                    "source": art.get("title", ""),
                }
            )

    remaining = [s for s in ordered if not diag_ctx.is_step_exhausted_or_seen(s["instruction"])]
    return ordered, remaining


async def resolution_node(state: WorkflowState) -> dict:
    """Generate focused, progressive, grounded resolution from retrieved knowledge.

    This node:
    1. Builds a step plan from the grounded articles (subtype-matching first)
    2. Advances past steps already suggested or reported as failed
    3. Presents the NEXT 2-3 steps (never repeats a failed batch)
    4. Detects exhaustion/loops and routes to escalation when nothing is left
    5. Computes a calibrated, multi-component resolution confidence
    6. NEW: If user asks for simpler explanation, simplify first before escalating
    """
    logger.info(
        "resolution_node_start",
        session_id=state.get("session_id"),
        knowledge_count=len(state.get("knowledge_results", [])),
    )

    knowledge_results = state.get("knowledge_results", [])
    diag_ctx = DiagnosticContext.from_dict(state.get("diagnostic_context") or {})
    trace = state.get("retrieval_trace") or {}

    # ── NEW: Check if KB articles actually match the diagnosed issue ──
    # This enables agent collaboration: if retrieval found same-category articles
    # but wrong subtype, we should try web search instead.
    from app.services.agents.retrieval_quality import RetrievalQualityAnalyzer

    quality = RetrievalQualityAnalyzer(knowledge_results, diag_ctx).analyze()
    logger.info(
        "retrieval_quality_check",
        is_relevant=quality.is_relevant,
        confidence=quality.confidence,
        should_try_web_search=quality.should_try_web_search,
        subtype_matches=quality.matched_subtype_count,
    )

    # NEW: Check if user asked for simpler explanation (before escalating)
    messages = state.get("messages", [])
    latest_message = messages[-1].content if messages else ""
    asks_for_simpler = _asks_for_simpler_explanation(latest_message)

    if asks_for_simpler and diag_ctx.resolution_attempts >= 2:
        # User tried steps and is confused → simplify instead of escalating
        logger.info(
            "simplification_requested",
            session_id=state.get("session_id"),
            attempts=diag_ctx.resolution_attempts,
        )
        return await _handle_simplification_request(state, diag_ctx, knowledge_results, trace)

    # ── Mismatch detected: KB has wrong articles for this issue → try web search ──
    if quality.should_try_web_search and knowledge_results:
        from app.services.web_search_service import WebSearchService

        logger.info(
            "retrieval_mismatch_detected",
            session_id=state.get("session_id"),
            kb_count=len(knowledge_results),
            reason=quality.mismatch_reason,
        )

        diag_ctx.resolution_attempts += 1
        web_service = WebSearchService()
        web_results = await web_service.search(
            query=diag_ctx.exact_problem_statement or "",
            category=diag_ctx.issue_subtype or diag_ctx.issue_category or "",
            system=diag_ctx.normalized_system or "",
        )

        # If web search found better results, use them
        if web_results:
            web_response = _format_web_results_for_user(web_results)
            diag_ctx.resolution_confidence = 0.4  # Slightly higher for mismatch recovery
            diag_ctx.phase = DiagnosticPhase.CONFIRMING
            diag_ctx.last_response_type = "resolve"
            logger.info(
                "web_search_used_for_mismatch",
                results_count=len(web_results),
                kb_mismatch_reason=quality.mismatch_reason,
            )
            return {
                "current_node": "resolve",
                "resolution_steps": [],
                "resolution_confidence": 0.4,
                "diagnostic_context": diag_ctx.to_dict(),
                "conversation_phase": diag_ctx.phase.value,
                "messages": [AIMessage(content=web_response)],
                "audit_trail": [
                    {
                        "event": "resolution.web_search_mismatch_recovery",
                        "confidence": 0.4,
                        "kb_mismatch": quality.mismatch_reason,
                        "web_results": len(web_results),
                        "resolution_attempt": diag_ctx.resolution_attempts,
                    }
                ],
            }

        # Web search also failed after mismatch → escalate with context
        logger.info(
            "mismatch_without_web_recovery",
            kb_mismatch=quality.mismatch_reason,
        )
        diag_ctx.escalation_reason = (
            f"I found some KB articles, but they don't seem to match your specific issue "
            f"({quality.mismatch_reason}). Let me connect you with our IT team so they can "
            f"help you directly."
        )
        diag_ctx.resolution_confidence = 0.0
        diag_ctx.phase = DiagnosticPhase.CONFIRMING
        diag_ctx.last_response_type = "resolve"
        return {
            "current_node": "resolve",
            "resolution_steps": [],
            "resolution_confidence": 0.0,
            "diagnostic_context": diag_ctx.to_dict(),
            "conversation_phase": diag_ctx.phase.value,
            "messages": [
                AIMessage(
                    content=(
                        "I wasn't able to find a specific solution for this in our knowledge "
                        "base or online. Would you like me to create a support ticket "
                        "so our IT team can assist you directly?"
                    )
                )
            ],
            "audit_trail": [
                {
                    "event": "resolution.generated",
                    "confidence": 0.0,
                    "steps_count": 0,
                    "method": "none",
                    "resolution_attempt": diag_ctx.resolution_attempts,
                }
            ],
        }

    ordered, remaining = _build_progression(knowledge_results, diag_ctx)

    # ── Proactive escalation after N consecutive misses (B1) ──────────
    # Even if more grounded steps exist, don't drag the user through all of
    # them — offer a live specialist once enough steps have failed.
    miss_threshold = max(1, settings.RESOLUTION_MISS_ESCALATE_THRESHOLD)
    if remaining and len(diag_ctx.failed_steps) >= miss_threshold:
        diag_ctx.resolution_attempts += 1
        diag_ctx.resolution_confidence = 0.0
        diag_ctx.phase = DiagnosticPhase.ESCALATING
        diag_ctx.last_response_type = "escalate"
        subtype = diag_ctx.issue_subtype or diag_ctx.symptom or "this issue"
        diag_ctx.escalation_reason = (
            f"{len(diag_ctx.failed_steps)} troubleshooting steps for '{subtype}' were "
            f"attempted without resolving the issue."
        )
        logger.info(
            "resolution_miss_threshold_escalation",
            failed=len(diag_ctx.failed_steps),
            threshold=miss_threshold,
        )
        return {
            "current_node": "resolve",
            "resolution_steps": [],
            "resolution_confidence": 0.0,
            "escalation_reason": diag_ctx.escalation_reason,
            "diagnostic_context": diag_ctx.to_dict(),
            "conversation_phase": diag_ctx.phase.value,
            "audit_trail": [
                {
                    "event": "resolution.miss_threshold_escalation",
                    "failed_steps": len(diag_ctx.failed_steps),
                    "threshold": miss_threshold,
                }
            ],
        }

    # ── Exhaustion / loop → escalate (no message; escalation speaks) ──
    if not remaining:
        diag_ctx.loop_counter += 1
        diag_ctx.resolution_attempts += 1
        diag_ctx.resolution_confidence = 0.0
        diag_ctx.phase = DiagnosticPhase.ESCALATING
        diag_ctx.last_response_type = "escalate"
        subtype = diag_ctx.issue_subtype or diag_ctx.symptom or "this issue"
        diag_ctx.escalation_reason = (
            f"All grounded troubleshooting steps for '{subtype}' were attempted "
            f"without resolving the issue."
        )
        logger.info(
            "resolution_steps_exhausted",
            subtype=diag_ctx.issue_subtype,
            tried=len(diag_ctx.failed_steps),
            loop_counter=diag_ctx.loop_counter,
        )
        return {
            "current_node": "resolve",
            "resolution_steps": [],
            "resolution_confidence": 0.0,
            "escalation_reason": diag_ctx.escalation_reason,
            "diagnostic_context": diag_ctx.to_dict(),
            "conversation_phase": diag_ctx.phase.value,
            "audit_trail": [
                {
                    "event": "resolution.exhausted",
                    "subtype": diag_ctx.issue_subtype,
                    "steps_tried": len(diag_ctx.failed_steps),
                    "loop_counter": diag_ctx.loop_counter,
                }
            ],
        }

    # ── Present the next batch of NEW steps ──────────────────────
    batch_size = max(1, settings.RESOLUTION_STEP_BATCH_SIZE)
    batch = remaining[:batch_size]
    confidence_bd = _score_confidence(state, diag_ctx, trace)

    resolution = await _render_resolution(
        batch, knowledge_results, state, diag_ctx, confidence_bd.final
    )

    # Remember what we presented so the next turn advances past it.
    diag_ctx.record_suggested_steps([s["instruction"] for s in resolution["steps"]])
    src = state.get("knowledge_citations") or []
    for c in src:
        title = c.get("title")
        if title and title not in diag_ctx.retrieval_sources_used:
            diag_ctx.retrieval_sources_used.append(title)

    diag_ctx.resolution_attempts += 1
    diag_ctx.resolution_confidence = confidence_bd.final
    diag_ctx.last_resolution_failed = False  # consumed this turn
    diag_ctx.last_response_type = "resolve"
    diag_ctx.phase = DiagnosticPhase.CONFIRMING

    audit_entry = {
        "event": "resolution.generated",
        "confidence": confidence_bd.final,
        "confidence_breakdown": confidence_bd.to_dict(),
        "steps_count": len(resolution["steps"]),
        "method": resolution.get("method", "direct"),
        "subtype": diag_ctx.issue_subtype,
        "resolution_attempt": diag_ctx.resolution_attempts,
        "remaining_after": max(0, len(remaining) - len(batch)),
    }

    return {
        "current_node": "resolve",
        "resolution_steps": resolution["steps"],
        "resolution_confidence": confidence_bd.final,
        "confidence_breakdown": confidence_bd.to_dict(),
        "diagnostic_context": diag_ctx.to_dict(),
        "conversation_phase": diag_ctx.phase.value,
        "messages": [AIMessage(content=resolution["response"])],
        "audit_trail": [audit_entry],
        "quick_replies": [
            {"label": "That worked", "value": "that worked"},
            {"label": "Still not working", "value": "still not working"},
            {"label": "Talk to a specialist", "value": "talk to a specialist"},
        ],
    }


def _score_confidence(state: WorkflowState, diag_ctx: DiagnosticContext, trace: dict):
    """Compute the calibrated composite confidence for this resolution."""
    playbook = get_playbook(diag_ctx.issue_category or "other")
    playbook_fit = bool(
        diag_ctx.issue_subtype and playbook and diag_ctx.issue_subtype in playbook.subtypes
    )
    return compute_resolution_confidence(
        system_match=diag_ctx.entity_confidence,
        subtype_match=diag_ctx.subtype_confidence,
        retrieval_relevance=state.get("knowledge_confidence", 0.0),
        has_subtype_article=bool(trace.get("has_subtype_match")),
        same_family=True,  # grounding guard guarantees kept articles share the family
        playbook_fit=playbook_fit,
        loop_counter=diag_ctx.loop_counter,
        failed_attempts=diag_ctx.resolution_attempts,
    )


async def _render_resolution(
    batch: list[dict],
    knowledge_results: list[dict],
    state: WorkflowState,
    diag_ctx: DiagnosticContext,
    confidence: float,
) -> dict:
    """Render a response from the pre-selected, grounded step batch."""
    llm = get_llm_service()
    if llm.is_available:
        try:
            return await _llm_resolution(batch, state, diag_ctx, llm, confidence)
        except Exception as e:
            logger.warning("resolution_llm_fallback", error=str(e))

    # Deterministic fallback: format the batch directly.
    steps = [
        {"step_number": i, "instruction": s["instruction"], "details": s.get("details")}
        for i, s in enumerate(batch, 1)
    ]
    response = _format_concise_response(steps, knowledge_results[0], confidence, diag_ctx)
    return {"steps": steps, "confidence": confidence, "method": "direct", "response": response}


async def _llm_resolution(
    batch: list[dict],
    state: WorkflowState,
    diag_ctx: DiagnosticContext,
    llm: object,
    confidence: float,
) -> dict:
    """Use the LLM to phrase the response, grounded ONLY in the selected batch."""
    from app.services.llm_service import LLMService

    assert isinstance(llm, LLMService)

    # The LLM may only rephrase the steps we selected — it cannot introduce new
    # ones. This is the grounding constraint at generation time.
    steps_text = "\n".join(
        f"{i}. {s['instruction']}" + (f" — {s['details']}" if s.get("details") else "")
        for i, s in enumerate(batch, 1)
    )
    articles_text = f"Approved next steps (use ONLY these, do not invent others):\n{steps_text}"

    problem_desc = diag_ctx.exact_problem_statement or diag_ctx.symptom or "not specified"
    symptom = (
        diag_ctx.issue_subtype or diag_ctx.symptom or diag_ctx.issue_subcategory or "general issue"
    )

    additional = []
    if diag_ctx.platform_os:
        additional.append(f"- Platform: {diag_ctx.platform_os}")
    if diag_ctx.device_type:
        additional.append(f"- Device: {diag_ctx.device_type}")
    if diag_ctx.error_message:
        additional.append(f"- Error message: {diag_ctx.error_message}")
    if diag_ctx.failed_steps:
        additional.append(f"- Already tried (do NOT repeat): {', '.join(diag_ctx.failed_steps)}")

    # Include conversation summary if available (turn > 10)
    conversation_summary = getattr(diag_ctx, "conversation_summary", None)
    if conversation_summary:
        additional.append(f"- Conversation so far: {conversation_summary}")

    # Include urgency/sentiment context for tone adjustment
    if diag_ctx.urgency:
        additional.append(f"- User urgency level: {diag_ctx.urgency}")
    if diag_ctx.business_impact:
        additional.append(f"- Business impact: {diag_ctx.business_impact}")

    additional_text = "\n".join(additional) if additional else "None"

    prompt = RESOLUTION_PROMPT.format(
        category=state.get("issue_category", "other"),
        problem_description=problem_desc,
        symptom=symptom,
        additional_context=additional_text,
        knowledge_articles=articles_text,
    )

    content = await llm.complete(prompt, system_prompt=RESOLUTION_SYSTEM_PROMPT)

    steps = [
        {"step_number": i, "instruction": s["instruction"], "details": s.get("details")}
        for i, s in enumerate(batch, 1)
    ]
    return {"steps": steps, "confidence": confidence, "method": "llm", "response": content}


def _direct_resolution(
    knowledge_results: list[dict],
    state: WorkflowState,
    diag_ctx: DiagnosticContext,
) -> dict:
    """Extract steps directly from the best matching article (no-LLM fallback)."""
    best_article = knowledge_results[0]
    raw_steps = _get_steps(best_article)
    confidence = min(0.9, state.get("knowledge_confidence", 0.5) + 0.1)

    # Only take the first 3 steps for progressive disclosure
    formatted_steps = []
    for i, step in enumerate(raw_steps[:3], 1):
        if isinstance(step, dict):
            formatted_steps.append(
                {
                    "step_number": i,
                    "instruction": step.get("instruction") or step.get("step") or str(step),
                    "details": step.get("details") or step.get("expected_outcome"),
                }
            )
        elif isinstance(step, str):
            formatted_steps.append(
                {
                    "step_number": i,
                    "instruction": step,
                    "details": None,
                }
            )

    # Build concise response
    response = _format_concise_response(formatted_steps, best_article, confidence, diag_ctx)

    return {
        "steps": formatted_steps,
        "confidence": confidence,
        "method": "direct",
        "response": response,
    }


# Natural, plain-English descriptions of each subtype. Keyed by subtype slug so we
# NEVER surface the raw slug (e.g. "outlook-crash") to the user.
_SUBTYPE_PHRASES: dict[str, str] = {
    # Outlook / email
    "mailbox-full": (
        "It looks like your mailbox is full, which can stop new mail from coming through."
    ),
    "not-receiving-emails": "It looks like new emails aren't coming through to you.",
    "sending-failure": "It sounds like your emails aren't going out.",
    "outlook-slow": "It sounds like Outlook is running slowly or freezing on you.",
    "outlook-crash": "It sounds like Outlook isn't opening, or keeps closing on you.",
    "offline-mode": "It looks like Outlook is stuck working offline.",
    "calendar-sync": "It looks like your calendar isn't syncing properly.",
    "search-not-working": "It sounds like search isn't working in Outlook.",
    "rule-issue": "It looks like one of your Outlook rules may be moving your mail.",
    "addin-issue": "It sounds like an Outlook add-in might be causing the trouble.",
    "sign-in-problem": "It sounds like you're having trouble signing in to Outlook.",
    # Access
    "account-locked": "It looks like your account is locked.",
    "password-expired": "It sounds like this is a password issue.",
    "mfa-not-working": "It looks like your multi-factor sign-in isn't working.",
    # Zoom / audio (light coverage)
    "no-audio": "It sounds like you can't hear audio.",
    "no-video": "It sounds like your camera isn't working.",
    "cant-join-meeting": "It looks like you can't join the meeting.",
}


def _lower_first(text: str) -> str:
    """Lowercase only the first character so a step reads naturally mid-sentence."""
    return text[:1].lower() + text[1:] if text else text


def _friendly_problem(diag_ctx: DiagnosticContext) -> str:
    """A natural, plain-English statement of the problem (never a raw slug)."""
    subtype = (diag_ctx.issue_subtype or "").replace("_", "-").lower()
    if subtype in _SUBTYPE_PHRASES:
        return _SUBTYPE_PHRASES[subtype]
    system = diag_ctx.affected_system or "your system"
    return f"Let's take a look at the {system} issue you're seeing."


def _format_concise_response(
    steps: list[dict],
    article: dict,
    confidence: float,
    diag_ctx: DiagnosticContext,
) -> str:
    """Compose a natural, conversational reply.

    The precise click-by-click steps are rendered to the user as a separate
    structured block, so this message paraphrases the guidance in plain English
    instead of dumping the numbered list verbatim (which read like a manual and
    leaked internal slugs).
    """
    if not steps:
        return (
            "I'm sorry, I couldn't find a reliable fix for this in our knowledge base. "
            "Let me connect you with our IT team so they can take a closer look — "
            "shall I raise a ticket for you?"
        )

    first_action = _lower_first(steps[0]["instruction"])
    is_followup = bool(diag_ctx.failed_steps)

    parts: list[str] = []
    if is_followup:
        parts.append("Thanks for giving that a try — no worries, let's keep going.")
        parts.append(f"A good next step is to {first_action}.")
    else:
        parts.append(_friendly_problem(diag_ctx))
        parts.append(f"The best place to start is to {first_action}.")

    detail = steps[0].get("details")
    if len(steps) == 1 and detail:
        parts.append(f"Specifically: {detail}")
    elif len(steps) > 1:
        parts.append("Here are the exact steps to try.")

    if confidence >= 0.8:
        parts.append(
            "Give those a go and let me know if that sorts it — I'm here if you need more help."
        )
    else:
        parts.append(
            "Give those a try and tell me how it goes. If it doesn't help, "
            "I can escalate this to our IT team for you."
        )

    return " ".join(parts)


def _format_web_results_for_user(results: list) -> str:
    """Format web search results for display to user.

    Results include external sources when internal KB has no guidance.
    Always include a disclaimer that these are external sources.
    """
    if not results:
        return (
            "I wasn't able to find guidance in our knowledge base. "
            "Let me connect you with our IT team instead."
        )

    trust_badge = {
        "official": "✓ Official",
        "vendor": "✓ Vendor",
        "trusted_community": "Community",
        "general_blog": "Blog",
    }

    formatted_results = []
    for i, result in enumerate(results, 1):
        badge = trust_badge.get(result.trust_level.value, "External")
        formatted_results.append(
            f"**{i}. {result.title}** [{badge}]\n{result.snippet}\n[Read more]({result.url})"
        )

    return (
        "I couldn't find this in our internal knowledge base, but I found some external resources "
        "that might help:\n\n" + "\n\n".join(formatted_results) + "\n\n"
        "You're welcome to try one of these solutions. Let me know if it helps, "
        "or I can escalate this to our IT team if you'd prefer."
    )


def _asks_for_simpler_explanation(message: str) -> bool:
    """Check if user is asking for simpler/clearer explanation.

    Keywords: simpler, explain, understand, confusing, easier, break down, etc.
    """
    keywords = {
        "simpler",
        "simple",
        "easier",
        "explain",
        "understand",
        "confusing",
        "confused",
        "don't understand",
        "not clear",
        "unclear",
        "break down",
        "step by step",
        "more detail",
        "more clearly",
        "plain english",
    }
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in keywords)


async def _handle_simplification_request(
    state: WorkflowState,
    diag_ctx: DiagnosticContext,
    knowledge_results: list[dict],
    trace: dict,
) -> dict:
    """Handle user request for simpler explanation.

    Instead of escalating, provide ultra-simple guidance with minimal steps.
    """
    if not knowledge_results:
        # No KB, can't simplify → escalate
        return {
            "current_node": "resolve",
            "resolution_steps": [],
            "resolution_confidence": 0.0,
            "diagnostic_context": diag_ctx.to_dict(),
            "conversation_phase": diag_ctx.phase.value,
            "messages": [
                AIMessage(
                    content=(
                        "I understand this is getting complicated. Let me have our IT team "
                        "take a closer look so they can walk you through this step by step. "
                        "Is that okay?"
                    )
                )
            ],
            "audit_trail": [
                {
                    "event": "resolution.escalation_offered_for_simplification",
                    "reason": "No KB articles to simplify further",
                    "attempts": diag_ctx.resolution_attempts,
                }
            ],
        }

    # Get the best article (most relevant)
    best_article = knowledge_results[0]
    ordered, remaining = _build_progression(knowledge_results, diag_ctx)

    # NEW: Create ULTRA-simplified version with 1-2 steps maximum
    if remaining:
        # Take only the first step, make it extremely simple
        simple_batch = [remaining[0]]  # Just 1 step
    elif ordered:
        # If no remaining, take first from ordered
        simple_batch = [ordered[0]]
    else:
        # Can't simplify further → offer escalation
        return {
            "current_node": "resolve",
            "resolution_steps": [],
            "resolution_confidence": 0.0,
            "diagnostic_context": diag_ctx.to_dict(),
            "conversation_phase": diag_ctx.phase.value,
            "messages": [
                AIMessage(
                    content=(
                        "I understand these steps are getting complicated. "
                        "Let me connect you with our IT team so they can help you directly. "
                        "Is that okay?"
                    )
                )
            ],
            "audit_trail": [
                {
                    "event": "resolution.escalation_offered",
                    "reason": "Steps too complex to simplify further",
                    "attempts": diag_ctx.resolution_attempts,
                }
            ],
        }

    # Render ultra-simple response
    resolution = await _render_simple_resolution(simple_batch, best_article, diag_ctx)

    # Log simplification attempt
    diag_ctx.record_suggested_steps([s["instruction"] for s in simple_batch])
    diag_ctx.resolution_attempts += 1
    diag_ctx.last_response_type = "resolve_simplified"
    diag_ctx.phase = DiagnosticPhase.CONFIRMING

    logger.info(
        "resolution_simplified",
        session_id=state.get("session_id"),
        steps_count=1,
        attempt=diag_ctx.resolution_attempts,
    )

    return {
        "current_node": "resolve",
        "resolution_steps": resolution["steps"],
        "resolution_confidence": 0.6,  # Lower confidence for simplified guidance
        "diagnostic_context": diag_ctx.to_dict(),
        "conversation_phase": diag_ctx.phase.value,
        "messages": [AIMessage(content=resolution["response"])],
        "quick_replies": [
            {"label": "That worked", "value": "that worked"},
            {"label": "Still not working", "value": "still not working"},
            {"label": "Talk to a specialist", "value": "talk to a specialist"},
        ],
        "audit_trail": [
            {
                "event": "resolution.simplified",
                "confidence": 0.6,
                "steps_count": 1,
                "attempt": diag_ctx.resolution_attempts,
            }
        ],
    }


async def _render_simple_resolution(
    batch: list[dict],
    article: dict,
    diag_ctx: DiagnosticContext,
) -> dict:
    """Render ultra-simple resolution with plain English, minimal jargon."""

    # Take only the first (most important) step
    step = batch[0] if batch else {}
    instruction = step.get("instruction", "")
    details = step.get("details", "")

    if not instruction:
        return {
            "steps": [],
            "confidence": 0.0,
            "method": "error",
            "response": (
                "I'm sorry, I'm having trouble simplifying these steps. "
                "Let me connect you with our IT team."
            ),
        }

    # Build ultra-simple response with step-by-step language
    simple_response = (
        f"Let me break this down into just one simple step:\n\n"
        f"**{instruction}**\n"
        f"{details if details else ''}\n\n"
        f"That's really all you need to do! "
        f"Try this step and let me know if it helps. "
        f"If it doesn't, I can get our IT team involved."
    )

    steps = [{"step_number": 1, "instruction": instruction, "details": details}]

    return {
        "steps": steps,
        "confidence": 0.6,
        "method": "simplified",
        "response": simple_response,
    }
