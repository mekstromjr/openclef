"""ORM model registry.

Importing this module ensures every model is attached to `Base.metadata`
so Alembic autogenerate sees the full schema. Add new model modules here
when they land.
"""
from __future__ import annotations

from openclef.models.annotation import Annotation, AnnotationRevision  # noqa: F401
from openclef.models.enrichment import EnrichmentJob  # noqa: F401
from openclef.models.library import Arrangement, ArrangementTag, Part, Tag  # noqa: F401
from openclef.models.setlist import Setlist, SetlistItem  # noqa: F401
from openclef.models.user import User, UserSettings  # noqa: F401

__all__ = [
    "Annotation",
    "AnnotationRevision",
    "Arrangement",
    "ArrangementTag",
    "EnrichmentJob",
    "Part",
    "Setlist",
    "SetlistItem",
    "Tag",
    "User",
    "UserSettings",
]
