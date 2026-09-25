"""EasyEDA Pro schematic MCP entry point."""

from .profiles import create_schematic_server

mcp = create_schematic_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
