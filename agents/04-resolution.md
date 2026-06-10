# Agent 04: Resolution

> **One-liner**: Generates step-by-step troubleshooting guidance using RAG
> (Retrieval-Augmented Generation) from knowledge base articles.

---

## Role

The Resolution Agent takes retrieved knowledge articles and the conversation
context, then uses an LLM to synthesize clear, actionable troubleshooting
steps that the user can follow. It MUST ground all advice in the knowledge
base — never hallucinate steps.

---

## Interface

| Direction | Type | Description |
|-----------|------|-------------|
| **Input** | `knowledge_results: list[dict]` | Articles from Retrieval Agent |
| **Input** | `knowledge_confidence: float` | Retrieval confidence |
| **Input** | `issue_category: str` | From Triage |
| **Input** | `messages: list[BaseMessage]` | Full conversation |
| **Output** | `resolution_steps: list[ResolutionStep]` | Ordered steps |
| **Output** | `resolution_confidence: float` | Overall confidence (0.0-1.0) |
| **Output** | `messages` (appended) | AI message with formatted guidance |

---

## Algorithm

```python
async def resolution_node(state: WorkflowState) -> dict:
    """Generate troubleshooting steps from knowledge."""
    logger.info("resolution.start", category=state.get("issue_category"))

    knowledge = state.get("knowledge_results", [])
    knowledge_confidence = state.get("knowledge_confidence", 0.0)

    # Step 1: Skip if no useful knowledge
    if not knowledge or knowledge_confidence < 0.3:
        return {
            "resolution_confidence": 0.0,
            "resolution_steps": [],
            "current_node": "resolution",
            "audit_trail": [{"event": "resolution.skipped", "reason": "no_knowledge"}],
        }

    # Step 2: Generate resolution via LLM
    try:
        result = await generate_resolution(
            knowledge_articles=knowledge,
            user_messages=state["messages"],
            category=state.get("issue_category"),
        )
    except (TimeoutError, ConnectionError):
        return {
            "resolution_confidence": 0.0,
            "current_node": "resolution",
            "audit_trail": [{"event": "resolution.llm_failed"}],
        }

    # Step 3: Calculate confidence
    confidence = calculate_confidence(
        knowledge_confidence=knowledge_confidence,
        num_articles=len(knowledge),
        category_match=result.category_match,
    )

    # Step 4: Build user-facing message
    ai_message = format_resolution_message(result.steps, confidence)

    return {
        "resolution_steps": result.steps,
        "resolution_confidence": confidence,
        "messages": [AIMessage(content=ai_message)],
        "current_node": "resolution",
        "audit_trail": [{"event": "resolution.generated", "confidence": confidence}],
    }
```

---

## Prompt Template

```
SYSTEM: You are a helpful IT support assistant for Aditi Consulting.
Generate clear, step-by-step troubleshooting instructions based ONLY on
the knowledge base articles provided below.

CRITICAL RULES:
1. Only include steps that are directly supported by the knowledge articles
2. Do NOT invent steps or add information not in the articles
3. Use friendly, clear language appropriate for non-technical employees
4. Number each step clearly
5. Include specific details (menu paths, button names, etc.)
6. If the knowledge doesn't fully cover the issue, say so honestly
7. Use tentative language: "Try this" not "Do this"

KNOWLEDGE ARTICLES:
{knowledge_articles_formatted}

USER'S ISSUE: {user_description}
CATEGORY: {issue_category}

Generate troubleshooting steps in this JSON format:
{
  "steps": [
    {"step_number": 1, "instruction": "Brief action", "details": "Detailed how-to"},
    ...
  ],
  "category_match": true/false,  // Does the KB directly address this issue?
  "notes": "Any caveats or limitations"
}
```

---

## Confidence Calibration

### Formula

