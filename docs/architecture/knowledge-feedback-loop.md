# Knowledge Feedback Loop

Negative post-chat feedback is connected to the knowledge base to drive
continuous improvement of IT support article quality.

---

## 1. Connection Points

When a support session ends, the session's `metadata_json` may contain
`knowledge_article_ids` — the list of KB article UUIDs that the retrieval
agent surfaced.  These IDs are copied into `ConversationFeedback.knowledge_article_ids`
at survey submission time.

---

## 2. Article Flagging

`FeedbackAnalyticsService.flag_articles_for_review(article_ids, threshold=3)`
returns any article IDs where `negative_sessions ≥ threshold`.

The caller (admin background task or `KnowledgeLearningAgent`) is responsible
for writing a flag to the `KnowledgeArticle` record — this service is
read-only with respect to the KB.

**Threshold rationale:** 3 negative sessions before flagging avoids noise from
single unhelpful interactions while catching systemic issues.

---

## 3. Admin Review Flow

```
Negative feedback                 FeedbackAnalyticsService
collected for article  ────────>  .flag_articles_for_review()
                                         │
                                         ▼
                               KnowledgeArticle.quality_score
                               drops / flag added by admin task
                                         │
                                         ▼
                               Admin sees article in KB
                               review queue with feedback
                               comment snippets attached
```

---

## 4. Rules

- ❌ The pipeline **must never auto-edit or auto-unpublish** KB articles based
  on feedback alone.
- ❌ Employee comment text must not be exposed verbatim in public article history.
- ✅ Flagged articles surface in the knowledge admin dashboard.
- ✅ Admins see `flag_threshold_breached=True` from the analytics API.
- ✅ Article `quality_score` (on `KnowledgeArticle`) is updated by the
  `KnowledgeLearningAgent` after reviewing flagged signals.

---

## 5. API Endpoint

```
GET /api/v1/feedback/analytics/articles?article_ids=<uuid1>,<uuid2>
```

Returns `dict[article_id, ArticleFeedbackSummary]` with `flag_threshold_breached`.

**Required permission:** `feedback:view_analytics`
