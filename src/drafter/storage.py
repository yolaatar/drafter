"""Raw JSON lake (gzipped files) plus a DuckDB catalog of parsed, query-friendly tables.

Raw payloads are kept untouched so new features can be re-derived later without re-crawling.
"""

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from drafter.riot.routing import patch_from_version

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    puuid TEXT PRIMARY KEY,
    platform TEXT,
    tier TEXT,
    league_points INTEGER,
    last_crawled_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    platform TEXT,
    patch TEXT,
    game_version TEXT,
    queue_id INTEGER,
    game_start TIMESTAMP,
    duration_s INTEGER,
    blue_win BOOLEAN,
    early_surrender BOOLEAN,
    has_timeline BOOLEAN,
    fetched_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS participants (
    match_id TEXT,
    puuid TEXT,
    team_id INTEGER,
    position TEXT,
    champion_id INTEGER,
    win BOOLEAN,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    gold_earned INTEGER,
    damage_to_champions INTEGER,
    cs INTEGER,
    PRIMARY KEY (match_id, puuid)
);
CREATE TABLE IF NOT EXISTS bans (
    match_id TEXT,
    team_id INTEGER,
    pick_turn INTEGER,
    champion_id INTEGER
);
"""


class Store:
    def __init__(self, db_path: Path, raw_dir: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_dir = raw_dir
        self.con = duckdb.connect(str(db_path))
        self.con.execute(SCHEMA)

    def close(self) -> None:
        self.con.close()

    def _raw_path(self, kind: str, region: str, match_id: str) -> Path:
        return self.raw_dir / region / kind / f"{match_id}.json.gz"

    def write_raw(self, kind: str, region: str, match_id: str, payload: dict) -> None:
        path = self._raw_path(kind, region, match_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))

    def read_raw(self, kind: str, region: str, match_id: str) -> dict | None:
        path = self._raw_path(kind, region, match_id)
        if not path.exists():
            return None
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)

    def upsert_players(self, rows: list[tuple[str, str, str, int]]) -> None:
        self.con.executemany(
            """
            INSERT INTO players (puuid, platform, tier, league_points) VALUES (?, ?, ?, ?)
            ON CONFLICT (puuid) DO UPDATE SET tier = excluded.tier, league_points = excluded.league_points
            """,
            rows,
        )

    def players_to_crawl(self, platform: str, limit: int) -> list[str]:
        rows = self.con.execute(
            """
            SELECT puuid FROM players WHERE platform = ?
            ORDER BY last_crawled_at NULLS FIRST, league_points DESC LIMIT ?
            """,
            [platform, limit],
        ).fetchall()
        return [r[0] for r in rows]

    def mark_crawled(self, puuid: str) -> None:
        self.con.execute("UPDATE players SET last_crawled_at = now() WHERE puuid = ?", [puuid])

    def unseen(self, match_ids: list[str]) -> list[str]:
        if not match_ids:
            return []
        seen = {
            r[0]
            for r in self.con.execute(
                "SELECT match_id FROM matches WHERE match_id IN (SELECT unnest(?))", [match_ids]
            ).fetchall()
        }
        return [m for m in match_ids if m not in seen]

    def insert_match(self, platform: str, match: dict, has_timeline: bool) -> None:
        match_row, participant_rows, ban_rows = parse_match(platform, match, has_timeline)
        self.con.execute("BEGIN")
        try:
            self.con.execute("INSERT OR IGNORE INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", match_row)
            self.con.executemany(
                "INSERT OR IGNORE INTO participants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", participant_rows
            )
            if ban_rows:
                self.con.executemany("INSERT INTO bans VALUES (?, ?, ?, ?)", ban_rows)
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise

    def patch_summary(self) -> list[tuple]:
        return self.con.execute(
            """
            SELECT platform, patch, count(*) AS games,
                   sum(CASE WHEN has_timeline THEN 1 ELSE 0 END) AS with_timeline,
                   round(avg(CASE WHEN blue_win THEN 1 ELSE 0 END), 4) AS blue_wr
            FROM matches WHERE NOT early_surrender
            GROUP BY ALL ORDER BY platform, patch DESC
            """
        ).fetchall()


def parse_match(platform: str, match: dict, has_timeline: bool) -> tuple[tuple, list[tuple], list[tuple]]:
    meta, info = match["metadata"], match["info"]
    match_id = meta["matchId"]
    parts = info["participants"]
    blue_win = next(t["win"] for t in info["teams"] if t["teamId"] == 100)
    match_row = (
        match_id,
        platform,
        patch_from_version(info["gameVersion"]),
        info["gameVersion"],
        info["queueId"],
        datetime.fromtimestamp(info["gameStartTimestamp"] / 1000, tz=timezone.utc).replace(tzinfo=None),
        info["gameDuration"],
        blue_win,
        any(p.get("gameEndedInEarlySurrender", False) for p in parts),
        has_timeline,
        datetime.now(timezone.utc).replace(tzinfo=None),
    )
    participant_rows = [
        (
            match_id,
            p["puuid"],
            p["teamId"],
            p.get("teamPosition") or None,
            p["championId"],
            p["win"],
            p["kills"],
            p["deaths"],
            p["assists"],
            p["goldEarned"],
            p["totalDamageDealtToChampions"],
            p["totalMinionsKilled"] + p.get("neutralMinionsKilled", 0),
        )
        for p in parts
    ]
    ban_rows = [
        (match_id, t["teamId"], b["pickTurn"], b["championId"])
        for t in info["teams"]
        for b in t.get("bans", [])
        if b["championId"] != -1
    ]
    return match_row, participant_rows, ban_rows
