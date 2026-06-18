# Agent Collaboration Architecture — Elegant Fallbacks

## Problem (Old Design)

The original system had **rigid sequential routing** with no intelligence about whether KB results were actually useful:

```
User Message
    ↓
Triage Agent → classify issue
    ↓
Retrieval Agent → fetch KB articles (ANY same-category articles)
    ↓
Resolution Agent → try to render response (using mismatched articles)
    ↓
If LLM fails → fall back to stiff template ("the your system issue...")
```

**Example failure**: User says "can't connect to internet"
1. Triage classifies: `category=network/connectivity, subtype=internet`
2. Retrieval returns: 14 KB articles (all VPN/Wi-Fi focused)
3. Resolution tries: Render VPN steps for internet issue → LLM confused → template fallback

---

## Solution (New Design)

**Agents now collaborate via intelligent quality gates and fallback strategies:**

```
User Message
    ↓
Triage Agent
    │ → Issue classification + context
    ↓
Retrieval Agent
    │ → KB search (broad candidate pool)
    ↓
Quality Analyzer ← ← ← NEW GATE
    │ Checks: Do these articles match the diagnosed issue?
    │ - Exact subtype match? → ✅ Use KB
    │ - Same category, wrong subtype? → ⚠️  Try web search
    │ - Different category? → ❌ Try web search
    ↓
Resolution Agent (Smart Strategy Selector)
    │ Chooses one of:
    │ 1. GROUNDED_LLM (if exact KB match)
    │ 2. WEB_SEARCH (if KB mismatch or low confidence)
    │ 3. SIMPLIFIED (if user confused)
    │ 4. ESCALATE (if all else fails)
    ↓
Response
    └─ Natural language (via LLM or web search)
       NOT a stiff template
```

---

## Key Components

### 1. **RetrievalQualityAnalyzer** (`retrieval_quality.py`)

Detects when KB articles don't match the diagnosed issue:

```python
quality = RetrievalQualityAnalyzer(kb_articles, diag_ctx).analyze()

# Returns:
# - is_relevant: bool (are these articles useful?)
# - has_exact_match: bool (do they match exact issue_subtype?)
# - confidence: float (0.0–1.0)
# - should_try_web_search: bool (even if KB returned results)
# - mismatch_reason: str (why KB is mismatched)
```

**Example**: 14 network articles retrieved but no "internet" subtype match
- Returns: `should_try_web_search=True, mismatch_reason="Found 14 network/connectivity articles but none match subtype 'internet' — articles cover: vpn-not-connecting, wifi-disconnecting"`

### 2. **ResolutionStrategySelector** (`resolution_strategy.py`)

Chooses which rendering approach based on situation:

- **GROUNDED_LLM**: High-quality natural response (exact KB match)
- **WEB_SEARCH**: External sources when KB is mismatched/empty
- **SIMPLIFIED**: Ultra-simple 1-step guidance (if user confused)
- **ESCALATE**: Human handoff (when nothing works)

No more forcing mismatched KB steps through LLM.

### 3. **Enhanced Resolution Node**

Now checks quality gate before rendering:

```python
# Agent collaboration checkpoint
quality = RetrievalQualityAnalyzer(knowledge_results, diag_ctx).analyze()

if quality.should_try_web_search and knowledge_results:
    # KB articles are mismatched → try web search instead
    web_results = await web_search(...)
    if web_results:
        return web_response  # Success!
    else:
        # Web search also failed → escalate with context
        return escalation_with_mismatch_context()

elif quality.is_relevant:
    # KB articles match → use grounded LLM rendering
    return await llm_render_steps(kb_articles)
```

---

## Benefits

| Aspect | Old | New |
|--------|-----|-----|
| **When KB has no articles** | Escalate immediately | Try web search first ✅ |
| **When KB has wrong articles** | Force through LLM, template fallback | Detect mismatch → try web search ✅ |
| **Agent communication** | None (rigid pipeline) | Rich context passing ✅ |
| **Handling confusion** | Escalate | Simplify first ✅ |
| **User experience** | Stiff templates | Natural responses ✅ |
| **Graceful degradation** | No strategy selection | Multiple fallback paths ✅ |

---

## Example Flows

### Flow 1: Exact Match (Best Case)
```
User: "can't receive emails"
Triage: subtype=not-receiving-emails
KB Search: Returns 3 articles with subcategory="not-receiving-emails"
Quality Check: ✅ Exact match (1 article)
Resolution: → GROUNDED_LLM → Natural response
```

### Flow 2: Mismatch Detection (New Intelligence)
```
User: "can't connect to internet"
Triage: subtype=internet
KB Search: Returns 14 articles (vpn-not-connecting, wifi-disconnecting, etc.)
Quality Check: ⚠️ No internet subtype match → should_try_web_search=True
Web Search: Finds good external guides on internet connectivity troubleshooting
Resolution: → WEB_SEARCH → "I found some helpful external resources..."
```

### Flow 3: Mismatch + Web Failure (Graceful Degradation)
```
User: "weird network issue" (vague)
Triage: subtype=None (unclear)
KB Search: Returns articles but low relevance score
Quality Check: ❌ Mismatch detected
Web Search: No results for vague query
Escalation: "I couldn't find a match in our guides. Let me connect you with our IT team..."
  (+ passes mismatch_reason to IT for context)
```

---

## Integration

All new components are imported in `resolution.py`:

```python
from app.services.agents.retrieval_quality import RetrievalQualityAnalyzer
from app.services.agents.resolution_strategy import ResolutionStrategySelector

# Check KB quality at the gate
quality = RetrievalQualityAnalyzer(knowledge_results, diag_ctx).analyze()

# Choose appropriate strategy
strategy = ResolutionStrategySelector(
    kb_articles=knowledge_results,
    subtype_match_count=quality.matched_subtype_count,
    has_failed_steps=bool(diag_ctx.failed_steps),
    diag_ctx=diag_ctx,
).select()
```

---

## Testing These Flows

After rebuild, test:

1. **Exact match**: "I can't receive emails" → Should get grounded LLM response
2. **Mismatch (new)**: "I can't connect to internet" → Should get web search results or escalation
3. **Mismatch recovery**: "My Wi-Fi is acting weird" → Should try web search if KB is uncertain
4. **Graceful escalation**: Vague issue → Should escalate with context about why

All use natural language, not templates. ✅
