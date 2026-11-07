"""Crawl recent apex-tier (Master+) solo queue games for one platform."""

import asyncio
import logging
import time

from drafter.riot.client import APEX_TIERS, RiotClient
from drafter.riot.routing import region_for
from drafter.storage import Store

log = logging.getLogger(__name__)


async def seed_players(client: RiotClient, store: Store, platform: str) -> int:
    total = 0
    for tier in APEX_TIERS:
        league = await client.apex_league(platform, tier)
        if not league:
            continue
        rows = [(e["puuid"], platform, tier, e["leaguePoints"]) for e in league["entries"] if e.get("puuid")]
        store.upsert_players(rows)
        total += len(rows)
        log.info("%s %s: %d players", platform, tier, len(rows))
    return total


async def _fetch_one(
    client: RiotClient, store: Store, platform: str, region: str, match_id: str, with_timeline: bool
) -> bool:
    match = await client.match(region, match_id)
    if match is None:
        return False
    timeline = await client.timeline(region, match_id) if with_timeline else None
    store.write_raw("matches", region, match_id, match)
    if timeline is not None:
        store.write_raw("timelines", region, match_id, timeline)
    store.insert_match(platform, match, has_timeline=timeline is not None)
    return True


async def crawl(
    client: RiotClient,
    store: Store,
    platform: str,
    max_matches: int,
    since_days: float = 14,
    with_timelines: bool = True,
    concurrency: int = 8,
) -> int:
    region = region_for(platform)
    await seed_players(client, store, platform)
    start_time = int(time.time() - since_days * 86400)
    sem = asyncio.Semaphore(concurrency)
    fetched = 0

    async def bounded(match_id: str) -> bool:
        async with sem:
            try:
                return await _fetch_one(client, store, platform, region, match_id, with_timelines)
            except Exception:
                log.exception("failed to fetch %s", match_id)
                return False

    # Plenty of apex players exist; walk them least-recently-crawled first.
    for puuid in store.players_to_crawl(platform, limit=10_000):
        if fetched >= max_matches:
            break
        ids = store.unseen(await client.match_ids(region, puuid, start_time=start_time))
        ids = ids[: max_matches - fetched]
        results = await asyncio.gather(*(bounded(m) for m in ids))
        fetched += sum(results)
        store.mark_crawled(puuid)
        if ids:
            log.info("%d/%d matches", fetched, max_matches)
    return fetched
