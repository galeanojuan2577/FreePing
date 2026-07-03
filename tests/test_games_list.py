from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from freeping.data.games_list import (
    _get_local_version,
    get_game_ip_ranges,
    list_game_names,
    load_games,
    update_games_list,
)


class TestLoadGames:
    def test_returns_default_when_file_missing(self, monkeypatch):
        monkeypatch.setattr(
            "freeping.data.games_list._GAMES_JSON",
            Path("/nonexistent/path.json"),
        )
        result = load_games()
        assert result.version == 1
        assert result.games == []

    def test_loads_from_default_path(self, tmp_path, sample_games_list_data, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps(sample_games_list_data))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        result = load_games()
        assert result.version == 1
        assert len(result.games) == 2
        assert result.games[0].name == "Game1"
        assert result.games[1].name == "Game2"

    def test_loads_from_custom_path(self, tmp_path, sample_games_list_data):
        json_path = tmp_path / "custom.json"
        json_path.write_text(json.dumps(sample_games_list_data))
        result = load_games(json_path)
        assert result.version == 1
        assert len(result.games) == 2

    def test_returns_default_with_custom_missing_path(self, tmp_path):
        result = load_games(tmp_path / "missing.json")
        assert result.version == 1
        assert result.games == []

    def test_raises_on_corrupted_json(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text("not valid json")
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        with pytest.raises(json.JSONDecodeError):
            load_games()

    def test_uses_supplied_path_over_default(self, tmp_path, sample_games_list_data, monkeypatch):
        default_path = tmp_path / "default.json"
        default_path.write_text(json.dumps({"version": 0, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", default_path)
        custom_path = tmp_path / "custom.json"
        custom_path.write_text(json.dumps(sample_games_list_data))
        result = load_games(custom_path)
        assert result.version == 1
        assert len(result.games) == 2

    def test_handles_empty_games_list(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 3, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        result = load_games()
        assert result.version == 3
        assert result.games == []


class TestGetGameIpRanges:
    def test_returns_ranges_for_existing_game(self, tmp_path, sample_games_list_data, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps(sample_games_list_data))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        result = get_game_ip_ranges("Game1")
        assert result == ["10.0.0.0/8"]

    def test_returns_empty_list_for_missing_game(self, tmp_path, sample_games_list_data, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps(sample_games_list_data))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        result = get_game_ip_ranges("NonExistent")
        assert result == []

    def test_case_insensitive_match(self, tmp_path, sample_games_list_data, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps(sample_games_list_data))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        result = get_game_ip_ranges("game1")
        assert result == ["10.0.0.0/8"]

    def test_returns_empty_when_file_missing(self, monkeypatch):
        monkeypatch.setattr(
            "freeping.data.games_list._GAMES_JSON",
            Path("/nonexistent.json"),
        )
        result = get_game_ip_ranges("Game1")
        assert result == []

    def test_returns_ranges_for_second_game(self, tmp_path, sample_games_list_data, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps(sample_games_list_data))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        result = get_game_ip_ranges("Game2")
        assert result == ["192.168.0.0/16"]


class TestListGameNames:
    def test_returns_all_names(self, tmp_path, sample_games_list_data, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps(sample_games_list_data))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        result = list_game_names()
        assert result == ["Game1", "Game2"]

    def test_returns_empty_when_file_missing(self, monkeypatch):
        monkeypatch.setattr(
            "freeping.data.games_list._GAMES_JSON",
            Path("/nonexistent.json"),
        )
        result = list_game_names()
        assert result == []

    def test_returns_empty_when_no_games(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 1, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        result = list_game_names()
        assert result == []


class TestUpdateGamesList:
    @pytest.mark.asyncio
    async def test_updates_when_remote_newer(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 1, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": 2,
            "games": [{"name": "NewGame", "protocols": ["udp"], "ip_ranges": []}],
        }
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        result = await update_games_list(mock_client)
        assert result is True
        updated = json.loads(json_path.read_text())
        assert updated["version"] == 2
        assert updated["games"][0]["name"] == "NewGame"

    @pytest.mark.asyncio
    async def test_no_update_when_same_version(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 2, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": 2, "games": []}
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        result = await update_games_list(mock_client)
        assert result is False
        assert json.loads(json_path.read_text())["version"] == 2

    @pytest.mark.asyncio
    async def test_no_update_when_remote_older(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 3, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": 2, "games": []}
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        result = await update_games_list(mock_client)
        assert result is False
        assert json.loads(json_path.read_text())["version"] == 3

    @pytest.mark.asyncio
    async def test_returns_false_on_http_error(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 1, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        result = await update_games_list(mock_client)
        assert result is False

    @pytest.mark.asyncio
    async def test_catches_request_error(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 1, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        result = await update_games_list(mock_client)
        assert result is False

    @pytest.mark.asyncio
    async def test_catches_generic_exception(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 1, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=RuntimeError("Unexpected failure"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        result = await update_games_list(mock_client)
        assert result is False

    @pytest.mark.asyncio
    async def test_updates_when_local_file_missing(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": 1, "games": []}
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        result = await update_games_list(mock_client)
        assert result is True
        assert json_path.exists()
        assert json.loads(json_path.read_text())["version"] == 1

    @pytest.mark.asyncio
    async def test_catches_json_decode_error_from_remote(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 1, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Bad JSON", "", 0)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        result = await update_games_list(mock_client)
        assert result is False

    @pytest.mark.asyncio
    async def test_creates_client_when_none_passed(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 1, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": 2, "games": []}

        mock_async_client = MagicMock(spec=httpx.AsyncClient)
        mock_async_client.get = AsyncMock(return_value=mock_response)
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)

        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: mock_async_client)

        result = await update_games_list()
        assert result is True

    @pytest.mark.asyncio
    async def test_catches_exception_from_created_client(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 1, "games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)

        monkeypatch.setattr(
            "httpx.AsyncClient",
            lambda **kw: (_ for _ in ()).throw(ConnectionError("No internet")),
        )

        result = await update_games_list()
        assert result is False


class TestGetLocalVersion:
    def test_returns_zero_when_file_missing(self, monkeypatch):
        monkeypatch.setattr(
            "freeping.data.games_list._GAMES_JSON",
            Path("/nonexistent.json"),
        )
        assert _get_local_version() == 0

    def test_returns_version_from_file(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"version": 5}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        assert _get_local_version() == 5

    def test_returns_zero_on_corrupted_json(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text("corrupted content")
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        assert _get_local_version() == 0

    def test_returns_zero_when_version_key_missing(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text(json.dumps({"games": []}))
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        assert _get_local_version() == 0

    def test_returns_zero_for_empty_file(self, tmp_path, monkeypatch):
        json_path = tmp_path / "games_list.json"
        json_path.write_text("")
        monkeypatch.setattr("freeping.data.games_list._GAMES_JSON", json_path)
        assert _get_local_version() == 0
