"""Unit tests for FeedbackService business logic.

Tests cover:
- submit_feedback creates new record for own session
- submit_feedback updates existing record (idempotent)
- review_flag set when rating ≤ 2
- review_flag set when resolved=False
- quality_bucket POSITIVE when helpful+resolved+rating≥4
- quality_bucket NEGATIVE on low rating alone
- support_mode mapped from session_type
- PermissionError raised for wrong user
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.feedback import ConversationFeedback, QualityBucket, SupportMode
from app.schemas.feedback import ConversationFeedbackCreate
from app.services.feedback_service import (
    FeedbackService,
    _compute_quality_bucket,
    _compute_review_flag,
    _SESSION_TYPE_MAP,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def make_session(
    user_id: uuid.UUID,
    session_type: str = "ai_chat",
    status: str = "resolved",
    assigned_agent_id: uuid.UUID | None = None,
    issue_category: str | None = "email/outlook",
    issue_subcategory: str | None = "delivery",
    resolved_at: datetime | None = None,
    created_at: datetime | None = None,
    metadata_json: dict | None = None,
) -> MagicMock:
    session = MagicMock()
    session.id = uuid.uuid4()
    session.user_id = user_id
    session.session_type = session_type
    session.status = status
    session.assigned_agent_id = assigned_agent_id
    session.issue_category = issue_category
    session.issue_subcategory = issue_subcategory
    session.resolved_at = resolved_at or datetime.now(timezone.utc)
    session.created_at = created_at or datetime.now(timezone.utc)
    session.metadata_json = metadata_json or {}
    return session


def make_service(
    db_session: MagicMock | None = None,
    existing_feedback: ConversationFeedback | None = None,
    support_session: MagicMock | None = None,
) -> FeedbackService:
    db = db_session or AsyncMock()
    service = FeedbackService(db)
    # Patch the repo
    service.repo = AsyncMock()
    service.repo.get_by_conversation_and_user = AsyncMock(return_value=existing_feedback)
    service.repo.create = AsyncMock(side_effect=lambda fb: fb)
    service.repo.update = AsyncMock(side_effect=lambda fb, upd: fb)
    return service


# ─── Pure function tests (no DB needed) ───────────────────────────────────────


class TestComputeQualityBucket:
    def test_all_positive(self):
        assert _compute_quality_bucket(True, True, 5) == QualityBucket.POSITIVE

    def test_positive_no_rating(self):
        assert _compute_quality_bucket(True, True, None) == QualityBucket.POSITIVE

    def test_negative_rating_alone(self):
        assert _compute_quality_bucket(None, None, 1) == QualityBucket.NEGATIVE

    def test_negative_helpful_false(self):
        assert _compute_quality_bucket(False, True, 5) == QualityBucket.NEGATIVE

    def test_negative_resolved_false(self):
        assert _compute_quality_bucket(True, False, 4) == QualityBucket.NEGATIVE

    def test_neutral_mixed(self):
        # helpful=True but resolved=False → NEGATIVE (any negative pulls down)
        assert _compute_quality_bucket(True, False, None) == QualityBucket.NEGATIVE

    def test_all_none_is_neutral(self):
        assert _compute_quality_bucket(None, None, None) == QualityBucket.NEUTRAL


class TestComputeReviewFlag:
    def test_no_flag_for_positive(self):
        flagged, reason = _compute_review_flag(True, True, 5)
        assert not flagged
        assert reason is None

    def test_flag_low_rating(self):
        flagged, reason = _compute_review_flag(None, None, 2)
        assert flagged
        assert "low rating" in reason

    def test_flag_rating_1(self):
        flagged, reason = _compute_review_flag(None, None, 1)
        assert flagged

    def test_flag_not_helpful(self):
        flagged, reason = _compute_review_flag(False, True, 4)
        assert flagged
        assert "not helpful" in reason

    def test_flag_unresolved(self):
        flagged, reason = _compute_review_flag(True, False, 5)
        assert flagged
        assert "unresolved" in reason

    def test_flag_multiple_reasons(self):
        flagged, reason = _compute_review_flag(False, False, 1)
        assert flagged
        assert "not helpful" in reason
        assert "unresolved" in reason
        assert "low rating" in reason

    def test_no_flag_rating_3(self):
        # rating=3 is NOT below threshold (threshold is ≤2)
        flagged, _ = _compute_review_flag(None, None, 3)
        assert not flagged


class TestSessionTypeMapping:
    def test_ai_chat_maps_to_ai_only(self):
        assert _SESSION_TYPE_MAP["ai_chat"] == SupportMode.AI_ONLY

    def test_live_support_maps_to_live_agent_only(self):
        assert _SESSION_TYPE_MAP["live_support"] == SupportMode.LIVE_AGENT_ONLY

    def test_hybrid_maps_to_ai_plus_live(self):
        assert _SESSION_TYPE_MAP["hybrid"] == SupportMode.AI_PLUS_LIVE_AGENT


# ─── Service integration tests (mocked DB) ────────────────────────────────────


class TestFeedbackServiceSubmit:
    @pytest.mark.asyncio
    async def test_creates_new_record_for_own_session(self):
        user_id = uuid.uuid4()
        session = make_session(user_id=user_id)
        service = make_service(support_session=session)

        # Patch the DB query for SupportSession
        from sqlalchemy import select as sa_select
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        service.db.execute = AsyncMock(return_value=mock_result)

        async def capture_and_fill(fb):
            # Simulate what SQLAlchemy does on INSERT
            fb.id = uuid.uuid4()
            fb.created_at = datetime.now(timezone.utc)
            fb.updated_at = datetime.now(timezone.utc)
            return fb

        service.repo.create = AsyncMock(side_effect=capture_and_fill)

        payload = ConversationFeedbackCreate(helpful=True, resolved=True, rating=5)
        result = await service.submit_feedback(
            session_id=str(session.id),
            user_id=str(user_id),
            payload=payload,
        )

        service.repo.create.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_permission_error_for_wrong_user(self):
        owner_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        session = make_session(user_id=owner_id)
        service = make_service(support_session=session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        service.db.execute = AsyncMock(return_value=mock_result)

        payload = ConversationFeedbackCreate(helpful=True)
        with pytest.raises(PermissionError):
            await service.submit_feedback(
                session_id=str(session.id),
                user_id=str(other_user_id),
                payload=payload,
            )

    @pytest.mark.asyncio
    async def test_not_found_raises_value_error(self):
        user_id = uuid.uuid4()
        session_id = str(uuid.uuid4())
        service = make_service()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        service.db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError):
            await service.submit_feedback(
                session_id=session_id,
                user_id=str(user_id),
                payload=ConversationFeedbackCreate(),
            )

    @pytest.mark.asyncio
    async def test_idempotent_update_when_record_exists(self):
        user_id = uuid.uuid4()
        session = make_session(user_id=user_id)
        existing = MagicMock(spec=ConversationFeedback)
        existing.id = uuid.uuid4()
        existing.conversation_id = session.id
        existing.submitted_by_user_id = user_id
        existing.helpful = False
        existing.resolved = None
        existing.rating = None
        existing.comment = None
        existing.support_mode = "ai_only"
        existing.escalation_occurred = False
        existing.category = "email/outlook"
        existing.subcategory = "delivery"
        existing.knowledge_article_ids = None
        existing.session_duration_seconds = None
        existing.first_response_time_seconds = None
        existing.quality_bucket = "negative"
        existing.review_flag = True
        existing.review_flag_reason = "not helpful"
        existing.ticket_id = None
        existing.channel = "web_chat"
        existing.feedback_source = "inline_chat"
        existing.agent_user_id = None
        existing.submitted_at = datetime.now(timezone.utc)
        existing.created_at = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)

        service = make_service(existing_feedback=existing, support_session=session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        service.db.execute = AsyncMock(return_value=mock_result)

        payload = ConversationFeedbackCreate(helpful=True, resolved=True, rating=5)
        await service.submit_feedback(
            session_id=str(session.id),
            user_id=str(user_id),
            payload=payload,
        )

        # update was called, not create
        service.repo.update.assert_awaited_once()
        service.repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_review_flag_set_on_low_rating(self):
        user_id = uuid.uuid4()
        session = make_session(user_id=user_id)
        created_records: list[ConversationFeedback] = []

        service = make_service(support_session=session)

        async def capture_create(fb):
            fb.id = uuid.uuid4()
            fb.created_at = datetime.now(timezone.utc)
            fb.updated_at = datetime.now(timezone.utc)
            created_records.append(fb)
            return fb

        service.repo.create = AsyncMock(side_effect=capture_create)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        service.db.execute = AsyncMock(return_value=mock_result)

        payload = ConversationFeedbackCreate(helpful=True, resolved=True, rating=1)
        await service.submit_feedback(
            session_id=str(session.id),
            user_id=str(user_id),
            payload=payload,
        )

        assert len(created_records) == 1
        assert created_records[0].review_flag is True

    @pytest.mark.asyncio
    async def test_review_flag_set_on_unresolved(self):
        user_id = uuid.uuid4()
        session = make_session(user_id=user_id)
        created_records: list[ConversationFeedback] = []

        service = make_service(support_session=session)

        async def capture_create(fb):
            fb.id = uuid.uuid4()
            fb.created_at = datetime.now(timezone.utc)
            fb.updated_at = datetime.now(timezone.utc)
            created_records.append(fb)
            return fb

        service.repo.create = AsyncMock(side_effect=capture_create)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        service.db.execute = AsyncMock(return_value=mock_result)

        payload = ConversationFeedbackCreate(helpful=True, resolved=False)
        await service.submit_feedback(
            session_id=str(session.id),
            user_id=str(user_id),
            payload=payload,
        )

        assert created_records[0].review_flag is True
        assert "unresolved" in (created_records[0].review_flag_reason or "")

    @pytest.mark.asyncio
    async def test_support_mode_inferred_from_session_type(self):
        user_id = uuid.uuid4()
        session = make_session(user_id=user_id, session_type="hybrid")
        created_records: list[ConversationFeedback] = []

        service = make_service(support_session=session)

        async def capture_create(fb):
            fb.id = uuid.uuid4()
            fb.created_at = datetime.now(timezone.utc)
            fb.updated_at = datetime.now(timezone.utc)
            created_records.append(fb)
            return fb

        service.repo.create = AsyncMock(side_effect=capture_create)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        service.db.execute = AsyncMock(return_value=mock_result)

        await service.submit_feedback(
            session_id=str(session.id),
            user_id=str(user_id),
            payload=ConversationFeedbackCreate(helpful=True),
        )

        assert created_records[0].support_mode == SupportMode.AI_PLUS_LIVE_AGENT.value

    @pytest.mark.asyncio
    async def test_knowledge_article_ids_pulled_from_session_metadata(self):
        user_id = uuid.uuid4()
        article_ids = ["art-1", "art-2"]
        session = make_session(
            user_id=user_id,
            metadata_json={"knowledge_article_ids": article_ids},
        )
        created_records: list[ConversationFeedback] = []
        service = make_service(support_session=session)

        async def capture_create(fb):
            fb.id = uuid.uuid4()
            fb.created_at = datetime.now(timezone.utc)
            fb.updated_at = datetime.now(timezone.utc)
            created_records.append(fb)
            return fb

        service.repo.create = AsyncMock(side_effect=capture_create)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        service.db.execute = AsyncMock(return_value=mock_result)

        await service.submit_feedback(
            session_id=str(session.id),
            user_id=str(user_id),
            payload=ConversationFeedbackCreate(helpful=True),
        )

        assert created_records[0].knowledge_article_ids == article_ids
