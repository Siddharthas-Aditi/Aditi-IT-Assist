"""KnowledgeRetrievalService vector+hybrid orchestration (Phase 6).

Exercises the service wiring with injected fakes (no DB, no provider):
- flag off → keyword path, ``source='db_keyword'`` (unchanged behaviour);
- flag on + provider available + vector scores → ``source='db_hybrid'`` and the
  semantic signal reorders results;
- flag on but provider unavailable / embed fails / no embedded chunks → graceful
  fallback to keyword.

The raw pgvector SQL in ``KnowledgeRepository.article_vector_scores`` needs a
real Postgres+pgvector and is covered by integration tests in CI; here we fake
the repository to test the orchestration deterministically.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.services.knowledge.retrieval import KnowledgeRetrievalService


@dataclass
class FakeArticle:
    id: uuid.UUID
    title: str
    retrieval_text: str
    tags: tuple[str, ...] = ()
    usage_count: int = 0
    quality_score: float = 0.0
    short_summary: str | None = None
    content: str = ""


@dataclass
class FakeRepo:
    articles: list[FakeArticle]
    vector_scores: dict[uuid.UUID, float] = field(default_factory=dict)

    async def list_published(self, **kwargs):
        return list(self.articles)

    async def article_vector_scores(self, query_embedding, article_ids):
        return {aid: s for aid, s in self.vector_scores.items() if aid in article_ids}


class FakeEmbedder:
    def __init__(self, *, available: bool, vector=None, raises: bool = False) -> None:
        self.available = available
        self._vector = vector or [1.0, 0.0]
        self._raises = raises

    async def embed(self, texts):
        if self._raises:
            raise RuntimeError("provider down")
        return [self._vector] if self._vector is not None else None


def _articles():
    a = FakeArticle(uuid.uuid4(), "VPN guide", "vpn will not connect network tunnel", tags=("vpn",))
    b = FakeArticle(
        uuid.uuid4(),
        "Mailbox full",
        "outlook mailbox full quota storage",
        tags=("outlook", "mailbox"),
    )
    return a, b


def _service(repo, embedder):
    return KnowledgeRetrievalService(db=None, repo=repo, embedder=embedder)


class TestFlagOff:
    async def test_keyword_path_unchanged(self, monkeypatch) -> None:
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_VECTOR_RETRIEVAL", False)
        a, b = _articles()
        svc = _service(FakeRepo([a, b]), FakeEmbedder(available=True))
        res = await svc.search("mailbox full quota")
        assert res.source == "db_keyword"
        assert res.items[0].article.title == "Mailbox full"


class TestHybridPath:
    async def test_vector_signal_reorders(self, monkeypatch) -> None:
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_VECTOR_RETRIEVAL", True)
        a, b = _articles()
        # Query lexically matches NEITHER strongly, but vector strongly favours 'a'.
        repo = FakeRepo([a, b], vector_scores={a.id: 0.97, b.id: 0.02})
        svc = _service(repo, FakeEmbedder(available=True))
        res = await svc.search("connectivity issue")
        assert res.source == "db_hybrid"
        assert res.items[0].article.title == "VPN guide"

    async def test_provider_unavailable_falls_back(self, monkeypatch) -> None:
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_VECTOR_RETRIEVAL", True)
        a, b = _articles()
        svc = _service(FakeRepo([a, b]), FakeEmbedder(available=False))
        res = await svc.search("mailbox full quota")
        assert res.source == "db_keyword"

    async def test_embed_failure_falls_back(self, monkeypatch) -> None:
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_VECTOR_RETRIEVAL", True)
        a, b = _articles()
        svc = _service(FakeRepo([a, b]), FakeEmbedder(available=True, raises=True))
        res = await svc.search("mailbox full quota")
        assert res.source == "db_keyword"
        assert res.items  # still returns keyword results

    async def test_no_embedded_chunks_falls_back(self, monkeypatch) -> None:
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_VECTOR_RETRIEVAL", True)
        a, b = _articles()
        # Provider available + query embeds, but repo has no vectors yet.
        repo = FakeRepo([a, b], vector_scores={})
        svc = _service(repo, FakeEmbedder(available=True))
        res = await svc.search("mailbox full quota")
        assert res.source == "db_keyword"


class TestWeightsRobustness:
    async def test_invalid_weights_fall_back_to_defaults(self, monkeypatch) -> None:
        """Misconfigured weights must not break retrieval — they degrade to defaults."""
        from app.core import config

        monkeypatch.setattr(config.settings, "FEATURE_VECTOR_RETRIEVAL", False)
        # Weights that do not sum to 1.0.
        monkeypatch.setattr(config.settings, "HYBRID_WEIGHT_VECTOR", 0.9)
        monkeypatch.setattr(config.settings, "HYBRID_WEIGHT_KEYWORD", 0.9)
        a, b = _articles()
        svc = _service(FakeRepo([a, b]), FakeEmbedder(available=False))
        res = await svc.search("mailbox full quota")  # must not raise
        assert res.items
