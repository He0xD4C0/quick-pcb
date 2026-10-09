"""Read-only EasyEDA system-library MCP entry point."""

from .profiles import create_library_server

mcp = create_library_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
