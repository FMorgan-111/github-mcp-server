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
