import asyncio
import logging

import typer

from drafter.config import Settings
from drafter.crawl.ladder import crawl as crawl_ladder
from drafter.riot.client import RiotClient
from drafter.static import download_champions
from drafter.storage import Store

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


@app.command()
def static(version: str = typer.Option(None, help="Data Dragon version, defaults to latest")) -> None:
    """Download champion static data."""
    path = download_champions(Settings().static_dir, version)
    typer.echo(f"Saved {path}")


@app.command()
def crawl(
    platform: str = typer.Option("euw1", help="Platform id, e.g. euw1, kr, na1"),
    max_matches: int = typer.Option(1000),
    since_days: float = typer.Option(14, help="Only matches newer than this"),
    timelines: bool = typer.Option(True, help="Also fetch per-minute timelines (2x requests)"),
) -> None:
    """Crawl recent Master+ solo queue games."""
    settings = Settings()
    store = Store(settings.db_path, settings.raw_dir)

    async def run() -> int:
        async with RiotClient(settings.riot_api_key, settings.app_rate_limit) as client:
            return await crawl_ladder(client, store, platform, max_matches, since_days, timelines)

    try:
        n = asyncio.run(run())
    finally:
        store.close()
    typer.echo(f"Fetched {n} new matches")


@app.command()
def stats() -> None:
    """Games stored per platform and patch."""
    settings = Settings()
    store = Store(settings.db_path, settings.raw_dir)
    try:
        rows = store.patch_summary()
    finally:
        store.close()
    if not rows:
        typer.echo("No matches yet")
        return
    typer.echo(f"{'platform':<9} {'patch':<7} {'games':>7} {'timeline':>9} {'blue_wr':>8}")
    for platform, patch, games, with_tl, blue_wr in rows:
        typer.echo(f"{platform:<9} {patch:<7} {games:>7} {with_tl:>9} {blue_wr:>8}")
