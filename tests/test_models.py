from __future__ import annotations

from freeping.core.models import (
    Game,
    GameProtocol,
    GamesList,
    LatencyResult,
    OciCredentials,
    TunnelConfig,
    TunnelState,
    VPSStatus,
)


class TestVPSStatus:
    def test_has_expected_values(self) -> None:
        assert VPSStatus.RUNNING.value == "running"
        assert VPSStatus.STOPPED.value == "stopped"
        assert VPSStatus.TERMINATED.value == "terminated"
        assert VPSStatus.UNKNOWN.value == "unknown"


class TestTunnelState:
    def test_has_expected_values(self) -> None:
        assert TunnelState.INACTIVE.value == "inactive"
        assert TunnelState.CONNECTING.value == "connecting"
        assert TunnelState.ACTIVE.value == "active"
        assert TunnelState.ERROR.value == "error"


class TestGame:
    def test_create_from_json(self, sample_game_data: dict) -> None:
        game = Game.load_from_json(sample_game_data)
        assert game.name == "TestGame"
        assert game.ip_ranges == ["192.168.1.0/24", "10.0.0.0/8"]
        assert game.protocols == [GameProtocol.UDP]
        assert game.ports == ["7000-7500"]

    def test_create_with_string_protocols(self) -> None:
        data = {
            "name": "Test",
            "protocols": ["udp", "tcp"],
            "ip_ranges": ["10.0.0.0/8"],
        }
        game = Game.load_from_json(data)
        assert GameProtocol.UDP in game.protocols
        assert GameProtocol.TCP in game.protocols

    def test_to_dict_roundtrip(self) -> None:
        original = Game(
            name="Test",
            ip_ranges=["10.0.0.0/8"],
            protocols=[GameProtocol.UDP],
            ports=["1234"],
        )
        data = original.to_dict()
        restored = Game.load_from_json(data)
        assert restored.name == original.name
        assert restored.ip_ranges == original.ip_ranges
        assert restored.protocols == original.protocols
        assert restored.ports == original.ports

    def test_default_protocol_is_udp(self) -> None:
        game = Game(name="Test")
        assert game.protocols == [GameProtocol.UDP]


class TestGamesList:
    def test_from_json(self, sample_games_list_data: dict) -> None:
        games_list = GamesList.from_json(sample_games_list_data)
        assert games_list.version == 1
        assert len(games_list.games) == 2
        assert games_list.games[0].name == "Game1"
        assert games_list.games[1].name == "Game2"

    def test_find_game_found(self, sample_games_list_data: dict) -> None:
        games_list = GamesList.from_json(sample_games_list_data)
        game = games_list.find_game("Game1")
        assert game is not None
        assert game.name == "Game1"

    def test_find_game_case_insensitive(self, sample_games_list_data: dict) -> None:
        games_list = GamesList.from_json(sample_games_list_data)
        game = games_list.find_game("game1")
        assert game is not None
        assert game.name == "Game1"

    def test_find_game_not_found(self, sample_games_list_data: dict) -> None:
        games_list = GamesList.from_json(sample_games_list_data)
        game = games_list.find_game("NonExistent")
        assert game is None

    def test_all_ip_ranges(self, sample_games_list_data: dict) -> None:
        games_list = GamesList.from_json(sample_games_list_data)
        ranges = games_list.all_ip_ranges()
        assert "10.0.0.0/8" in ranges
        assert "192.168.0.0/16" in ranges
        assert len(ranges) == 2


