# Quick PCB Agent Plugin

Quick PCB packages a BoardSpec skill and four local stdio MCP servers:

- `boardspec-core`: validate, expand, and export BoardSpec without EasyEDA.
- `boardspec-library`: query normalized, read-only EasyEDA system-library candidates and full part details.
- `boardspec-layout`: checked EasyEDA Pro PCB reads and writes.
- `boardspec-schematic`: checked EasyEDA Pro schematic planning, writes, and verification.

The distributable plugin enables Core and Library by default and leaves Layout and Schematic disabled. Library needs the official EasyEDA Bridge and a connected EDA window but exposes only read-only tools. All EDA writes require tool approval in the Codex compatibility configuration.

The default workflow extracts electrical and package constraints, compares real system-library candidates with `search_parts`, verifies shortlisted parts with `get_part`, and only then creates BoardSpec definitions and instances. Part lookup never selects drawing sheets. Engineering schematic planning defaults to an adaptive A4/A3 landscape page, patches only the page's existing native `titleBlockData`, uses a module grid, and places a real same-name Net Port or power/ground Flag at every endpoint. It never places `Drawing-Symbol_*` or assembles a frame from graphics. This is a baseline project drafting convention, not a claim of full GB-standard compliance.

## Requirements

- Python 3.10 or newer
- `uv` and Git available on `PATH`
- EasyEDA Pro plus the official Bridge for Library, Layout, or Schematic tools

The MCP commands install Quick PCB from the fixed `v0.4.0` Git tag into the `uv` cache. The first start needs network access and can take several minutes; later starts use the cache.

The local v0.4.0 wheel and release bundle can be installed before publication, but fixed-tag plugin startup requires the remote `v0.4.0` tag to exist.

## Other MCP clients

Clients that support Agent Plugins 1.0 can load this directory directly through `plugin.json` and `mcp.json`. Other stdio MCP clients can copy one server entry from `mcp.json`. Library queries engineering/CAD metadata, not live price, stock, lead time, or lifecycle data.

Netlist import opens EasyEDA's review flow and returns `staged: true`; it does not mean the user applied or saved the change. Before EDA writes, read the active window, document, context revision, and document revision.
