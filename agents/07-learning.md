# Agent 07: Knowledge Learning (Async)

> **One-liner**: Analyzes conversation patterns to identify knowledge gaps
> and suggest new articles for the knowledge base.

---

## Role

The Knowledge Learning Agent runs **asynchronously** (not in the real-time
conversation flow). It periodically analyzes completed sessions, identifies
patterns where the AI couldn't help, and generates suggestions for new
knowledge base articles.

---

## Interface

| Direction | Type | Description |
|-----------|------|-------------|
| **Input** | Session history (database) | Completed conversations |
| **Input** | Escalation records | Why things escalated |
| **Input** | User feedback | Thumbs up/down on resolutions |
| **Output** | Gap reports | Categories with poor coverage |
| **Output** | Article suggestions | Outlines for new KB articles |
| **Trigger** | Scheduled (daily cron) | Not real-time |

---

## Algorithm

```python
async def knowledge_learning_task():
    """Daily analysis of knowledge gaps."""
    logger.info("learning.start")

    # Step 1: Gather sessions from last 24h
    sessions = await get_recent_sessions(hours=24)

    # Step 2: Identify low-confidence sessions
    low_confidence = [s for s in sessions if s.resolution_confidence < 0.5]

    # Step 3: Cluster by category
    clusters = cluster_by_category(low_confidence)

    # Step 4: Identify categories with high escalation rates
    escalation_rates = calculate_escalation_rates(sessions)
    problem_categories = [
        cat for cat, rate in escalation_rates.items() if rate > 0.4
    ]

    # Step 5: Generate article suggestions via LLM
    for category in problem_categories:
        relevant_sessions = clusters.get(category, [])
        if len(relevant_sessions) >= 3:  # Minimum pattern threshold
            suggestion = await generate_article_outline(
                category=category,
                sample_issues=relevant_sessions[:5],
            )
            await submit_to_review_queue(suggestion)

    # Step 6: Generate gap report
    report = GapReport(
        period="24h",
        total_sessions=len(sessions),
        escalation_rate=sum(escalation_rates.values()) / len(escalation_rates),
        problem_categories=problem_categories,
        suggestions_generated=len(problem_categories),
    )
    await save_gap_report(report)

    logger.info("learning.complete", suggestions=len(problem_categories))
```

---

## Gap Detection Criteria

| Signal | Threshold | Action |
|--------|-----------|--------|
| Category escalation rate | > 40% | Flag for article creation |
| Zero knowledge results | > 3 sessions same category | High-priority gap |
| User thumbs-down | > 30% on a category | Review existing articles |
| Resolution confidence avg | < 0.5 for category | Knowledge quality issue |
| Repeated similar questions | > 5 same subcategory | Specific article needed |

---

## Article Suggestion Format

```python
ArticleSuggestion = {
    "title": str,                    # Suggested article title
    "category": str,                 # Target category
    "subcategory": str,              # Target subcategory
    "outline": list[str],            # Suggested sections
    "sample_issues": list[str],      # Example user messages that triggered this
    "rationale": str,                # Why this article is needed
    "priority": str,                 # high / medium / low
    "estimated_impact": str,         # "Would resolve ~15 sessions/week"
    "status": "pending_review",      # Always starts as pending
}
```

---

## Failure Modes

| Failure | Detection | Recovery | Impact |
|---------|-----------|----------|--------|
| No sessions in period | Empty query result | Skip analysis, log | No suggestions |
| LLM unavailable | Connection error | Template-based suggestions | Lower quality |
| Database unavailable | Connection error | Retry with backoff, alert | Delayed analysis |
| Too many suggestions | > 20 in one run | Cap at 10 highest priority | Manageable queue |

---

## Boundaries

- ❌ Must NOT run in real-time conversation flow
- ❌ Must NOT auto-publish articles (human review required)
- ❌ Must NOT delete existing articles
- ❌ Must NOT modify article content without review
- ✅ Runs on schedule (daily) or manual trigger
- ✅ All suggestions go to admin review queue
- ✅ Tracks metrics over time for trend analysis
- ✅ Respects minimum sample size (3 sessions) before suggesting

---

## Metrics Tracked

| Metric | Calculation | Purpose |
|--------|-------------|---------|
| Resolution rate by category | `resolved / total` per category | Find weak areas |
| Escalation rate by category | `escalated / total` per category | Priority gaps |
| Avg confidence by category | Mean `resolution_confidence` | Knowledge quality |
| Knowledge gap frequency | Sessions with 0 results | Coverage gaps |
| Article effectiveness | Confidence before/after article added | Impact measurement |

---

## Testing Checklist

- [ ] Correctly identifies low-confidence sessions
- [ ] Clusters sessions by category accurately
- [ ] Generates suggestions only when threshold met (3+ sessions)
- [ ] Handles empty session periods gracefully
- [ ] Cap on suggestions per run (≤ 10)
- [ ] Suggestions include rationale and sample issues
- [ ] Gap report contains accurate statistics

---

## Implementation File

`backend/app/tasks/knowledge_learning.py` (async task/cron)

---

## Schedule

- **Frequency**: Daily at 02:00 UTC
- **Runtime**: < 5 minutes typical
- **Trigger**: Also available via admin API endpoint for manual runs