class TestTunnelConfig:
    def test_default_values(self) -> None:
        config = TunnelConfig()
        assert config.vps_port == 51820
        assert config.client_address == "10.0.0.2/32"
        assert config.dns == "1.1.1.1"
        assert config.persistent_keepalive == 25

    def test_validate_valid(self) -> None:
        config = TunnelConfig(vps_ip="203.0.113.1")
        errors = config.validate()
        assert errors == []

    def test_validate_invalid_ip(self) -> None:
        config = TunnelConfig(vps_ip="not_an_ip")
        errors = config.validate()
        assert len(errors) > 0
        assert any("Invalid VPS IP" in e for e in errors)

    def test_validate_invalid_port(self) -> None:
        config = TunnelConfig(vps_ip="203.0.113.1", vps_port=99999)
        errors = config.validate()
        assert any("Invalid port" in e for e in errors)

    def test_validate_empty_ip(self) -> None:
        config = TunnelConfig(vps_ip="")
        errors = config.validate()
        assert errors == []

    def test_to_wireguard_conf_includes_keys(self) -> None:
        config = TunnelConfig(
            vps_ip="203.0.113.1",
            client_private_key="client_priv",
            public_key="server_pub",
            allowed_ips=["10.0.0.0/8"],
        )
        conf = config.to_wireguard_conf()
        assert "PrivateKey = client_priv" in conf
        assert "PublicKey = server_pub" in conf
        assert "Endpoint = 203.0.113.1:51820" in conf
        assert "AllowedIPs = 10.0.0.0/8" in conf
        assert "PersistentKeepalive = 25" in conf

    def test_to_wireguard_conf_default_allowed_ips(self) -> None:
        config = TunnelConfig(
            vps_ip="203.0.113.1",
            client_private_key="key",
            public_key="pub",
        )
        conf = config.to_wireguard_conf()
        assert "AllowedIPs = 0.0.0.0/0" in conf

    def test_to_dict_roundtrip(self) -> None:
        original = TunnelConfig(
            vps_ip="203.0.113.1",
            vps_port=51820,
            private_key="priv",
            public_key="pub",
            client_private_key="c_priv",
            allowed_ips=["10.0.0.0/8"],
        )
        data = original.to_dict()
        restored = TunnelConfig(**data)
        assert restored.vps_ip == original.vps_ip
        assert restored.vps_port == original.vps_port
        assert restored.private_key == original.private_key
        assert restored.allowed_ips == original.allowed_ips


class TestOciCredentials:
    def test_validate_valid(self, sample_credentials: OciCredentials) -> None:
        errors = sample_credentials.validate()
        assert errors == []

    def test_validate_invalid_user_ocid(self, sample_credentials: OciCredentials) -> None:
        sample_credentials.user_ocid = "invalid"
        errors = sample_credentials.validate()
        assert len(errors) > 0

    def test_validate_invalid_tenancy_ocid(self, sample_credentials: OciCredentials) -> None:
        sample_credentials.tenancy_ocid = "invalid"
        errors = sample_credentials.validate()
        assert len(errors) > 0

    def test_validate_empty_fingerprint(self, sample_credentials: OciCredentials) -> None:
        sample_credentials.fingerprint = ""
        errors = sample_credentials.validate()
        assert any("Fingerprint" in e for e in errors)

    def test_validate_missing_private_key(self, sample_credentials: OciCredentials) -> None:
        sample_credentials.private_key = "no key here"
        errors = sample_credentials.validate()
        assert any("private key" in e for e in errors)

    def test_to_dict(self, sample_credentials: OciCredentials) -> None:
        data = sample_credentials.to_dict()
        assert data["user_ocid"] == sample_credentials.user_ocid
        assert "private_key" not in data


class TestLatencyResult:
    def test_improvement_positive(self) -> None:
        result = LatencyResult(without_tunnel_ms=100.0, with_tunnel_ms=30.0)
        assert result.improvement_ms == 70.0
        assert result.improvement_pct == 70.0

    def test_improvement_negative(self) -> None:
        result = LatencyResult(without_tunnel_ms=30.0, with_tunnel_ms=100.0)
        assert result.improvement_ms == -70.0
        assert result.improvement_pct is not None
        assert result.improvement_pct < 0

    def test_no_improvement(self) -> None:
        result = LatencyResult(without_tunnel_ms=50.0, with_tunnel_ms=50.0)
        assert result.improvement_ms == 0.0
        assert result.improvement_pct == 0.0

    def test_without_tunnel_only(self) -> None:
        result = LatencyResult(without_tunnel_ms=100.0)
        assert result.improvement_ms is None
        assert result.improvement_pct is None

    def test_none_values(self) -> None:
        result = LatencyResult()
        assert result.improvement_ms is None
        assert result.improvement_pct is None

    def test_to_dict(self) -> None:
        result = LatencyResult(without_tunnel_ms=100.0, with_tunnel_ms=30.0)
        data = result.to_dict()
        assert data["without_tunnel_ms"] == 100.0
        assert data["with_tunnel_ms"] == 30.0
        assert data["improvement_ms"] == 70.0
