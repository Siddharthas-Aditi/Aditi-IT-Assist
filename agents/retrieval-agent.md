# Retrieval Agent

## Role
Searches the knowledge base for relevant troubleshooting articles matching the user's issue.

## Inputs
- Issue classification (category, subcategory)
- User's issue description
- Conversation context

## Outputs
- `knowledge_results`: Ranked list of relevant articles
- `knowledge_confidence`: Float indicating result quality

## Strategy
1. Embed user query using embedding model
2. Search pgvector for similar articles
3. Apply category filter for precision
4. Rank by relevance score
5. Return top N results

## Implementation
- File: `backend/app/workflows/nodes/retrieval.py`
- Uses pgvector for vector similarity search
- Falls back to category-based lookup in development

## Boundaries
- Returns information ONLY — does not synthesize or advise
- Does not make LLM calls
- Must handle empty results gracefully
- Must report confidence honestly (0 if no results)
