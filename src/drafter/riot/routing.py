"""Platform (league-v4) to regional (match-v5) routing."""

PLATFORM_TO_REGION = {
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "me1": "europe",
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "kr": "asia",
    "jp1": "asia",
    "oc1": "sea",
    "sg2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}


def region_for(platform: str) -> str:
    try:
        return PLATFORM_TO_REGION[platform.lower()]
    except KeyError:
        raise ValueError(f"Unknown platform {platform!r}, expected one of {sorted(PLATFORM_TO_REGION)}")


def patch_from_version(game_version: str) -> str:
    """'15.20.712.4321' -> '15.20'."""
    major, minor, *_ = game_version.split(".")
    return f"{major}.{minor}"
