"""Enrichment job queue + results.

The two-level enrichment cache (search query + work-detail-by-MBID)
lives in a separate embedded SQLite at `${DATA_DIR}/enrichment-cache
.sqlite` per TRD §3.3 — that's not represented here. This table only
tracks job state and the selected candidate so the UI can ask
"what's the enrichment status of this arrangement?".
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from openclef.db import Base
from openclef.models._types import pg_enum, utcnow_aware
from openclef.models.enums import EnrichmentJobStatus


class EnrichmentJob(Base):
    __tablename__ = "enrichment_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    arrangement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("arrangements.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[EnrichmentJobStatus] = mapped_column(
        pg_enum(EnrichmentJobStatus, name="enrichment_job_status"),
        nullable=False,
        default=EnrichmentJobStatus.PENDING,
    )
    candidates_jsonb: Mapped[list | None] = mapped_column(JSONB(), nullable=True)
    selected_candidate_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    attempts: Mapped[int] = mapped_column(SmallInteger(), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=utcnow_aware(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_enrichment_jobs_arrangement_id", "arrangement_id"),
        # Composite index drives the worker's "next pending job" scan
        # and the UI's "recently failed" surfaces.
        Index("ix_enrichment_jobs_status_created_at", "status", "created_at"),
    )


__all__ = ["EnrichmentJob"]
