"""Add embedding column to knowledge_chunks table.

Revision ID: 006_add_knowledge_chunks_embedding
Revises: 005_feedback
Create Date: 2026-06-17

Adds the pgvector embedding column to knowledge_chunks for vector similarity
search. This was missing from the initial schema but is used by the knowledge
retrieval and indexing services.
"""

from alembic import op

revision = "006_add_knowledge_chunks_embedding"
down_revision = "005_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add embedding column to knowledge_chunks."""
    # Add the pgvector column for embeddings (3072 dimensions for text-embedding-3-large)
    # Using raw SQL since SQLAlchemy doesn't have built-in support for pgvector type in migrations
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(3072) NULL")


def downgrade() -> None:
    """Remove embedding column from knowledge_chunks."""
    op.drop_column("knowledge_chunks", "embedding")
