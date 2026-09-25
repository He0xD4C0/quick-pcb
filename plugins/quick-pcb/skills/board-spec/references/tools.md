# BoardSpec tools and CLI contract

Read this file only when a task needs part lookup, validation, module expansion, or export.

## Runtime

The bundled MVP scripts require Python 3.10+ and the packages pinned by range in `scripts/requirements.txt`. Install those dependencies in an isolated environment. The scripts never install packages automatically. BoardSpec input is parsed with `ruamel.yaml` in YAML 1.2 mode; duplicate mapping keys are rejected.

All relative library paths and output paths are resolved from the input BoardSpec file's directory. A `generic` library must use the JSON layout demonstrated by `parts.demo.json`. The bundled demo database is not an engineering authority.

## Structured diagnostics

Validation prints one JSON object to stdout:

```json
{
  "ok": false,
  "errors": [
    {
      "code": "UNKNOWN_PIN",
      "path": "/connections/2/endpoints/1",
      "message": "U1.PA5 was not found",
      "hint": "Available logical pin names: PA0, PA1"
    }
  ],
  "warnings": []
}
```

An error yields a non-zero exit status. Warnings preserve a zero status but must be reported to the user.

## CLI

Run commands from any directory; paths below are relative to the Skill root.

```bash
python3 scripts/part_db.py search STM32F103 --db references/parts.demo.json --limit 10
python3 scripts/part_db.py get MCU:STM32F103C8T6 --db references/parts.demo.json
python3 scripts/validate.py examples/status-led.yaml
python3 scripts/expand.py examples/status-led.yaml --output /tmp/status-led.expanded.yaml
python3 scripts/export_bom.py examples/status-led.yaml --output /tmp/status-led.csv
python3 scripts/export_kicad_netlist.py examples/status-led.yaml --output /tmp/status-led.net
```

`validate.py`, `expand.py`, and both exporters accept repeatable `--part-db PATH` arguments. Explicit databases override entries with the same identifier loaded from `libraries[].type: generic`.

The KiCad exporter emits a legacy Eeschema S-expression netlist exchange file, not a `.kicad_sch` project. Treat import into the target KiCad version as a separate verification step.

## Endpoint resolution

- `U1.PA5` selects every physical pin named `PA5`.
- `U1.VDD` intentionally selects every physical pin sharing the logical name `VDD`.
- `U1.#24` selects physical pin number `24` only.
- Expanded module instances use paths such as `LED1/R.1`.

## Logical tool contract

Hosts may expose equivalent functions instead of the CLI. Preserve these request/response shapes.

### `search_part(query, library?, limit?)`

Return a list of candidate objects with `part_id`, `description`, logical `pins`, `power_pins`, `footprint`, `source`, and `complete`. Do not hide incomplete or unverified provenance.

### `get_part(part_id)`

Return the same metadata plus detailed pins containing `number`, `name`, and electrical `type`, and an embeddable physical definition that preserves source UUIDs and raw pin types. Return `UNKNOWN_PART` rather than inventing a match.

### `get_project_component(designator)`

Read one uniquely matching placed schematic component, including live device/symbol/footprint UUIDs, pin numbers, reviewed electrical types, and No Connect flags.

### `get_netlist(netlist_type="PROTEL2", document_kind="schematic")`

Read the current schematic or PCB netlist without mutation. Use the PCB form after Apply to compare the EDA result against the expanded BoardSpec graph.

### `set_no_connects(designator, pin_selectors, apply=false)`

Accept exact `#PIN_NUMBER` selectors only. Preview by default; mutate only when `apply=true`, then read back every requested pin.

### `run_schematic_drc()` / `run_pcb_drc()`

Run strict DRC in the current document and return structured violations. An unrouted PCB is expected to retain physical connection errors; do not describe those as an electrically complete board.

### `validate(spec_yaml)`

Return `{ok, errors, warnings}`. Schema-only success is not enough when part or pin resolution was skipped.

### `expand(spec_yaml)`

Recursively flatten `definitions.kind: module`. Hierarchical instances use `PARENT/CHILD`; module ports are replaced by their mapped internal endpoints. Return the expanded specification and diagnostics.

The expanded result includes `reference_map`, a deterministic logical-path to physical-reference mapping. Module leaf parts require `reference_prefix`; top-level physical instance keys must already be legal EDA references.

### `export(spec_yaml, target)`

The repository core supports `kicad_netlist`, `protel2_netlist`, `bom_csv`, and `mermaid`. The small scripts bundled directly in this Skill expose only `kicad_netlist` and `bom_csv`; never report an unimplemented target as exported.

### `load_netlist(netlist_text, netlist_type="PROTEL2", document_kind="pcb")`

Stage a PCB netlist import and expose the EDA preview. Staging is not Apply: review the complete reference/network/pin set first, explicitly apply it in the disposable target project, then run `get_netlist` again for deterministic comparison.

Empty payloads and PROTEL2 content without a component record are rejected before the Bridge call, so `staged: true` only means EasyEDA accepted a real import preview request.

## Deliberate limits

- The local MVP reads generic JSON databases; it does not parse KiCad or Altium libraries. A host adapter may implement those library types.
- ERC is conservative and incomplete. It detects resolvable connection conflicts and emits heuristic warnings for decoupling, pull-ups, unconnected pins, incomplete part data, and missing footprints.
- Netlist export does not create symbols, footprints, schematics, PCB layout, or routing.
- Physical package, manufacturer part number, ratings, polarity, power sequencing, clocking, reset, EMC, thermal, and layout suitability remain engineering review items unless separately verified.
