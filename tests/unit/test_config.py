"""Unit tests for configuration loading."""

from pathlib import Path

import pytest

from huehub.config import HueConfig, _apply_toml, load_config, save_config


class TestLoadConfig:
    def test_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HUE_CONFIG_DIR", str(tmp_path))
        cfg = load_config()
        assert cfg.bridge.host is None
        assert cfg.tls.mode == "auto"
        assert cfg.connection.request_timeout_s == 10
        assert cfg.cache.ttl_seconds == 300

    def test_cli_host_override(self) -> None:
        cfg = load_config(host="10.0.0.1")
        assert cfg.bridge.host == "10.0.0.1"

    def test_cli_key_override(self) -> None:
        cfg = load_config(application_key="my-key")
        assert cfg.bridge.application_key == "my-key"

    def test_env_host_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HUE_BRIDGE_HOST", "192.168.0.99")
        cfg = load_config()
        assert cfg.bridge.host == "192.168.0.99"

    def test_env_key_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HUE_APPLICATION_KEY", "env-key")
        cfg = load_config()
        assert cfg.bridge.application_key == "env-key"

    def test_env_tls_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HUE_TLS_MODE", "skip")
        cfg = load_config()
        assert cfg.tls.mode == "skip"

    def test_cli_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HUE_BRIDGE_HOST", "192.168.0.1")
        cfg = load_config(host="10.0.0.2")
        assert cfg.bridge.host == "10.0.0.2"

    def test_custom_config_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HUE_CONFIG_DIR", str(tmp_path))
        cfg = load_config()
        assert cfg.config_path == tmp_path / "config.toml"


class TestSaveAndReload:
    def test_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HUE_CONFIG_DIR", str(tmp_path))
        cfg = load_config(host="192.168.1.42", application_key="key-abc")
        save_config(cfg)

        toml_path = tmp_path / "config.toml"
        assert toml_path.exists()

        # Re-load and verify
        cfg2 = load_config()
        assert cfg2.bridge.host == "192.168.1.42"
        assert cfg2.bridge.application_key == "key-abc"

    def test_save_creates_dir(self, tmp_path: Path) -> None:
        cfg = HueConfig()
        cfg.bridge.host = "1.2.3.4"
        cfg.config_path = tmp_path / "subdir" / "config.toml"
        save_config(cfg)
        assert cfg.config_path.exists()


class TestApplyToml:
    def test_apply_bridge_section(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[bridge]\nhost = "10.0.0.1"\napplication_key = "abc"\n')
        cfg = HueConfig()
        _apply_toml(cfg, toml_file)
        assert cfg.bridge.host == "10.0.0.1"
        assert cfg.bridge.application_key == "abc"

    def test_apply_tls_section(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[tls]\nmode = "skip"\n')
        cfg = HueConfig()
        _apply_toml(cfg, toml_file)
        assert cfg.tls.mode == "skip"

    def test_apply_colors_section(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[colors]\nkino = "#1A1A2E"\n')
        cfg = HueConfig()
        _apply_toml(cfg, toml_file)
        assert cfg.colors["kino"] == "#1A1A2E"
