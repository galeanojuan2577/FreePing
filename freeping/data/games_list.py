from __future__ import annotations

import json
from pathlib import Path

from freeping.core.models import GamesList

_GAMES_JSON = Path(__file__).parent / "games_list.json"
_REMOTE_URL = "https://raw.githubusercontent.com/diegogaleano/FreePing/main/freeping/data/games_list.json"


def load_games(path: Path | None = None) -> GamesList:
    source = path or _GAMES_JSON
    if not source.exists():
        return GamesList(version=1)

    data = json.loads(source.read_text())
    return GamesList.from_json(data)


def get_game_ip_ranges(game_name: str) -> list[str]:
    games = load_games()
    game = games.find_game(game_name)
    return game.ip_ranges if game else []


def list_game_names() -> list[str]:
    games = load_games()
    return [g.name for g in games.games]


async def update_games_list(client=None) -> bool:
    try:
        import httpx
        async with (client or httpx.AsyncClient(timeout=10.0)) as c:
            resp = await c.get(_REMOTE_URL)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("version", 0) > _get_local_version():
                    _GAMES_JSON.write_text(json.dumps(data, indent=2))
                    return True
    except Exception:
        pass
    return False


def _get_local_version() -> int:
    if not _GAMES_JSON.exists():
        return 0
    try:
        data = json.loads(_GAMES_JSON.read_text())
        return data.get("version", 0)
    except (json.JSONDecodeError, KeyError):
        return 0
