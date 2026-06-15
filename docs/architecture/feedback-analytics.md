# Feedback Analytics

`FeedbackAnalyticsService` (`services/feedback_analytics_service.py`) aggregates
survey data for IT dashboards and the knowledge improvement loop.

---

## 1. Global Summary (`/feedback/analytics/summary`)

Computed over a configurable time window, with optional `category` and
`support_mode` filters.

| Metric | Description |
|--------|-------------|
| `total_submissions` | Number of submitted surveys |
| `helpful_rate` | % sessions rated helpful (excludes None) |
| `resolved_rate` | % sessions rated resolved (excludes None) |
| `csat_avg` | Average 1–5 star rating (excludes None) |
| `ai_only_count` / etc. | Session count by support mode |
| `ai_only_helpful_rate` | Helpful rate restricted to AI-only sessions |
| `live_agent_helpful_rate` | Helpful rate for live-agent sessions |
| `positive_count` / `neutral_count` / `negative_count` | Quality bucket distribution |
| `escalation_rate` | % sessions with escalation |
| `escalated_resolved_rate` | % escalated sessions rated resolved |
| `category_breakdown` | Top 10 categories by submission count |
| `flagged_count` | Pending review queue size |

**Required permission:** `feedback:view_analytics` (granted to `it_lead`, `it_admin`)

---

## 2. Article Health (`/feedback/analytics/articles`)

Accepts a list of article UUIDs and returns per-article signals.

| Metric | Description |
|--------|-------------|
| `total_sessions_used` | Sessions that cited the article |
| `positive_sessions` / `negative_sessions` | Quality bucket breakdown |
| `avg_rating` | Average star rating for sessions citing the article |
| `helpful_rate` / `resolved_rate` | Survey signal rates |
| `flag_count` | # review-flagged sessions citing the article |
| `flag_threshold_breached` | True when `negative_sessions ≥ 3` |

Used by the **Knowledge Improvement Loop** — see `knowledge-feedback-loop.md`.

---

## 3. Agent Summary (`/feedback/analytics/agents/{agent_id}`)

Feedback signals for a specific live IT agent:
`helpful_rate`, `resolved_rate`, `csat_avg`, `positive_count`, `negative_count`.

---

## 4. Computation Notes

- All rates are computed at query time (no pre-aggregated columns) to stay
  accurate in real time.
- `_safe_rate(n, d)` returns `None` when denominator is zero (avoids division errors).
- `_safe_avg([...])` returns `None` for empty lists.
- Future: cache summaries using `AnalyticsSnapshot` for high-traffic dashboards.

---

## 5. Permissions

| Permission | Holder |
|------------|--------|
| `feedback:submit` | employee+ |
| `feedback:view_own` | employee+ |
| `feedback:view_analytics` | it_lead, it_admin |
| `feedback:review` | it_lead, it_admin |
