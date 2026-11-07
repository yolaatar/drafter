"""Async Riot API client with app- and method-level rate limiting."""

import asyncio
import logging
from typing import Any

import httpx

from drafter.riot.ratelimit import RateLimiter

log = logging.getLogger(__name__)

SOLO_QUEUE = "RANKED_SOLO_5x5"
SOLO_QUEUE_ID = 420
APEX_TIERS = ("challenger", "grandmaster", "master")

# Method limits are unknown until the first response; start permissive and let headers correct it.
_DEFAULT_METHOD_LIMIT = "500:10"


class RiotAuthError(RuntimeError):
    pass


class RiotClient:
    def __init__(self, api_key: str, app_rate_limit: str, max_retries: int = 5, timeout: float = 15.0):
        if not api_key:
            raise RiotAuthError("RIOT_API_KEY is not set (see .env.example)")
        self._http = httpx.AsyncClient(headers={"X-Riot-Token": api_key}, timeout=timeout)
        self._app_rate_limit = app_rate_limit
        self._max_retries = max_retries
        # App limits apply per routing host, method limits per (host, endpoint).
        self._app_limiters: dict[str, RateLimiter] = {}
        self._method_limiters: dict[tuple[str, str], RateLimiter] = {}

    async def __aenter__(self) -> "RiotClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._http.aclose()

    def _limiters(self, host: str, method: str) -> tuple[RateLimiter, RateLimiter]:
        app = self._app_limiters.setdefault(host, RateLimiter(self._app_rate_limit))
        meth = self._method_limiters.setdefault((host, method), RateLimiter(_DEFAULT_METHOD_LIMIT))
        return app, meth

    async def _get(self, host: str, path: str, method: str, params: dict | None = None) -> Any:
        app, meth = self._limiters(host, method)
        url = f"https://{host}.api.riotgames.com{path}"
        for attempt in range(self._max_retries):
            await app.acquire()
            await meth.acquire()
            try:
                resp = await self._http.get(url, params=params)
            except httpx.TransportError as e:
                log.warning("transport error on %s: %s (attempt %d)", path, e, attempt + 1)
                await asyncio.sleep(2**attempt)
                continue

            if spec := resp.headers.get("X-App-Rate-Limit"):
                app.update(spec)
            if spec := resp.headers.get("X-Method-Rate-Limit"):
                meth.update(spec)

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            if resp.status_code in (401, 403):
                raise RiotAuthError(f"{resp.status_code} from Riot API: key missing, invalid or expired")
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 1))
                log.warning("429 on %s (%s), sleeping %.1fs", path, resp.headers.get("X-Rate-Limit-Type"), retry_after)
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                await asyncio.sleep(2**attempt)
                continue
            resp.raise_for_status()
        raise RuntimeError(f"Giving up on {path} after {self._max_retries} attempts")

    async def apex_league(self, platform: str, tier: str, queue: str = SOLO_QUEUE) -> dict:
        path = f"/lol/league/v4/{tier}leagues/by-queue/{queue}"
        return await self._get(platform, path, f"league-v4.{tier}")

    async def match_ids(
        self,
        region: str,
        puuid: str,
        start_time: int | None = None,
        queue: int = SOLO_QUEUE_ID,
        start: int = 0,
        count: int = 100,
    ) -> list[str]:
        params = {"queue": queue, "start": start, "count": count}
        if start_time is not None:
            params["startTime"] = start_time
        path = f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
        return await self._get(region, path, "match-v5.ids", params) or []

    async def match(self, region: str, match_id: str) -> dict | None:
        return await self._get(region, f"/lol/match/v5/matches/{match_id}", "match-v5.match")

    async def timeline(self, region: str, match_id: str) -> dict | None:
        return await self._get(region, f"/lol/match/v5/matches/{match_id}/timeline", "match-v5.timeline")
