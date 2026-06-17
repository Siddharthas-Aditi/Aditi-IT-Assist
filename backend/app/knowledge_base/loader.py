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

    Production: replaced by pgvector semantic search.
    """
    knowledge = load_all_knowledge()
    results = []
    query_lower = query.lower()

    for _category, articles in knowledge.items():
        for article in articles:
            # Simple keyword matching
            title = article.get("title", "").lower()
            content = article.get("content", "").lower()
            tags = " ".join(article.get("tags", [])).lower()

            if query_lower in title or query_lower in content or query_lower in tags:
                results.append(article)

    return results[:limit]
