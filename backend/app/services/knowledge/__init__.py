"""Knowledge management service package.

Service boundaries (intentionally separated for testability and scale):

- ``lifecycle``      — pure status-transition + validation rules (no I/O)
- ``normalization``  — article → retrieval text + semantic chunk preparation
- ``taxonomy``       — admin-managed taxonomy CRUD + classification validation
- ``indexing``       — chunk generation + (re)indexing pipeline orchestration
- ``management``     — authoring, lifecycle transitions, versioning, feedback
- ``retrieval``      — governed, published-only retrieval for the chat agent
- ``analytics``      — usage / effectiveness aggregation

The legacy ``app.services.knowledge_service`` (YAML keyword search) is retained
as the development retrieval fallback and is composed by ``retrieval`` here.
"""

from app.services.knowledge.lifecycle import (
    LIFECYCLE_ACTIONS,
    LifecycleError,
    can_perform,
    next_states,
    resolve_transition,
    validate_for_publish,
)

__all__ = [
    "LIFECYCLE_ACTIONS",
    "LifecycleError",
    "can_perform",
    "next_states",
    "resolve_transition",
    "validate_for_publish",
]
