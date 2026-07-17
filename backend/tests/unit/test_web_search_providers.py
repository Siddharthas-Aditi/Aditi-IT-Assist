"""B2: swappable web-search providers parse results and assess trust."""

import pytest

from app.services import web_search_service as W


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Minimal async-context httpx.AsyncClient stand-in."""

    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return _FakeResponse(self._payload)

    async def post(self, *a, **k):
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_google_provider_parses_and_assesses_trust(monkeypatch):
    payload = {
        "items": [
            {
                "title": "Fix keyboard",
                "link": "https://support.microsoft.com/kb/1",
                "snippet": "Try the on-screen keyboard.",
            },
            {"title": "Random blog", "link": "https://someblog.example.com/post", "snippet": "..."},
        ]
    }
    monkeypatch.setattr(W.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(payload))
    provider = W.GoogleProgrammableSearchProvider(api_key="k", cx="cx")
    results = await provider.search("keyboard not working", category="hardware", system="windows")
    assert results, "expected parsed results"
    assert results[0].trust_level == W.DomainTrust.OFFICIAL  # microsoft ranks first
    assert any(r.domain.endswith("microsoft.com") for r in results)


@pytest.mark.asyncio
async def test_google_provider_returns_empty_on_error(monkeypatch):
    class _Boom:
        def __init__(self, *a, **k): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(W.httpx, "AsyncClient", lambda *a, **k: _Boom())
    provider = W.GoogleProgrammableSearchProvider(api_key="k", cx="cx")
    assert await provider.search("q", category="c", system="s") == []


def test_factory_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(W.settings, "FEATURE_WEB_RESEARCH", False, raising=False)
    assert W.get_web_search_provider() is None