```python
def calculate_confidence(
    knowledge_confidence: float,  # Best retrieval score
    num_articles: int,            # How many relevant articles
    category_match: bool,         # KB directly addresses category
) -> float:
    """Calculate resolution confidence score."""
    # Weighted components
    retrieval_weight = 0.50 * knowledge_confidence
    coverage_weight = 0.20 * min(num_articles / 3, 1.0)  # 3+ articles = full score
    match_weight = 0.30 * (1.0 if category_match else 0.3)

    return round(retrieval_weight + coverage_weight + match_weight, 2)
```

### Score Interpretation

| Score | Meaning | User Experience |
|-------|---------|-----------------|
| 0.85-1.00 | Strong match, specific steps | Direct resolution, no disclaimers |
| 0.70-0.84 | Good match, mostly relevant | Resolution with "Let me know if this helps" |
| 0.50-0.69 | Partial match, generic | Resolution + "I can connect you with IT staff" |
| 0.00-0.49 | Weak/no match | Skip resolution, escalate directly |

---

## Message Formatting

### High Confidence (≥ 0.8)
```
I found some steps that should help with your {category} issue:

1. **{instruction}**
   {details}

2. **{instruction}**
   {details}

Let me know if these steps resolve the issue, or if you'd like me to
connect you with our IT team for additional help.
```

### Medium Confidence (0.5-0.8)
```
Based on what I found in our knowledge base, here are some steps you can try:

1. **{instruction}**
   {details}

⚠️ These steps may not fully address your specific situation.
Would you like me to connect you with a human IT agent who can help further?
```

---

## Failure Modes

| Failure | Detection | Recovery | Impact |
|---------|-----------|----------|--------|
| LLM timeout (>15s) | `asyncio.TimeoutError` | Set confidence=0.0, escalate | User escalated |
| LLM returns invalid JSON | Parse error | Retry once, then escalate | Brief delay |
| LLM hallucination | Steps not in KB content | Validation check (future) | Misinformation risk |
| Empty knowledge input | `len(knowledge) == 0` | Skip generation, confidence=0.0 | Escalation |
| LLM refusal | Content filter triggered | Set confidence=0.0 | Escalation |
| Token limit exceeded | LLM returns truncated | Reduce context, retry | Delay |

### Hallucination Prevention

```python
def validate_resolution_against_kb(steps: list, knowledge: list) -> bool:
    """Check that generated steps are grounded in KB content."""
    kb_text = " ".join(article["content"] for article in knowledge).lower()
    for step in steps:
        # Check that key terms from each step appear in KB
        key_terms = extract_key_terms(step["instruction"])
        if not any(term in kb_text for term in key_terms):
            logger.warning("resolution.possible_hallucination", step=step)
            return False
    return True
```

---

## Boundaries

- ❌ Must NEVER invent steps not grounded in knowledge base
- ❌ Must NEVER promise resolution ("this will fix it")
- ❌ Must NEVER include sensitive system paths or credentials
- ❌ Must NEVER skip confidence scoring
- ❌ Must NEVER contradict information in knowledge articles
- ✅ Must ALWAYS cite which article(s) steps derive from
- ✅ Must ALWAYS include confidence score in state
- ✅ Must offer escalation when confidence < 0.8
- ✅ Must use tentative language ("try this", "you might")
- ✅ Must format steps clearly with numbered instructions

---

## Testing Checklist

- [ ] Generates relevant steps from valid knowledge articles
- [ ] Returns confidence=0.0 when no knowledge provided
- [ ] Handles LLM timeout gracefully (no crash)
- [ ] Confidence formula produces correct scores for known inputs
- [ ] Message formatting includes escalation offer when confidence < 0.8
- [ ] Steps are grounded in provided knowledge content
- [ ] Audit trail entry includes confidence and step count

---

## Dependencies

| Dependency | Purpose | Fallback |
|------------|---------|----------|
| LiteLLM | Step generation | Confidence=0.0, escalate |
| Knowledge articles | Source truth for steps | — (skip if empty) |
| Message formatter | User-facing output | Plain text fallback |

---

## Implementation File

`backend/app/workflows/nodes/resolution.py`
