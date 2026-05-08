"""ORM model registry.

Importing this module ensures every model is attached to `Base.metadata`
so Alembic autogenerate sees the full schema. Add new model modules here
when they land.
"""
from __future__ import annotations

# Re-exports land as model modules are added in subsequent commits:
#   from openclef.models.user import User, UserSettings  # noqa: F401
#   from openclef.models.library import Arrangement, Part, Tag, ArrangementTag  # noqa: F401
#   from openclef.models.annotation import Annotation, AnnotationRevision  # noqa: F401
#   from openclef.models.setlist import Setlist, SetlistItem  # noqa: F401
#   from openclef.models.enrichment import EnrichmentJob  # noqa: F401
