"""Tests for app/observability.py::init_sentry (ROADMAP.md Part 4 6.3).

No real Sentry account/DSN involved — just confirms the actual contract
this module promises: unconfigured is a true no-op, and a configured DSN
really does initialize the SDK client.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import sentry_sdk  # noqa: E402

from app.config import Settings  # noqa: E402
from app.observability import init_sentry  # noqa: E402


def test_init_sentry_is_a_noop_without_a_dsn():
    settings = Settings(sentry_dsn=None)
    init_sentry(settings)
    # No client, or an inactive one — either way, nothing was initialized.
    client = sentry_sdk.get_client()
    assert not client.is_active()


def test_init_sentry_initializes_with_a_real_dsn():
    # A syntactically valid but unreachable DSN — init_sentry only needs
    # to configure the client, never actually send anything for this test
    # to be meaningful.
    settings = Settings(sentry_dsn="https://fakepublickey@o0.ingest.sentry.io/0")
    init_sentry(settings)
    try:
        client = sentry_sdk.get_client()
        assert client.is_active()
        assert client.options["traces_sample_rate"] == settings.sentry_traces_sample_rate
        assert client.options["send_default_pii"] is False
    finally:
        # This suite shares one process (see test_analytics.py's own
        # docstring on why cross-file state here is a real, confirmed
        # issue) — an initialized client left active would have every
        # *other* test's exceptions/logger.exception() calls queue up as
        # Sentry events for the rest of the run, each one then stalling
        # process exit for up to 2s trying to flush to this fake,
        # unreachable DSN (confirmed live: exactly that delay, before
        # this cleanup existed). close(timeout=0) drops any already-
        # queued events immediately rather than waiting to flush them.
        sentry_sdk.get_client().close(timeout=0)
        sentry_sdk.init(dsn=None)
