"""Autonomous GenLayer-ecosystem prediction market generator.

Pipeline: ingest raw candidate events (TwitterAPI.io, falling back to
legacy tweepy, falling back to RSS, falling back to a generic webpage
scrape) -> cheap keyword/account relevance gate -> dedup against
MarketEventLog -> LLM extraction (Gemini, structured output) filters
hype/noise and proposes a market -> persist as a `Prediction` directly
through the existing SQLAlchemy session/model, exactly like
services/consensus.py and services/prediction_oracle.py do — this is an
internal job, not an HTTP client of its own API.

Ingestion honesty note: GenLayer doesn't publish a discoverable RSS feed
as of this writing (checked genlayerlabs.com and docs.genlayer.com —
only Discord/Telegram/X were found), so `market_generator_rss_feeds` and
`market_generator_web_pages` (config.py) default to empty; those fetchers
are real and generic, just not pre-pointed at a feed that doesn't exist.
Twitter/X ingestion has two tiers: TwitterAPI.io (`TWITTERAPI_IO_KEY`) is
the one actually verified working end-to-end against a real key and a
real GenLayer response, and is tried first; the official X API via
tweepy (`TWITTER_BEARER_TOKEN`) needs a paid developer tier this app
doesn't have, so it's kept as a secondary path for anyone who does.

Run as a one-off dry run (pulls real tweets if TWITTERAPI_IO_KEY is set,
otherwise falls back to mock events; works without a Gemini key too —
see `_extract_market_offline`):

    cd backend && venv/bin/python -m app.services.market_generator
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.db import AsyncSessionLocal, engine, init_db
from app.models import MarketEventLog, Prediction

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = "gemini-3.5-flash"
CATEGORY = "GenLayer Ecosystem"

# Spec's literal keyword list, matched case-insensitively as substrings.
# "genlayer mainnet" is deliberately its own phrase (not "genlayer" AND
# "mainnet" separately) so a tweet about some *other* project's mainnet
# doesn't match on the word "mainnet" alone.
KEYWORDS: tuple[str, ...] = (
    "genlayer mainnet",
    "testnet",
    "incentivized",
    "consensus",
    "release",
)

_RETRYABLE_ERRORS = (errors.APIError,)


# --- Ingestion ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawEvent:
    """One candidate post/announcement, however it was sourced."""

    source_id: str
    source: str  # "twitter" | "rss" | "web"
    author: str
    text: str
    url: str
    published_at: datetime


def _hash_source(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_relevant_candidate(event: RawEvent, trusted_accounts: set[str]) -> bool:
    """A tweet straight from a trusted GenLayer account is relevant even if
    it doesn't spell out "GenLayer" or a keyword by name (their own
    account tweeting "shipping incentivized testnet phase 2" doesn't need
    to self-reference the brand). Everything else — RSS, webpage scrapes,
    or a tweet from anyone else the search query happened to surface —
    needs an explicit keyword or brand-name hit.
    """
    if event.source == "twitter" and event.author.lower() in trusted_accounts:
        return True
    lowered = event.text.lower()
    return "genlayer" in lowered or any(kw in lowered for kw in KEYWORDS)


TWITTERAPI_IO_URL = "https://api.twitterapi.io/twitter/user/last_tweets"


async def _ingest_from_twitter(accounts: list[str], api_key: str | None) -> list[RawEvent] | None:
    """Primary Twitter/X ingestion path — TwitterAPI.io, a third-party
    proxy that doesn't need a paid X developer tier. Verified live against
    the real @GenLayer account; response shape:

        {"status": "success", "code": 0, "msg": "success",
         "data": {"pin_tweet": null, "tweets": [
             {"id": "...", "url": "...", "text": "...",
              "createdAt": "Mon Aug 31 15:56:11 +0000 2026",
              "author": {"userName": "GenLayer", ...}, ...}
         ]}}

    One request per account (the endpoint is single-user). Returns None
    (not []) only if *every* configured account's request failed outright
    — meaning "ingestion unavailable, try the next tier" — as opposed to a
    real empty/partial result, which should NOT trigger a fallback.
    """
    if not api_key:
        logger.info("TWITTERAPI_IO_KEY not set — skipping TwitterAPI.io ingestion.")
        return None

    events: list[RawEvent] = []
    any_succeeded = False

    async with httpx.AsyncClient(timeout=15) as client:
        for handle in accounts:
            try:
                resp = await client.get(
                    TWITTERAPI_IO_URL,
                    params={"userName": handle},
                    headers={"X-API-Key": api_key},
                )
                resp.raise_for_status()
                payload = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("TwitterAPI.io request failed for %s: %s", handle, exc)
                continue

            if payload.get("status") != "success":
                logger.warning(
                    "TwitterAPI.io returned a non-success status for %s: %s",
                    handle,
                    payload.get("msg"),
                )
                continue

            any_succeeded = True
            tweets = payload.get("data", {}).get("tweets", []) or []
            for tweet in tweets:
                tweet_id = tweet.get("id")
                text = tweet.get("text")
                url = tweet.get("url")
                if not (tweet_id and text and url):
                    continue  # malformed entry — skip rather than crash the batch
                author = (tweet.get("author") or {}).get("userName", handle)
                events.append(
                    RawEvent(
                        source_id=f"twitter_{tweet_id}",
                        source="twitter",
                        author=author,
                        text=text,
                        url=url,
                        published_at=_parse_twitter_created_at(tweet.get("createdAt")),
                    )
                )

    if not any_succeeded:
        logger.warning("TwitterAPI.io ingestion failed for every configured account — falling back.")
        return None
    return events


def _parse_twitter_created_at(value: str | None) -> datetime:
    """Twitter's classic date format, e.g. "Mon Aug 31 15:56:11 +0000 2026"."""
    if value:
        try:
            return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            logger.warning("Unparseable Twitter createdAt %r — using now().", value)
    return datetime.now(timezone.utc)


