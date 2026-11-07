# drafter

League of Legends draft assistant. Recommends picks and bans during champion select and explains *why*: matchup mechanics, team composition gaps, win conditions.

Starts with high-elo solo queue (lots of data, easy to playtest), then pro play (fearless series planning).

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Setup

```sh
uv sync
cp .env.example .env   # then put your Riot key in it
uv run drafter static  # champion data from Data Dragon
uv run drafter crawl --platform euw1 --max-matches 500
uv run drafter stats
```

## Tests

```sh
uv run pytest
```
