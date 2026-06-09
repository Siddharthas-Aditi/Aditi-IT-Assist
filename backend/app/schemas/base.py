"""Shared base schemas and utilities."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(from_attributes=True)


class TimestampMixin(BaseModel):
    """Mixin adding created_at/updated_at fields."""

    created_at: datetime
    updated_at: datetime | None = None


class IDMixin(BaseModel):
    """Mixin adding UUID id field."""

    id: UUID
