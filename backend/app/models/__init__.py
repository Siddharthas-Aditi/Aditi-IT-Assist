"""Database models package — re-exports all models for Aditi IT Assist enterprise platform."""

from app.models.agent_action_ledger import AgentActionLedger
from app.models.analytics import AnalyticsSnapshot
from app.models.audit import AuditEvent
from app.models.auth import (
    AuthIdentity,
    Group,
    LoginSession,
    Permission,
    Role,
    RolePermission,
    User,
    UserGroup,
    UserRoleAssignment,
)
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.escalation import EscalationContext, TranscriptSnapshot
from app.models.feedback import ConversationFeedback, MessageFeedback
from app.models.ingestion import IngestionCandidate, IngestionJob
from app.models.knowledge import (
    KnowledgeArticle,
    KnowledgeArticleVersion,
    KnowledgeChunk,
    KnowledgeFeedback,
    KnowledgeOwnershipGroup,
    KnowledgeReviewNote,
    KnowledgeTaxonomyTerm,
)
from app.models.knowledge_candidate import KnowledgeCandidate
from app.models.live_handoff import LiveHandoffOffer, SpecialistAvailability
from app.models.pending_approval import PendingApprovalRecord
from app.models.remote_support import RemoteSessionEvent, RemoteSupportConsent, RemoteSupportSession
from app.models.reporting import ScheduledReportRun
from app.models.specialist_chat import SpecialistChatMessage, SpecialistChatSession
from app.models.sso import IdentityProviderConfig, IdPGroupRoleMapping, SPCertificate
from app.models.support import Message, SupportSession
from app.models.ticket import Ticket, TicketCategory, TicketComment, TicketEvent

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    # Auth & RBAC
    "User",
    "Role",
    "Permission",
    "RolePermission",
    "UserRoleAssignment",
    "Group",
    "UserGroup",
    "AuthIdentity",
    "LoginSession",
    # SSO / IdP
    "IdentityProviderConfig",
    "IdPGroupRoleMapping",
    "SPCertificate",
    # Support
    "SupportSession",
    "Message",
    # Tickets
    "Ticket",
    "TicketCategory",
    "TicketComment",
    "TicketEvent",
    # Chat-escalation artifacts
    "TranscriptSnapshot",
    "EscalationContext",
    # Feedback
    "ConversationFeedback",
    "MessageFeedback",
    # Knowledge
    "KnowledgeArticle",
    "KnowledgeArticleVersion",
    "KnowledgeChunk",
    "KnowledgeTaxonomyTerm",
    "KnowledgeOwnershipGroup",
    "KnowledgeFeedback",
    "KnowledgeReviewNote",
    "KnowledgeCandidate",
    # Live IT-Specialist Chat
    "SpecialistChatSession",
    "SpecialistChatMessage",
    # Remote Support
    "RemoteSupportSession",
    "RemoteSupportConsent",
    "RemoteSessionEvent",
    # Live Handoff
    "SpecialistAvailability",
    "LiveHandoffOffer",
    # Scheduled reporting
    "ScheduledReportRun",
    # Audit & Analytics
    "AuditEvent",
    "AnalyticsSnapshot",
    # Document Ingestion
    "IngestionJob",
    "IngestionCandidate",
]
