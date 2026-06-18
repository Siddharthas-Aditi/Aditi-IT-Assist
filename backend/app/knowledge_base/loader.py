"""Knowledge base loader — loads YAML playbooks into searchable format."""

from pathlib import Path

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)

SEED_DIR = Path(__file__).parent / "seed"

# In-memory knowledge store (development fallback)
_knowledge_cache: dict[str, list[dict]] = {}


def load_all_knowledge() -> dict[str, list[dict]]:
    """Load all knowledge base YAML files from seed directory."""
    global _knowledge_cache

    if _knowledge_cache:
        return _knowledge_cache

    if not SEED_DIR.exists():
        logger.warning("knowledge_seed_dir_missing", path=str(SEED_DIR))
        return {}

    for yaml_file in SEED_DIR.glob("*.yml"):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            if data and "articles" in data:
                category = data.get("category", yaml_file.stem)
                # Merge articles if multiple YAML files share the same category
                if category not in _knowledge_cache:
                    _knowledge_cache[category] = []
                _knowledge_cache[category].extend(data["articles"])
                logger.info(
                    "knowledge_loaded",
                    file=yaml_file.name,
                    category=category,
                    articles=len(data["articles"]),
                    total_for_category=len(_knowledge_cache[category]),
                )
        except Exception as e:
            logger.error("knowledge_load_error", file=yaml_file.name, error=str(e))

    return _knowledge_cache


def get_articles_by_category(category: str) -> list[dict]:
    """Get knowledge articles for a specific issue category."""
    knowledge = load_all_knowledge()

    # Direct category match
    if category in knowledge:
        return knowledge[category]

    # Partial match (e.g., "email/outlook" matches "email")
    for key, articles in knowledge.items():
        if key in category or category in key:
            return articles

    return []


def search_articles(query: str, limit: int = 5) -> list[dict]:
    """Simple keyword search across all knowledge articles.

    Uses word-level matching so natural-language queries (e.g. "I have an
    Outlook email issue") correctly match article titles and content.
    Stops short words (≤ 2 chars) and common stop-words to reduce noise.

    Production: replaced by pgvector semantic search.
    """
    knowledge = load_all_knowledge()

    _STOPWORDS = frozenset(
        {"i", "a", "an", "the", "is", "am", "are", "was", "were", "be",
         "been", "being", "have", "has", "had", "do", "does", "did", "will",
         "would", "could", "should", "may", "might", "shall", "can", "need",
         "to", "of", "in", "on", "at", "by", "for", "with", "or", "and",
         "but", "not", "my", "me", "we", "you", "it", "its"}
    )

    # Split query into meaningful content words (>2 chars, not stop-words)
    query_words = [
        w for w in query.lower().split()
        if len(w) > 2 and w not in _STOPWORDS
    ]
    # Fall back to all non-trivially-short words if nothing survives
    if not query_words:
        query_words = [w for w in query.lower().split() if len(w) > 1]

    results: list[tuple[int, dict]] = []  # (score, article)

    for _category, articles in knowledge.items():
        for article in articles:
            title = article.get("title", "").lower()
            content = article.get("content", "").lower()
            tags = " ".join(article.get("tags", [])).lower()
            keywords = " ".join(article.get("keywords", [])).lower()
            haystack = f"{title} {tags} {keywords} {content}"

            # Count how many query words appear somewhere in the article
            score = sum(1 for w in query_words if w in haystack)
            if score > 0:
                results.append((score, article))

    # Return highest-scoring articles first
    results.sort(key=lambda x: x[0], reverse=True)
    return [art for _, art in results[:limit]]
