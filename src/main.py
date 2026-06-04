"""GitHub MCP Server entry point"""
import os, sys
# Ensure the project dir is on the path so imports work regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools import mcp


def main():
    """Run the MCP server"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()