"""BoardSpec-only MCP entry point."""

from .profiles import create_core_server

mcp = create_core_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
