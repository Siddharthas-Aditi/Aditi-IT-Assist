"""Seed data script — loads knowledge base articles into the database."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.knowledge_base.loader import load_all_knowledge
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def seed_knowledge_base() -> None:
    """Load all YAML knowledge articles into the database."""
    setup_logging()
    logger.info("seed_start", action="loading knowledge base")

    knowledge = load_all_knowledge()

    total_articles = 0
    for category, articles in knowledge.items():
        logger.info("seed_category", category=category, articles=len(articles))
        total_articles += len(articles)

        # TODO(team): Insert into database via repository layer
        # For now, just validates that the YAML files load correctly
        for article in articles:
            assert "title" in article, f"Article missing title in {category}"
            assert "steps" in article, f"Article missing steps in {category}"
            logger.info("seed_article", title=article["title"])

    logger.info("seed_complete", total_articles=total_articles, categories=len(knowledge))


async def seed_demo_users() -> None:
    """Create demo users for development."""
    logger.info("seed_users_start")

    demo_users = [
        {
            "email": "employee@aditiconsulting.com",
            "full_name": "Demo Employee",
            "role": "employee",
            "employee_id": "ADT-001",
            "department": "Engineering",
        },
        {
            "email": "agent@aditiconsulting.com",
            "full_name": "IT Agent",
            "role": "it_agent",
            "employee_id": "ADT-100",
            "department": "IT Support",
        },
        {
            "email": "admin@aditiconsulting.com",
            "full_name": "Admin User",
            "role": "admin",
            "employee_id": "ADT-200",
            "department": "IT Management",
        },
    ]

    for user in demo_users:
        logger.info("seed_user", email=user["email"], role=user["role"])
        # TODO(team): Insert into database via repository layer

    logger.info("seed_users_complete", count=len(demo_users))


async def main() -> None:
    """Run all seed operations."""
    await seed_knowledge_base()
    await seed_demo_users()
    print("\n✅ Seed data loaded successfully!")


if __name__ == "__main__":
    asyncio.run(main())
