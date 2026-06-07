"""Tests for config.py."""
import pytest

from src import config


def test_get_github_token_reads_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_token")
    assert config.get_github_token() == "ghp_token"


def test_get_github_token_raises_when_missing(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(ValueError, match="GITHUB_TOKEN not set"):
        config.get_github_token()


def test_config_defaults_and_boolean_envs(monkeypatch):
    monkeypatch.delenv("GITHUB_API_BASE", raising=False)
    monkeypatch.delenv("GITHUB_POLICY_PATH", raising=False)
    monkeypatch.delenv("GITHUB_POLICY_REQUIRED", raising=False)
    monkeypatch.delenv("GITHUB_AUDIT_LOG", raising=False)
    monkeypatch.delenv("GITHUB_DRY_RUN", raising=False)

    assert config.get_github_api_base() == "https://api.github.com"
    assert config.get_policy_path() == "policy.json"
    assert config.get_policy_required() is False
    assert config.get_audit_sink() == "stdout"
    assert config.get_dry_run_enabled() is False

    monkeypatch.setenv("GITHUB_API_BASE", "https://api.example")
    monkeypatch.setenv("GITHUB_POLICY_PATH", "/tmp/policy.json")
    monkeypatch.setenv("GITHUB_POLICY_REQUIRED", "yes")
    monkeypatch.setenv("GITHUB_AUDIT_LOG", "stderr")
    monkeypatch.setenv("GITHUB_DRY_RUN", "1")

    assert config.get_github_api_base() == "https://api.example"
    assert config.get_policy_path() == "/tmp/policy.json"
    assert config.get_policy_required() is True
    assert config.get_audit_sink() == "stderr"
    assert config.get_dry_run_enabled() is True