async def _fetch_from_twitter_legacy(
    accounts: list[str], bearer_token: str | None
) -> list[RawEvent] | None:
    """Secondary Twitter/X ingestion path via the official API (tweepy) —
    kept for anyone with a paid X developer tier, but not what this app is
    actually configured with; see _ingest_from_twitter for the real path.
    Returns None (not []) to mean "unavailable, fall back further" —
    distinct from a real empty result, which just means no new matching
    tweets this cycle and should NOT trigger the fallback.
    """
    if not bearer_token:
        logger.info("TWITTER_BEARER_TOKEN not set — skipping legacy Twitter ingestion.")
        return None

    try:
        import tweepy
    except ImportError:
        logger.warning("tweepy not installed — skipping Twitter ingestion.")
        return None

    account_clause = " OR ".join(f"from:{handle}" for handle in accounts)
    keyword_clause = " OR ".join(f'"{kw}"' for kw in KEYWORDS)
    query = f"({account_clause}) ({keyword_clause}) -is:retweet"

    client = tweepy.Client(bearer_token=bearer_token)
    try:
        # tweepy's Client is a synchronous (requests-based) client — run it
        # off the event loop rather than blocking every other coroutine.
        response = await asyncio.to_thread(
            client.search_recent_tweets,
            query=query,
            max_results=25,
            tweet_fields=["created_at", "author_id"],
            expansions=["author_id"],
            user_fields=["username"],
        )
    except Exception as exc:  # tweepy.TweepyException and its subclasses
        logger.warning("Twitter ingestion failed (%s) — falling back to RSS/web.", exc)
        return None

    if not response or not response.data:
        return []

    users_by_id = {u.id: u.username for u in (response.includes or {}).get("users", [])}
    events = []
    for tweet in response.data:
        username = users_by_id.get(tweet.author_id, "unknown")
        events.append(
            RawEvent(
                source_id=f"twitter:{tweet.id}",
                source="twitter",
                author=username,
                text=tweet.text,
                url=f"https://x.com/{username}/status/{tweet.id}",
                published_at=tweet.created_at or datetime.now(timezone.utc),
            )
        )
    return events


def _parse_feed_time(entry: dict) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


