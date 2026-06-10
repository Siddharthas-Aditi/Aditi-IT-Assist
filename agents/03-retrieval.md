# Agent 03: Knowledge Retrieval

> **One-liner**: Searches the knowledge base for relevant troubleshooting
> articles using vector similarity and keyword fallback.

---

## Role

The Retrieval Agent takes the classified issue and searches for relevant
knowledge base articles. It does NOT synthesize or advise — it simply
returns ranked results with confidence scores.

---

## Interface

| Direction | Type | Description |
|-----------|------|-------------|
| **Input** | `issue_category: str` | From Triage Agent |
| **Input** | `issue_subcategory: str` | From Triage Agent |
| **Input** | `messages: list[BaseMessage]` | User's description for embedding |
| **Output** | `knowledge_results: list[dict]` | Ranked articles |
| **Output** | `knowledge_confidence: float` | Best match score (0.0-1.0) |

---

## Algorithm

```python
async def retrieval_node(state: WorkflowState) -> dict:
    """Search knowledge base for relevant articles."""
    logger.info("retrieval.start", category=state.get("issue_category"))

    user_description = extract_user_description(state["messages"])
    category = state.get("issue_category", "other")

    # Step 1: Vector similarity search
    vector_results = await vector_search(
        query=f"{category}: {user_description}",
        top_k=5,
        min_score=0.5,
    )

    # Step 2: Keyword fallback (if vector results insufficient)
    if len(vector_results) < 3:
        keyword_results = await keyword_search(
            query=user_description,
            category_filter=category,
            limit=5,
        )
    else:
        keyword_results = []

    # Step 3: Merge and deduplicate
    merged = merge_results(vector_results, keyword_results)

    # Step 4: Calculate confidence
    confidence = merged[0].score if merged else 0.0

    return {
        "knowledge_results": [r.to_dict() for r in merged[:5]],
        "knowledge_confidence": confidence,
        "current_node": "retrieval",
        "audit_trail": [{
            "event": "retrieval.complete",
            "results_count": len(merged),
            "confidence": confidence,
            "search_strategy": "vector" if vector_results else "keyword",
        }],
    }
```

---

## Search Strategy

### 1. Vector Search (Primary)

```sql
SELECT id, title, content, category,
       1 - (embedding <=> $query_embedding) AS similarity
FROM knowledge_articles
WHERE category = $category OR $category IS NULL
ORDER BY embedding <=> $query_embedding
LIMIT 5;
```

- Uses pgvector cosine similarity
- Embedding model: `text-embedding-3-small` (via LiteLLM)
- Minimum threshold: 0.5 (below this, result is discarded)

### 2. Keyword Search (Fallback)

```sql
SELECT id, title, content, category,
       ts_rank(search_vector, plainto_tsquery($query)) AS rank
FROM knowledge_articles
WHERE search_vector @@ plainto_tsquery($query)
  AND ($category IS NULL OR category = $category)
ORDER BY rank DESC
LIMIT 5;
```

- PostgreSQL full-text search
- Activated when vector search returns < 3 results
- Also used when embedding model is unavailable

### 3. Score Combination

```python
def merge_results(vector_results, keyword_results):
    """Combine vector and keyword results with deduplication."""
    seen_ids = set()
    merged = []

    for r in vector_results:
        seen_ids.add(r.id)
        merged.append(ScoredResult(
            article=r,
            score=0.7 * r.similarity + 0.3 * get_keyword_score(r, keyword_results),
        ))

    for r in keyword_results:
        if r.id not in seen_ids:
            merged.append(ScoredResult(article=r, score=0.3 * r.rank))

    return sorted(merged, key=lambda x: x.score, reverse=True)
```

---

## Output Schema

```python
{
    "knowledge_results": [
        {
            "article_id": "550e8400-e29b-41d4-a716-446655440000",
            "title": "Outlook Not Receiving Emails - Troubleshooting Guide",
            "content": "## Steps\n1. Check junk folder\n2. Verify rules...",
            "category": "email/outlook",
            "subcategory": "email-delivery",
            "relevance_score": 0.92,
            "source": "vector_search",  # or "keyword_search" or "combined"
        }
    ],
    "knowledge_confidence": 0.92,  # Score of top result
}
```

---

## Failure Modes

| Failure | Detection | Recovery | Impact |
|---------|-----------|----------|--------|
| pgvector unavailable | `ConnectionError` on DB | Keyword-only search | Reduced accuracy |
| Embedding model down | Exception in embed call | Category filter + keyword | Reduced accuracy |
| No results at all | `len(results) == 0` | Set confidence=0.0, let Orchestrator escalate | User escalated |
| All results below threshold | Best score < 0.5 | Return results anyway with low confidence | Resolution may skip |
| Database timeout | Query > 5s | Return empty, set confidence=0.0 | Escalation triggered |
| Embedding dimension mismatch | Insert/query error | Recompute embedding | Brief delay |

---

## Boundaries

- ❌ Must NOT generate advice or synthesis
- ❌ Must NOT modify the knowledge base
- ❌ Must NOT call LLM for answer generation
- ❌ Must NOT filter results based on user role
- ✅ Returns raw articles ranked by relevance
- ✅ Must always set `knowledge_confidence`
- ✅ Must handle empty results gracefully
- ✅ Must log search strategy and result count

---

## Testing Checklist

- [ ] Returns relevant articles for known categories
- [ ] Falls back to keyword search when vector unavailable
- [ ] Correctly deduplicates combined results
- [ ] Sets confidence to 0.0 when no results found
- [ ] Respects minimum score threshold (0.5)
- [ ] Handles database connection errors gracefully
- [ ] Audit trail entry includes result metadata

---

## Dependencies

| Dependency | Purpose | Fallback |
|------------|---------|----------|
| PostgreSQL + pgvector | Vector similarity search | Keyword search only |
| LiteLLM (embedding) | Generate query embedding | Category filter search |
| Knowledge base tables | Source of articles | — (none; empty results) |

---

## Implementation File

`backend/app/workflows/nodes/retrieval.py`
