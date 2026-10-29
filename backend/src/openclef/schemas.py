"""Pydantic v2 request/response schemas for the openclef Phase 1 API.

Per-entity Read / Create / Update where applicable. Read schemas use
`from_attributes=True` so they convert directly from ORM rows. Create
and Update schemas use `extra="forbid"` + `strict=True` so unknown or
loosely-typed fields fail loudly at the boundary.

Schema split convention: all schemas live in this single module for
Phase 1 since the surface is small (~20 classes). When the file grows
past ~400 lines, split per-entity to mirror the models/ layout.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from openclef.models.enums import (
    EditionType,
    EnrichmentJobStatus,
    KeySignature,
    PartType,
    Period,
    Theme,
    UserRole,
)


_READ_CONFIG = ConfigDict(from_attributes=True)
_WRITE_CONFIG = ConfigDict(extra="forbid", strict=True)


# --- User -------------------------------------------------------------


class UserRead(BaseModel):
    model_config = _READ_CONFIG

    id: uuid.UUID
    username: str
    email: str | None
    role: UserRole
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    model_config = _WRITE_CONFIG

    username: str = Field(min_length=1, max_length=64)
    email: str | None = None
    password_hash: str | None = None  # populated by auth code, not API clients
    oidc_sub: str | None = None
    role: UserRole = UserRole.USER


class UserUpdate(BaseModel):
    model_config = _WRITE_CONFIG

    email: str | None = None
    role: UserRole | None = None


# --- UserSettings -----------------------------------------------------


class UserSettingsRead(BaseModel):
    model_config = _READ_CONFIG

    user_id: uuid.UUID
    theme: Theme
    enrichment_default_enabled: bool
    enrichment_providers_jsonb: list[dict[str, Any]]
    preferences_jsonb: dict[str, Any]


class UserSettingsUpdate(BaseModel):
    model_config = _WRITE_CONFIG

    theme: Theme | None = None
    enrichment_default_enabled: bool | None = None
    enrichment_providers_jsonb: list[dict[str, Any]] | None = None
    preferences_jsonb: dict[str, Any] | None = None


# --- Arrangement ------------------------------------------------------


class ArrangementRead(BaseModel):
    model_config = _READ_CONFIG

    id: uuid.UUID
    title: str
    subtitle: str | None
    alternative_titles: list[str]
    composer: list[str]
    arranger: list[str]
    lyricist: list[str]
    instrumentation: list[str]
    key_signature: KeySignature | None
    opus_catalog_number: str | None
    period: Period | None
    difficulty: int | None
    edition_type: EditionType | None
    publisher: str | None
    publication_year: int | None
    composition_year: int | None
    language: list[str]
    duration_minutes: int | None
    notes: str | None
    description: str | None
    external_links_jsonb: list[dict[str, Any]] | None
    musicbrainz_work_id: uuid.UUID | None
    movements: list[dict[str, Any]] | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ArrangementCreate(BaseModel):
    model_config = _WRITE_CONFIG

    title: str = Field(min_length=1)
    subtitle: str | None = None
    alternative_titles: list[str] = Field(default_factory=list)
    composer: list[str] = Field(default_factory=list)
    arranger: list[str] = Field(default_factory=list)
    lyricist: list[str] = Field(default_factory=list)
    instrumentation: list[str] = Field(default_factory=list)
    key_signature: KeySignature | None = None
    opus_catalog_number: str | None = None
    period: Period | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    edition_type: EditionType | None = None
    publisher: str | None = None
    publication_year: int | None = None
    composition_year: int | None = None
    language: list[str] = Field(default_factory=list)
    duration_minutes: int | None = None
    notes: str | None = None
    description: str | None = None
    external_links_jsonb: list[dict[str, Any]] | None = None
    musicbrainz_work_id: uuid.UUID | None = None
    movements: list[dict[str, Any]] | None = None


class ArrangementUpdate(BaseModel):
    model_config = _WRITE_CONFIG

    title: str | None = Field(default=None, min_length=1)
    subtitle: str | None = None
    alternative_titles: list[str] | None = None
    composer: list[str] | None = None
    arranger: list[str] | None = None
    lyricist: list[str] | None = None
    instrumentation: list[str] | None = None
    key_signature: KeySignature | None = None
    opus_catalog_number: str | None = None
    period: Period | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    edition_type: EditionType | None = None
    publisher: str | None = None
    publication_year: int | None = None
    composition_year: int | None = None
    language: list[str] | None = None
    duration_minutes: int | None = None
    notes: str | None = None
    description: str | None = None
    external_links_jsonb: list[dict[str, Any]] | None = None
    musicbrainz_work_id: uuid.UUID | None = None
    movements: list[dict[str, Any]] | None = None


# --- Part -------------------------------------------------------------


class PartRead(BaseModel):
    model_config = _READ_CONFIG

    id: uuid.UUID
    arrangement_id: uuid.UUID
    part_type: PartType
    label: str
    instrument: str | None
    page_count: int
    file_size_bytes: int
    storage_key: str
    thumbnail_storage_key: str | None
    file_hash_sha256: str | None
    uploaded_by: uuid.UUID
    created_at: datetime


class PartCreate(BaseModel):
    model_config = _WRITE_CONFIG

    arrangement_id: uuid.UUID
    part_type: PartType
    label: str = Field(min_length=1)
    instrument: str | None = None
    page_count: int = Field(ge=1)
    file_size_bytes: int = Field(ge=0)
    storage_key: str
    thumbnail_storage_key: str | None = None
    file_hash_sha256: str | None = None


class ArrangementUploadMetadata(ArrangementCreate):
    """The `metadata` form field of an upload. Same fields as
    ArrangementCreate, but `title` may be omitted: it then falls back to
    the PDF's embedded Title, then to the file name."""

    title: str | None = Field(default=None, min_length=1)