async def _fetch_from_rss(feed_urls: list[str]) -> list[RawEvent]:
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser not installed — skipping RSS ingestion.")
        return []

    events: list[RawEvent] = []
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for feed_url in feed_urls:
            try:
                resp = await client.get(feed_url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("RSS fetch failed for %s: %s", feed_url, exc)
                continue

            parsed = feedparser.parse(resp.content)
            feed_title = parsed.feed.get("title", feed_url) if parsed.feed else feed_url
            for entry in parsed.entries:
                url = entry.get("link") or feed_url
                events.append(
                    RawEvent(
                        source_id=f"rss:{_hash_source(url)}",
                        source="rss",
                        author=feed_title,
                        text=f"{entry.get('title', '')}\n{entry.get('summary', '')}".strip(),
                        url=url,
                        published_at=_parse_feed_time(entry),
                    )
                )
    return events


async def _fetch_from_webpage(page_urls: list[str]) -> list[RawEvent]:
    """Last-tier fallback for a source with no feed at all: grab every
    reasonably-long link on the page as a headline candidate. Deliberately
    generic (no site-specific CSS selectors) — tune `min link text length`
    per-site if a real target page turns out noisier than expected.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("beautifulsoup4 not installed — skipping webpage ingestion.")
        return []

    events: list[RawEvent] = []
    headers = {"User-Agent": "NuanceMarketGenerator/1.0 (+https://genlayer.com)"}
    async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=headers) as client:
        for page_url in page_urls:
            try:
                resp = await client.get(page_url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Webpage fetch failed for %s: %s", page_url, exc)
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            base = httpx.URL(page_url)
            for link in soup.find_all("a", href=True):
                text = link.get_text(strip=True)
                if len(text) < 20:  # nav/footer chrome is short; real headlines aren't
                    continue
                absolute_url = str(base.join(link["href"]))
                events.append(
                    RawEvent(
                        source_id=f"web:{_hash_source(absolute_url)}",
                        source="web",
                        author=page_url,
                        text=text,
                        url=absolute_url,
                        published_at=datetime.now(timezone.utc),
                    )
                )
    return events


async def _ingest_events(
    accounts: list[str],
    twitterapi_io_key: str | None,
    bearer_token: str | None,
    rss_feeds: list[str],
    web_pages: list[str],
) -> list[RawEvent]:
    """Raw events only — no relevance filtering here. That lives in
    `_process_events` instead, so both this real path and the mock-event
    dry run below apply the exact same filter rather than the dry run
    silently skipping it.

    Tiers, each falling through to the next only when the one before it
    is *unavailable* (unconfigured or every request failed) — a real but
    empty result at any tier is final, not a signal to keep falling back:
    TwitterAPI.io -> legacy tweepy -> RSS -> generic webpage scrape.
    """
    twitter_events = await _ingest_from_twitter(accounts, twitterapi_io_key)
    if twitter_events is None:
        twitter_events = await _fetch_from_twitter_legacy(accounts, bearer_token)
    if twitter_events is not None:
        return list(twitter_events)

    events: list[RawEvent] = []
    events.extend(await _fetch_from_rss(rss_feeds))
    events.extend(await _fetch_from_webpage(web_pages))
    return events


# --- LLM extraction ------------------------------------------------------


DEFAULT_HORIZON_DAYS = 30
MAX_HORIZON_DAYS = 365


class ExtractedMarket(BaseModel):
    is_verifiable_milestone: bool = Field(
        description=(
            "True only if this describes a concrete, FUTURE, quantifiable "
            "GenLayer milestone — a hackathon and its deadline, a testnet/"
            "incentivized-testnet phase, a points-to-token conversion, a "
            "mainnet launch date, a protocol/consensus upgrade with a "
            "stated timeline, or similar. False for hype, opinion, memes, "
            "recap/highlight videos, replies with no new information, or "
            "anything already fully resolved by the time of posting."
        )
    )
    title: str = Field(
        default="",
        description=(
            "A yes/no question a bettor could unambiguously answer later, "
            "phrased starting with 'Will GenLayer' — e.g. \"Will GenLayer's "
            "Hackathon conclude on September 17, 2026?\" or 'Will GenLayer "
            "announce a Mainnet launch date before Q4 2026?'. Empty if "
            "is_verifiable_milestone is false."
        ),
    )
    resolution_rules: str = Field(
        default="",
        description=(
            "Concrete, binary, checkable criteria referencing only "
            "publicly verifiable facts — what exactly must be true for "
            "this to resolve YES vs. NO. Empty if is_verifiable_milestone "
            "is false."
        ),
    )
    end_time: str = Field(
        default="",
        description=(
            "ISO 8601 UTC timestamp for when this should resolve. Derive "
            "it from any concrete date/deadline mentioned in the source "
            "text (a stated hackathon end date, a quoted quarter/date); if "
            f"none is mentioned, estimate a reasonable horizon (typically "
            f"14-60 days out — never more than {MAX_HORIZON_DAYS} days). "
            "Empty if is_verifiable_milestone is false."
        ),
    )


_EXTRACTOR_SYSTEM_PROMPT = (
    "You are a market-generation analyst for Nuance, a GenLayer-ecosystem "
    "prediction market platform. You are given one raw social post or "
    "announcement, most often from GenLayer's own official account. "
    "Identify only future-facing, quantifiable GenLayer milestones: "
    "hackathons and their deadlines, testnet/incentivized-testnet phases, "
    "points-to-token conversions, mainnet launch dates, protocol/consensus "
    "upgrades with a stated timeline, and similar named, dated events. "
    "Strictly reject generic commentary, memes, recap or highlight videos, "
    "replies with no new information, and anything already fully resolved "
    "by the time of posting.\n\n"
    "When you do flag a milestone, phrase `title` as a yes/no question "
    "starting with 'Will GenLayer'. Respond with the required structured "
    "JSON only."
)


def _extractor_user_prompt(event: RawEvent) -> str:
    return (
        f"Source: {event.source}\n"
        f"Author: {event.author}\n"
        f"Published: {event.published_at.isoformat()}\n"
        f"URL: {event.url}\n\n"
        f"Content:\n{event.text}"
    )


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _call_extractor(client: genai.Client, event: RawEvent) -> ExtractedMarket:
    config = types.GenerateContentConfig(
        system_instruction=_EXTRACTOR_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=ExtractedMarket,
        temperature=0.3,
    )
    response = await client.aio.models.generate_content(
        model=EXTRACTION_MODEL,
        contents=_extractor_user_prompt(event),
        config=config,
    )

    if response.parsed and isinstance(response.parsed, ExtractedMarket):
        return response.parsed
    if response.text:
        return ExtractedMarket(**json.loads(response.text))
    raise ValueError("Empty response from the extraction model.")


async def _extract_market(client: genai.Client, event: RawEvent) -> ExtractedMarket | None:
    result = await _call_extractor(client, event)
    if not result.is_verifiable_milestone or not result.title.strip():
        return None
    return result


def _extract_market_offline(event: RawEvent) -> ExtractedMarket | None:
    """No GEMINI_API_KEY configured. Mirrors services/consensus.py's own
    no-key philosophy: degrade to a deterministic, clearly-labeled
    stand-in rather than silently doing nothing, so the rest of the
    pipeline (dedup, persistence, the dry run below) stays exercisable.
    Every keyword-relevant event is treated as a candidate here — there's
    no real "filter noise" step without an LLM, which is exactly why this
    is a fallback, not the real extraction path.
    """
    snippet = event.text.strip().splitlines()[0][:140]
    if not snippet:
        return None
    end_time = (datetime.now(timezone.utc) + timedelta(days=DEFAULT_HORIZON_DAYS)).isoformat()
    return ExtractedMarket(
        is_verifiable_milestone=True,
        title=f'Will this GenLayer claim hold true: "{snippet}"?',
        resolution_rules=(
            f"Resolves YES if the claim in the source post ({event.url}) is "
            "independently confirmed by an official GenLayer announcement "
            "before the resolution date; NO otherwise. (Auto-generated "
            "without LLM extraction — GEMINI_API_KEY not configured, so "
            "this has not been checked for noise/hype.)"
        ),
        end_time=end_time,
    )


def _parse_end_time(raw: str) -> datetime:
    """Validates/clamps the extractor's end_time rather than trusting it
    blindly — an LLM (or the offline fallback) producing a malformed or
    nonsensical timestamp would otherwise become a live market's actual
    resolution date. Falls back to DEFAULT_HORIZON_DAYS from now.
    """
    fallback = datetime.now(timezone.utc) + timedelta(days=DEFAULT_HORIZON_DAYS)
    if not raw or not raw.strip():
        return fallback

    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Unparseable end_time %r from extractor — using default horizon.", raw)
        return fallback

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if parsed <= now:
        logger.warning("Extractor end_time %r is not in the future — using default horizon.", raw)
        return fallback
    max_allowed = now + timedelta(days=MAX_HORIZON_DAYS)
    if parsed > max_allowed:
        logger.warning("Extractor end_time %r is implausibly far out — clamping.", raw)
        return max_allowed
    return parsed


async def _ensure_schema() -> None:
    """`init_db()` (create_all) only creates *missing tables* — it won't
    retroactively add `resolution_source_url` to a `predictions` table that
    already existed before this prompt. There's no Alembic yet (ROADMAP.md
    Part 3), so for SQLite specifically this patches the live dev DB with a
    plain `ALTER TABLE ... ADD COLUMN` rather than requiring everyone to
    delete and recreate nuance.db. A no-op once the column exists, and
    deliberately scoped to sqlite only — Postgres gets a real migration.
    """
    await init_db()
    if engine.dialect.name != "sqlite":
        return
    async with engine.begin() as conn:
        result = await conn.exec_driver_sql("PRAGMA table_info(predictions)")
        existing_columns = {row[1] for row in result.fetchall()}
        if "resolution_source_url" not in existing_columns:
            await conn.exec_driver_sql(
                "ALTER TABLE predictions ADD COLUMN resolution_source_url TEXT"
            )
            logger.info(
                "Patched dev DB: added predictions.resolution_source_url "
                "(pre-existing table, no Alembic yet)."
            )


# --- Dedup + persistence ---------------------------------------------------


async def _already_processed(db: AsyncSession, source_id: str) -> bool:
    return await db.get(MarketEventLog, source_id) is not None


async def _mark_processed(
    db: AsyncSession, event: RawEvent, outcome: str, prediction_id: int | None = None
) -> None:
    db.add(
        MarketEventLog(
            source_id=event.source_id,
            source=event.source,
            source_url=event.url,
            outcome=outcome,
            prediction_id=prediction_id,
        )
    )


async def _process_events(
    db: AsyncSession,
    events: Iterable[RawEvent],
    *,
    auto_publish: bool,
    gemini_client: genai.Client | None,
    trusted_accounts: set[str],
) -> list[Prediction]:
    created: list[Prediction] = []
    seen_this_batch: set[str] = set()

    for event in events:
        if event.source_id in seen_this_batch:
            continue
        seen_this_batch.add(event.source_id)

        if await _already_processed(db, event.source_id):
            continue

        # Cheap pre-LLM gate: applied here (not in _ingest_events) so both
        # the real ingestion path and the mock-event dry run get it —
        # skipping this cost the dry run a wasted, rate-limited API call
        # against an obviously irrelevant mock tweet during development.
        if not _is_relevant_candidate(event, trusted_accounts):
            await _mark_processed(db, event, outcome="skipped")
            continue

        try:
            extracted = (
                await _extract_market(gemini_client, event)
                if gemini_client is not None
                else _extract_market_offline(event)
            )
        except Exception as exc:  # noqa: BLE001 — one bad extraction shouldn't kill the batch
            logger.warning("Extraction failed for %s: %s", event.source_id, exc)
            await _mark_processed(db, event, outcome="error")
            continue

        if extracted is None:
            await _mark_processed(db, event, outcome="skipped")
            continue

        prediction = Prediction(
            title=extracted.title.strip(),
            description=extracted.resolution_rules.strip(),
            category=CATEGORY,
            resolution_date=_parse_end_time(extracted.end_time),
            status_key="open" if auto_publish else "pending_review",
            resolution_source_url=event.url,
        )
        db.add(prediction)
        await db.flush()  # assign prediction.id before logging it below
        await _mark_processed(db, event, outcome="created", prediction_id=prediction.id)
        created.append(prediction)

    await db.commit()
    for prediction in created:
        await db.refresh(prediction)
    return created


async def process_latest_events(db: AsyncSession, auto_publish: bool = True) -> list[Prediction]:
    """Ingests, filters, extracts, and persists new GenLayer-ecosystem
    markets. `auto_publish=False` still creates the Prediction rows (so
    nothing has to be re-extracted later) but as `status_key="pending_
    review"` rather than `"open"` — invisible to betting (the bet endpoint
    already rejects anything whose status isn't "open") until a human
    flips it live.
    """
    await _ensure_schema()
    settings = get_settings()
    events = await _ingest_events(
        accounts=settings.market_generator_accounts_list,
        twitterapi_io_key=settings.twitterapi_io_key,
        bearer_token=settings.twitter_bearer_token,
        rss_feeds=settings.market_generator_rss_feeds_list,
        web_pages=settings.market_generator_web_pages_list,
    )

    gemini_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
    if gemini_client is None:
        logger.warning(
            "GEMINI_API_KEY not set — market_generator using the offline "
            "heuristic extractor (see _extract_market_offline)."
        )

    trusted = {handle.lower() for handle in settings.market_generator_accounts_list}
    return await _process_events(
        db, events, auto_publish=auto_publish, gemini_client=gemini_client, trusted_accounts=trusted
    )


# --- Dry run / CLI ----------------------------------------------------------

_MOCK_EVENTS: list[RawEvent] = [
    RawEvent(
        source_id="mock:milestone",
        source="twitter",
        author="genlayer",
        text=(
            "Incentivized Testnet Phase 2 goes live next month, with GEN "
            "staking rewards for validators who help harden consensus "
            "ahead of Mainnet. Full details in the docs."
        ),
        url="https://x.com/genlayer/status/mock-milestone",
        published_at=datetime.now(timezone.utc),
    ),
    RawEvent(
        source_id="mock:hype",
        source="twitter",
        author="genlayer",
        text="gm builders ☀️ what are you shipping today?",
        url="https://x.com/genlayer/status/mock-hype",
        published_at=datetime.now(timezone.utc),
    ),
    RawEvent(
        source_id="mock:irrelevant",
        source="twitter",
        author="some_random_account",
        text="Just had the best coffee of my life, nothing to do with crypto.",
        url="https://x.com/some_random_account/status/mock-irrelevant",
        published_at=datetime.now(timezone.utc),
    ),
    RawEvent(
        source_id="mock:announcement",
        source="rss",
        author="GenLayer Blog",
        text=(
            "GenLayer Mainnet launch date announced: consensus release "
            "targeted for Q1 2027 pending final security audit."
        ),
        url="https://genlayerlabs.com/blog/mainnet-date",
        published_at=datetime.now(timezone.utc),
    ),
]


async def _dry_run() -> None:
    """Pulls real tweets (and/or RSS/web) when a real ingestion source is
    configured; otherwise exercises the whole pipeline against the mock
    events below, network-free. Either way, `auto_publish=False` — this
    is still a dry run, so anything created lands as a `pending_review`
    draft, not a live bettable market. Publishing a reviewed draft live
    isn't wired up yet (there's no admin/publish endpoint) — see
    ROADMAP.md.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    await _ensure_schema()

    settings = get_settings()
    gemini_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
    trusted = {handle.lower() for handle in settings.market_generator_accounts_list}

    live_source_configured = bool(
        settings.twitterapi_io_key
        or settings.twitter_bearer_token
        or settings.market_generator_rss_feeds_list
        or settings.market_generator_web_pages_list
    )

    if live_source_configured:
        events = await _ingest_events(
            accounts=settings.market_generator_accounts_list,
            twitterapi_io_key=settings.twitterapi_io_key,
            bearer_token=settings.twitter_bearer_token,
            rss_feeds=settings.market_generator_rss_feeds_list,
            web_pages=settings.market_generator_web_pages_list,
        )
        mode = f"LIVE ingestion — {len(events)} raw event(s) fetched"
    else:
        events = _MOCK_EVENTS
        mode = f"no live ingestion source configured — {len(events)} mock event(s)"

    print(
        f"--- market_generator dry run "
        f"({'Gemini' if gemini_client else 'offline heuristic'} extraction, {mode}, "
        f"auto_publish=False so results land as drafts) ---\n"
    )

    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, events, auto_publish=False, gemini_client=gemini_client, trusted_accounts=trusted
        )

    if not created:
        print(
            "No markets created — everything was noise, irrelevant, or "
            "already processed on a prior run against this same database "
            "(MarketEventLog dedup applies to real tweet ids too, so "
            "re-running won't reprocess the same tweet twice)."
        )
    for prediction in created:
        print(f"[created as '{prediction.status_key}'] {prediction.title}")
        print(f"  category: {prediction.category}")
        print(f"  resolves: {prediction.resolution_date.isoformat()}")
        print(f"  source:   {prediction.resolution_source_url}")
        print(f"  rules:    {prediction.description}\n")


if __name__ == "__main__":
    asyncio.run(_dry_run())
