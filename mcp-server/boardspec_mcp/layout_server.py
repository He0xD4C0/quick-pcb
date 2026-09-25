"""EasyEDA Pro PCB layout MCP entry point."""

from .profiles import create_layout_server

mcp = create_layout_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
