"""GitHub MCP Server entry point"""
import os
import sys
import signal

# Ensure the project dir is on the path so imports work regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools import mcp


def main() -> None:
    """Run the MCP server"""
    try:
        # Handle SIGTERM gracefully for container environments
        def signal_handler(signum: int, frame: object) -> None:
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Error starting MCP server: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()