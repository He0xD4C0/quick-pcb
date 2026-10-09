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

### `search_parts(query, page=1, page_size=10)`

Return a compact table of real EasyEDA system-library candidates. The calling model must first state the electrical, rating, polarity, package, and pin constraints it is comparing. Do not hide incomplete or unverified provenance, and do not treat search rank as an engineering suitability score.

### `get_part(part_uuid, library_uuid="")`

Fetch every shortlisted candidate before creating physical definitions or instances. Return detailed pins containing `number`, `name`, and electrical `type`, plus symbol/footprint identity and an embeddable physical definition that preserves source UUIDs and raw pin types. Return `UNKNOWN_PART` rather than inventing a match. Recommend a self-built symbol only after recording that no reliable candidate satisfied the constraints.

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

For `board-spec/v0.2`, a top-level `{connect: [...]}` entry is normalized to an ordinary flat network with `net_origin: generated` and a stable `N_AUTO_<12位哈希>` name computed from the sorted expanded endpoints. Named networks carry `net_origin: explicit`. Anonymous generated names are exporter/internal identities and cannot be constraint or module-port targets.

### `export(spec_yaml, target)`

The repository core supports `kicad_netlist`, `protel2_netlist`, `bom_csv`, and `mermaid`. The small scripts bundled directly in this Skill expose only `kicad_netlist` and `bom_csv`; never report an unimplemented target as exported.

## Complete engineering-schematic workflow

Do not jump directly from a prose circuit request to `plan_schematic`. Use this order:

1. Extract explicit electrical and package constraints for each physical part.
2. Call `search_parts` for each part class and compare real candidates.
3. Call `get_part` for every shortlisted candidate; confirm pin numbers, polarity, symbol, footprint/package, and provenance.
4. Build and validate BoardSpec. Engineering planning requires `project.name`, `project.version`, `project.drawing.title`, and `project.drawing.number`; optional title-block facts are written only when supplied.
5. Call `get_eda_windows` and `get_schematic_context`, then `plan_schematic` with `engineering_basic` and `sheet_size=auto`. Use `net_annotation_policy=every_endpoint` when every endpoint needs an explicit named marker; use `sparse_named` for continuous-wire analog drawings where only explicit nets get one marker and anonymous nets get none.
6. Place components, reread revisions, and call `resolve_schematic_plan` against live pin coordinates and component bounding boxes.
7. Apply `set_schematic_page_format` from `plan.sheet`, then diff and apply the resolved wires, Net Ports, named power/ground Flags, and No Connects in revision-checked batches. The page-format write patches only the current page's existing native `titleBlockData`; it never searches for or places a drawing symbol.
8. Reread and require `verify_schematic_topology`, `verify_schematic_readability`, `verify_schematic_engineering_drawing`, and strict schematic DRC to pass. Under `every_endpoint`, every endpoint requires a same-name marker. Under `sparse_named`, every selected named network requires its one planned marker while anonymous networks are proved by continuous wires and topology readback.
9. Call `diff_schematic_plan` again and require no planned marker additions/replacements/deletions. Save only when the user explicitly requests it.

`set_schematic_page_format` uses EasyEDA's native page title-block API. It writes `Name`, `Part Number`, `Version`, optional user-supplied fields, and `Page Size`; EDA-managed `@Project Name`, `@Update Date`, `@Page No`, and `@Page Count` receive visibility settings but no caller-provided values. Structural fields such as `Symbol`, `Device`, `Border`, `Width`, and `Height` are readback-only. If native A4/A3 structure does not follow the requested page size, return `PAGE_SIZE_NOT_APPLIED`. If the API or native title block is unavailable, stop; do not draw a fake frame from generic graphics or use plain text as NET labels. A write timeout or HTTP 5xx is `WRITE_STATUS_UNKNOWN`, so reread before any retry.

### `load_netlist(netlist_text, netlist_type="PROTEL2", document_kind="pcb")`

Stage a PCB netlist import and expose the EDA preview. Staging is not Apply: review the complete reference/network/pin set first, explicitly apply it in the disposable target project, then run `get_netlist` again for deterministic comparison.

Empty payloads and PROTEL2 content without a component record are rejected before the Bridge call, so `staged: true` only means EasyEDA accepted a real import preview request.

## Deliberate limits

- The local MVP reads generic JSON databases; it does not parse KiCad or Altium libraries. A host adapter may implement those library types.
- ERC is conservative and incomplete. It detects resolvable connection conflicts and emits heuristic warnings for decoupling, pull-ups, unconnected pins, incomplete part data, and missing footprints.
- Netlist export does not create symbols, footprints, schematics, PCB layout, or routing.
- Physical package, manufacturer part number, ratings, polarity, power sequencing, clocking, reset, EMC, thermal, and layout suitability remain engineering review items unless separately verified.
