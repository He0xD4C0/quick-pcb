# Quick PCB Agent Plugin

Quick PCB packages a BoardSpec skill and three local stdio MCP servers:

- `boardspec-core`: validate, expand, and export BoardSpec without EasyEDA.
- `boardspec-layout`: checked EasyEDA Pro PCB reads and writes.
- `boardspec-schematic`: checked EasyEDA Pro schematic planning, writes, and verification.

This repository's trusted `.codex/config.toml` enables Core and disables Layout and Schematic by default. Enable an EDA service only for tasks that need the official EasyEDA Bridge. All EDA writes require tool approval in the Codex compatibility configuration.

## Requirements

- Python 3.10 or newer
- `uv` and Git available on `PATH`
- EasyEDA Pro plus the official Bridge for Layout or Schematic tools

The MCP commands install Quick PCB from the fixed `v0.3.1` Git tag into the `uv` cache. The first start needs network access and can take several minutes; later starts use the cache.

## Other MCP clients

Clients that support Agent Plugins 1.0 can load this directory directly through `plugin.json` and `mcp.json`. Other stdio MCP clients can copy one server entry from `mcp.json`. Use Core alone unless the task needs a connected EasyEDA window.

Netlist import opens EasyEDA's review flow and returns `staged: true`; it does not mean the user applied or saved the change. Before EDA writes, read the active window, document, context revision, and document revision.
