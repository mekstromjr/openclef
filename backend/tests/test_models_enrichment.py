"""Round-trip + status-transition test for EnrichmentJob."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from openclef.models.enrichment import EnrichmentJob
from openclef.models.enums import EnrichmentJobStatus
from tests.factories import make_enrichment_job


async def test_enrichment_job_round_trip(session):
    job = await make_enrichment_job(session)
    fetched = (
        await session.execute(select(EnrichmentJob).where(EnrichmentJob.id == job.id))
    ).scalar_one()
    assert fetched.status == EnrichmentJobStatus.PENDING
    assert fetched.attempts == 0
    assert fetched.completed_at is None


async def test_enrichment_job_completion(session):
    job = await make_enrichment_job(session)
    job.status = EnrichmentJobStatus.SUCCEEDED
    job.candidates_jsonb = [{"mbid": "abc-123", "score": 0.97}]
    job.selected_candidate_id = "abc-123"
    job.attempts = 1
    job.completed_at = datetime.now(timezone.utc)
    await session.flush()

    fetched = (
        await session.execute(select(EnrichmentJob).where(EnrichmentJob.id == job.id))
    ).scalar_one()
    assert fetched.status == EnrichmentJobStatus.SUCCEEDED
    assert fetched.candidates_jsonb == [{"mbid": "abc-123", "score": 0.97}]
    assert fetched.selected_candidate_id == "abc-123"
    assert fetched.attempts == 1
    assert fetched.completed_at is not None
