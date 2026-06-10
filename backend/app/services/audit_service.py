"""Audit service — enterprise governance event logging."""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.auth import User

logger = structlog.get_logger()


class AuditService:
    """Records immutable audit events for compliance and security monitoring."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        action: str,
        resource_type: str,
        *,
        actor: User | None = None,
        resource_id: str | None = None,
        description: str | None = None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        session_id: uuid.UUID | None = None,
        severity: str = "info",
        metadata: dict | None = None,
    ) -> AuditEvent:
        """Record an audit event."""
        event = AuditEvent(
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            actor_role=actor.primary_role if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            old_value=self._sanitize_payload(old_value),
            new_value=self._sanitize_payload(new_value),
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            severity=severity,
            metadata_json=metadata,
        )
        self.db.add(event)

        logger.info(
            "audit_event",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_email=actor.email if actor else "system",
            severity=severity,
        )

        return event

    @staticmethod
    def _sanitize_payload(payload: dict | None) -> dict | None:
        """Remove sensitive fields from audit payloads."""
        if not payload:
            return None
        sensitive_keys = {"password", "hashed_password", "secret", "token", "api_key"}
        return {
            k: "***REDACTED***" if k.lower() in sensitive_keys else v
            for k, v in payload.items()
        }
