"""GitHub MCP Server entry point"""
import atexit
import os
import sys
import signal

# Ensure the project dir is on the path so imports work regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── CLI argument handling (before mcp.run() parses its own) ──
_NO_WATCH_FLAG = "--no-watch"
if _NO_WATCH_FLAG in sys.argv:
    os.environ["GITHUB_POLICY_NO_WATCH"] = "true"
    sys.argv.remove(_NO_WATCH_FLAG)

from src.tools import mcp, _stop_policy_watcher  # noqa: E402


def main() -> None:
    """Run the MCP server"""
    try:
        # Handle SIGTERM gracefully for container environments
        def signal_handler(signum: int, frame: object) -> None:
            _stop_policy_watcher()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        atexit.register(_stop_policy_watcher)
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        _stop_policy_watcher()
        sys.exit(0)
    except Exception as e:
        print(f"Error starting MCP server: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
