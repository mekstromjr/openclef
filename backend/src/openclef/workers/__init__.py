"""Dramatiq broker setup. Imported before any actor is defined.

Actors bind to whichever broker is current when their decorator runs,
so this module must be imported first (openclef.workers.tasks does).
Run the worker with:

    dramatiq openclef.workers.tasks --processes 1 --threads 1

One process and one thread: PDFium is not thread-safe, and the default
(one process per CPU, 8 threads each) would blow a small pod's memory.
"""
from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker

from openclef.config import get_settings


def _build_broker() -> dramatiq.Broker:
    settings = get_settings()
    if settings.worker_broker == "stub":
        stub = StubBroker()
        stub.emit_after("process_boot")
        return stub
    return RedisBroker(url=settings.redis_url)


broker = _build_broker()
dramatiq.set_broker(broker)