class UploadResponse(BaseModel):
    arrangement: ArrangementRead
    part: PartRead
    enrichment_job_id: uuid.UUID | None = None


class ArrangementDetail(ArrangementRead):
    """One arrangement with its parts (upload order) and tag names."""

    parts: list[PartRead]
    tags: list[str]


class ArrangementSummary(BaseModel):
    """One library card: the searchable fields plus what the card shows."""

    id: uuid.UUID
    title: str
    subtitle: str | None
    composer: list[str]
    arranger: list[str]
    instrumentation: list[str]
    key_signature: KeySignature | None
    period: Period | None
    difficulty: int | None
    created_at: datetime
    part_count: int
    # First-uploaded part: its PDF opens from the card, its thumbnail is the cover.
    cover_part_id: uuid.UUID | None
    cover_thumbnail_ready: bool


class FacetCount(BaseModel):
    value: str
    count: int


class ArrangementList(BaseModel):
    items: list[ArrangementSummary]
    total: int
    page: int
    page_size: int
    # Each facet is counted with every OTHER active filter applied, so the
    # sidebar still shows the alternatives to a value already selected.
    facets: dict[str, list[FacetCount]]


# --- Tag --------------------------------------------------------------


class TagRead(BaseModel):
    model_config = _READ_CONFIG

    id: uuid.UUID
    name: str


class TagCreate(BaseModel):
    model_config = _WRITE_CONFIG

    name: str = Field(min_length=1, max_length=64)


# --- Annotation -------------------------------------------------------


class AnnotationRead(BaseModel):
    model_config = _READ_CONFIG

    id: uuid.UUID
    user_id: uuid.UUID
    part_id: uuid.UUID
    page_number: int
    current_revision_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AnnotationCreate(BaseModel):
    model_config = _WRITE_CONFIG

    part_id: uuid.UUID
    page_number: int = Field(ge=1)


class AnnotationRevisionRead(BaseModel):
    model_config = _READ_CONFIG

    id: uuid.UUID
    annotation_id: uuid.UUID
    parent_revision_id: uuid.UUID | None
    payload_jsonb: dict[str, Any]
    created_at: datetime
    created_session_id: str | None


class AnnotationRevisionCreate(BaseModel):
    model_config = _WRITE_CONFIG

    annotation_id: uuid.UUID
    parent_revision_id: uuid.UUID | None = None
    payload_jsonb: dict[str, Any]
    created_session_id: str | None = None


# --- Setlist ----------------------------------------------------------


class SetlistItemRead(BaseModel):
    model_config = _READ_CONFIG

    setlist_id: uuid.UUID
    position: int
    arrangement_id: uuid.UUID
    part_id: uuid.UUID | None


class SetlistItemCreate(BaseModel):
    model_config = _WRITE_CONFIG

    arrangement_id: uuid.UUID
    part_id: uuid.UUID | None = None
    position: int = Field(ge=0)


class SetlistRead(BaseModel):
    model_config = _READ_CONFIG

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SetlistCreate(BaseModel):
    model_config = _WRITE_CONFIG

    name: str = Field(min_length=1, max_length=200)


class SetlistUpdate(BaseModel):
    model_config = _WRITE_CONFIG

    name: str | None = Field(default=None, min_length=1, max_length=200)


# --- EnrichmentJob ----------------------------------------------------


class EnrichmentJobRead(BaseModel):
    model_config = _READ_CONFIG

    id: uuid.UUID
    arrangement_id: uuid.UUID
    status: EnrichmentJobStatus
    candidates_jsonb: list[dict[str, Any]] | None
    selected_candidate_id: str | None
    error_message: str | None
    attempts: int
    created_at: datetime
    completed_at: datetime | None
