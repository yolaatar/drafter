from drafter.riot.routing import patch_from_version, region_for
from drafter.storage import Store, parse_match


def _participant(i: int, team: int, win: bool) -> dict:
    return {
        "puuid": f"p{i}",
        "teamId": team,
        "teamPosition": ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"][i % 5],
        "championId": 100 + i,
        "win": win,
        "kills": 1,
        "deaths": 2,
        "assists": 3,
        "goldEarned": 10000,
        "totalDamageDealtToChampions": 20000,
        "totalMinionsKilled": 150,
        "neutralMinionsKilled": 10,
    }


MATCH = {
    "metadata": {"matchId": "EUW1_123"},
    "info": {
        "gameVersion": "15.20.712.4321",
        "queueId": 420,
        "gameStartTimestamp": 1_760_000_000_000,
        "gameDuration": 1800,
        "participants": [_participant(i, 100 if i < 5 else 200, i < 5) for i in range(10)],
        "teams": [
            {"teamId": 100, "win": True, "bans": [{"championId": 1, "pickTurn": 1}, {"championId": -1, "pickTurn": 2}]},
            {"teamId": 200, "win": False, "bans": [{"championId": 2, "pickTurn": 6}]},
        ],
    },
}


def test_routing():
    assert region_for("EUW1") == "europe"
    assert region_for("kr") == "asia"
    assert patch_from_version("15.20.712.4321") == "15.20"


def test_parse_match():
    match_row, parts, bans = parse_match("euw1", MATCH, has_timeline=False)
    assert match_row[2] == "15.20"
    assert match_row[7] is True
    assert len(parts) == 10
    assert parts[0][-1] == 160
    assert [b[3] for b in bans] == [1, 2]


def test_store_roundtrip(tmp_path):
    store = Store(tmp_path / "db.duckdb", tmp_path / "raw")
    store.write_raw("matches", "europe", "EUW1_123", MATCH)
    store.insert_match("euw1", MATCH, has_timeline=False)
    store.insert_match("euw1", MATCH, has_timeline=False)
    assert store.unseen(["EUW1_123", "EUW1_999"]) == ["EUW1_999"]
    assert store.read_raw("matches", "europe", "EUW1_123") == MATCH
    assert store.patch_summary() == [("euw1", "15.20", 1, 0, 1.0)]
    store.close()
