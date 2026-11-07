"""Static champion data from Data Dragon."""

import json
from pathlib import Path

import httpx

DDRAGON = "https://ddragon.leagueoflegends.com"


def latest_version() -> str:
    return httpx.get(f"{DDRAGON}/api/versions.json", timeout=15).json()[0]


def download_champions(static_dir: Path, version: str | None = None) -> Path:
    version = version or latest_version()
    data = httpx.get(f"{DDRAGON}/cdn/{version}/data/en_US/champion.json", timeout=30).json()
    static_dir.mkdir(parents=True, exist_ok=True)
    path = static_dir / f"champions_{version}.json"
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def load_champions(static_dir: Path) -> dict[int, str]:
    """championId -> display name, from the most recent downloaded file."""
    files = sorted(static_dir.glob("champions_*.json"))
    if not files:
        raise FileNotFoundError("No champion data yet, run `drafter static` first")
    data = json.loads(files[-1].read_text(encoding="utf-8"))["data"]
    return {int(c["key"]): c["name"] for c in data.values()}
