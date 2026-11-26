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
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, StringConstraints, Tag

from openclef.models.enums import (
    EditionType,
    EnrichmentJobStatus,
    KeySignature,
    PartType,
    Period,
    SharePermission,
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
    # The SSO subject itself stays server-side; the UI only needs to know.
    sso_linked: bool = False
    has_password: bool = True


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
    owner_id: uuid.UUID
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
    # Setlists this piece is on. Deleting it leaves a "deleted" entry there.
    setlists: list["SetlistRef"] = []
    # Setlists the viewer can't see that still hold the piece, so the delete
    # confirmation can count them. A count only: names would leak (openclef#62).
    hidden_setlist_count: int = 0
    owner_username: str | None = None
    # Groups the piece is shared with. Filled for its owner only: anyone
    # else would learn about groups they aren't in (openclef#63).
    groups: list["GroupRef"] = []


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
    # Whose library the piece is in: drives the "Shared by" icon.
    owner_id: uuid.UUID
    owner_username: str


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


# Request bodies arrive as JSON, where ids and timestamps are strings.
# Strict mode would refuse that conversion, so these fields opt out of it.
_JsonUuid = Annotated[uuid.UUID, Field(strict=False)]
_JsonDatetime = Annotated[datetime, Field(strict=False)]

SETLIST_MAX_ITEMS = 200


class SetlistCreate(BaseModel):
    model_config = _WRITE_CONFIG

    name: str = Field(min_length=1, max_length=200)


class SetlistUpdate(BaseModel):
    model_config = _WRITE_CONFIG

    name: str = Field(min_length=1, max_length=200)
    # Optimistic concurrency: the `updated_at` the client loaded. A stale
    # value gets 409 instead of overwriting someone else's edit.
    expected_updated_at: _JsonDatetime | None = None


class SetlistItemWrite(BaseModel):
    """A piece to add (append, or a new entry in a saved order)."""

    model_config = _WRITE_CONFIG

    arrangement_id: _JsonUuid
    # None opens the arrangement's cover (first-uploaded) part.
    part_id: _JsonUuid | None = None


class SetlistItemKeep(BaseModel):
    """An entry already on the setlist, by id. It keeps its piece and who
    added it; only the part can change, and only on an entry the editor can
    see. Leave `part_id` out to keep the part as it is."""

    model_config = _WRITE_CONFIG

    id: _JsonUuid
    part_id: _JsonUuid | None = None


def _entry_kind(value: Any) -> str:
    # By shape, not by trying each model: a plain union would validate both
    # in strict mode first, which refuses the JSON-string ids.
    return "keep" if isinstance(value, dict) and "id" in value else "new"


SetlistEntryWrite = Annotated[
    Annotated[SetlistItemKeep, Tag("keep")] | Annotated[SetlistItemWrite, Tag("new")],
    Discriminator(_entry_kind),
]


class SetlistItemsReplace(BaseModel):
    """The whole running order, first to last. Saving replaces it: entries
    left out are removed. Named `entries` (it was `items` before
    openclef#64) so a page still sending the old shape gets a 422 instead
    of re-adding every piece as new."""

    model_config = _WRITE_CONFIG

    entries: list[SetlistEntryWrite] = Field(max_length=SETLIST_MAX_ITEMS)
    expected_updated_at: _JsonDatetime | None = None


class SetlistEntry(BaseModel):
    """One position in a setlist, with what the editor and player show.

    `available` is false when the viewer can't open the piece. Then
    `removed` says why, when the viewer may know: "deleted" (by
    `removed_by`) or "unshared" (its owner `removed_by` no longer shares it
    with them), with the title it had. Anyone who never saw the piece gets
    neither: everything but the position and id is withheld."""

    id: uuid.UUID
    position: int
    # Added by the viewer: a contributor may remove only these.
    yours: bool = False
    available: bool = True
    removed: Literal["deleted", "unshared"] | None = None
    removed_by: str | None = None
    arrangement_id: uuid.UUID | None = None
    title: str | None = None
    subtitle: str | None = None
    composer: list[str] = Field(default_factory=list)
    # What was chosen (None = cover), and the part that will actually open.
    part_id: uuid.UUID | None = None
    effective_part_id: uuid.UUID | None = None
    part_label: str | None = None
    page_count: int | None = None
    thumbnail_ready: bool = False


class SetlistSummary(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    owner_username: str
    item_count: int
    created_at: datetime
    updated_at: datetime
    # Add pieces and reorder: the owner, an admin, or a contribute share.
    can_edit: bool
    # Rename and delete: the owner or an admin. Sharing is the owner's alone.
    can_manage: bool = False
    # Shared with anyone (a setlist share; partners don't count). On a
    # shared setlist everyone adds only pieces they own (openclef#64).
    shared: bool = False


class SetlistDetail(SetlistSummary):
    items: list[SetlistEntry]


class SetlistShareCreate(BaseModel):
    """Share a setlist with one person or one group you're in."""

    model_config = _WRITE_CONFIG

    user_id: _JsonUuid | None = None
    group_id: _JsonUuid | None = None
    permission: SharePermission


class SetlistShareUpdate(BaseModel):
    model_config = _WRITE_CONFIG

    permission: SharePermission


class SetlistShareRead(BaseModel):
    id: uuid.UUID
    user: "Person | None" = None
    group: "GroupRef | None" = None
    permission: SharePermission


class HeldBackPiece(BaseModel):
    arrangement_id: uuid.UUID
    title: str


class SetlistShareCheck(BaseModel):
    """The dry run before sharing: pieces on the setlist that its audience
    won't get, because whoever added them doesn't own them. Pieces the
    owner can't see themselves are only counted."""

    held_back: list[HeldBackPiece]
    hidden_count: int = 0


class SetlistRef(BaseModel):
    id: uuid.UUID
    name: str


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


# --- Sharing: people and partners (openclef#62) -------------------------


class Person(BaseModel):
    """Another account, as anyone signed in may see it: no email or role."""

    id: uuid.UUID
    username: str


class IncomingPartner(Person):
    # The receiver's choice: list this person's pieces in my library.
    show_in_library: bool


class Partners(BaseModel):
    # People I share my library with.
    outgoing: list[Person]
    # People who share their library with me.
    incoming: list[IncomingPartner]


class PartnerCreate(BaseModel):
    model_config = _WRITE_CONFIG

    user_id: _JsonUuid


class IncomingPartnerUpdate(BaseModel):
    model_config = _WRITE_CONFIG

    show_in_library: bool


# --- Sharing: groups (openclef#63) -------------------------------------

GroupName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class GroupRef(BaseModel):
    id: uuid.UUID
    name: str


class GroupRead(GroupRef):
    """A group as its members see it. Non-members never get one."""

    owner: Person
    # Everyone in the group, the owner included, by username.
    members: list[Person]


class GroupCreate(BaseModel):
    model_config = _WRITE_CONFIG

    name: GroupName


class GroupUpdate(BaseModel):
    model_config = _WRITE_CONFIG

    name: GroupName


class GroupMemberCreate(BaseModel):
    model_config = _WRITE_CONFIG

    user_id: _JsonUuid


class ArrangementSharesUpdate(BaseModel):
    """The whole set of groups a piece is shared with (replaces it)."""

    model_config = _WRITE_CONFIG

    group_ids: list[_JsonUuid] = Field(max_length=100)


# ArrangementDetail refers to SetlistRef, defined later in this module.
ArrangementDetail.model_rebuild()
