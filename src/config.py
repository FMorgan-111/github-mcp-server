"""GitHub MCP Agent — configuration"""
import os
from dotenv import load_dotenv

load_dotenv()


def get_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError(
            "GITHUB_TOKEN not set. "
            "Create a .env file with GITHUB_TOKEN=ghp_xxx "
            "or set the environment variable."
        )
    return token


def get_github_api_base() -> str:
    return os.environ.get("GITHUB_API_BASE", "https://api.github.com")


def get_policy_path() -> str:
    return os.environ.get("GITHUB_POLICY_PATH", "policy.json")


def get_policy_required() -> bool:
    return os.environ.get("GITHUB_POLICY_REQUIRED", "").lower() in ("true", "1", "yes")


def get_audit_sink() -> str:
    return os.environ.get("GITHUB_AUDIT_LOG", "stdout")


def get_dry_run_enabled() -> bool:
    return os.environ.get("GITHUB_DRY_RUN", "").lower() in ("true", "1", "yes")


def get_policy_no_watch() -> bool:
    return os.environ.get("GITHUB_POLICY_NO_WATCH", "").lower() in ("true", "1", "yes")
