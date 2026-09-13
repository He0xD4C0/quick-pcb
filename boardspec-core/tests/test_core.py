"""Tests for BoardSpec core: schema, expansion, ERC, and exporters."""

from __future__ import annotations

import os

import pytest

from boardspec.core import process
from boardspec.exporters import (
    parse_protel2_netlist,
    render_bom_csv,
    render_kicad_netlist,
    render_mermaid,
    render_protel2_netlist,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
STATUS_LED = os.path.join(FIXTURES, "status-led.yaml")
E2E_MOSFET_LED = os.path.abspath(
    os.path.join(FIXTURES, "..", "..", "..", "examples", "boardspec-e2e-mosfet-led.yaml")
)


def _process(path):
    return process(path)


def test_status_led_validates_clean():
    _, expanded, _, errors, warnings = _process(STATUS_LED)
    assert errors == []
    # Expected demo-fixture warnings, not errors.
    codes = {w["code"] for w in warnings}
    assert codes >= {"INCOMPLETE_PART_DATA", "FOOTPRINT_UNCONFIRMED"}


def test_module_expansion_namespaces():
    _, expanded, _, _, _ = _process(STATUS_LED)
    insts = expanded["instances"]
    # The module instance LED1 is flattened into LED1/R and LED1/D.
    assert "LED1" not in insts
    assert "LED1/R" in insts
    assert "LED1/D" in insts
    assert insts["LED1/R"]["part"] == "Device:R"
    assert insts["LED1/R"]["value"] == "2.2k"  # parameter substitution
    assert insts["LED1/D"]["part"] == "Device:LED"
    assert expanded["reference_map"] == {
        "C1": "C1",
        "LED1/D": "LED1",
        "LED1/R": "R1",
        "U1": "U1",
    }


def test_expansion_resolves_port_endpoints():
    _, expanded, _, _, _ = _process(STATUS_LED)
    nets = {c["net"]: c["endpoints"] for c in expanded["connections"]}
    assert "LED1.VCC" not in nets["3V3"]
    # Module port VCC mapped to R.2 inside the module.
    assert "LED1/R.2" in nets["3V3"]
    assert "LED1/D.K" in nets["GND"]


def test_protel2_netlist_export():
    _, expanded, resolver, _, _ = _process(STATUS_LED)
    out = render_protel2_netlist(expanded, resolver)
    assert out.startswith("PROTEL NETLIST 2.0\n[\nDESIGNATOR\n")
    assert "U1"
    assert "3V3"
    assert "U1-24" in out  # VDD pin 24
    assert "U1-24 STM32F103C8T6-VDD POWER" in out
    assert "("
    assert ")"
    assert out.endswith("\n")
    parsed = parse_protel2_netlist(out)
    assert set(parsed["components"]) == {"C1", "LED1", "R1", "U1"}
    assert ("U1", "24") in parsed["nets"]["3V3"]


def test_bom_csv_export():
    _, expanded, resolver, _, _ = _process(STATUS_LED)
    out = render_bom_csv(expanded, resolver)
    header = out.splitlines()[0]
    assert header == (
        "reference,logical_path,value,part,footprint,supplier_id,description,dnp"
    )
    assert "R1,LED1/R" in out
    assert "LED1,LED1/D" in out


def test_kicad_netlist_export():
    _, expanded, resolver, _, _ = _process(STATUS_LED)
    out = render_kicad_netlist(expanded, resolver)
    assert out.startswith("(export (version D)")
    assert "(comp (ref \"U1\")" in out
    assert "(net (code \"\") (name \"3V3\")" in out


def test_mermaid_export():
    _, expanded, resolver, _, _ = _process(STATUS_LED)
    out = render_mermaid(expanded, resolver)
    assert out.startswith("graph LR")
    assert "3V3" in out


def test_unknown_pin_is_error(tmp_path):
    spec = """\
spec: board-spec/v0.1
project:
  name: bad
libraries:
  - id: demo
    type: generic
    path: {db}
instances:
  R1:
    part: Device:R
connections:
  - net: N
    endpoints: [R1.99]
""".format(
        db=os.path.join(FIXTURES, "parts.demo.json")
    )
    p = tmp_path / "bad.yaml"
    p.write_text(spec, encoding="utf-8")
    _, _, _, errors, _ = _process(str(p))
    assert any(e["code"] == "UNKNOWN_PIN" for e in errors)


def test_duplicate_net_is_error(tmp_path):
    spec = """\
spec: board-spec/v0.1
project:
  name: bad
libraries:
  - id: demo
    type: generic
    path: {db}
instances:
  R1:
    part: Device:R
  R2:
    part: Device:R
connections:
  - net: N
    endpoints: [R1.1, R2.1]
  - net: N
    endpoints: [R1.2, R2.2]
""".format(
        db=os.path.join(FIXTURES, "parts.demo.json")
    )
    p = tmp_path / "dup.yaml"
    p.write_text(spec, encoding="utf-8")
    _, _, _, errors, _ = _process(str(p))
    assert any(e["code"] == "DUPLICATE_NET" for e in errors)


def test_yaml_12_plain_on_is_a_string(tmp_path):
    spec = """\
spec: board-spec/v0.1
project:
  name: yaml-12
libraries:
  - id: demo
    type: generic
    path: {db}
instances:
  R1:
    part: Device:R
connections:
  - net: ON
    endpoints: [R1.1]
outputs:
  - type: protel2_netlist
""".format(
        db=os.path.join(FIXTURES, "parts.demo.json")
    )
    p = tmp_path / "yaml-12.yaml"
    p.write_text(spec, encoding="utf-8")

    _, expanded, _, errors, _ = _process(str(p))

    assert errors == []
    assert expanded["connections"][0]["net"] == "ON"
    assert expanded["outputs"][0]["type"] == "protel2_netlist"


def test_malformed_yaml_returns_structured_diagnostic(tmp_path):
    p = tmp_path / "malformed.yaml"
    p.write_text("spec: [", encoding="utf-8")

    _, expanded, resolver, errors, warnings = _process(str(p))

    assert expanded is None
    assert resolver is None
    assert warnings == []
    assert errors[0]["code"] == "SCHEMA_INVALID"
    assert errors[0]["path"] == "/"
    assert "line 1" in errors[0]["message"]


def test_duplicate_yaml_key_is_rejected(tmp_path):
    p = tmp_path / "duplicate-key.yaml"
    p.write_text(
        """\
spec: board-spec/v0.1
project: {name: first, name: second}
instances: {}
connections: []
""",
        encoding="utf-8",
    )

    _, _, _, errors, _ = _process(str(p))

    assert errors[0]["code"] == "SCHEMA_INVALID"
    assert "duplicate key" in errors[0]["message"]


def test_reviewed_physical_part_accepts_explicit_no_connect(tmp_path):
    p = tmp_path / "no-connect.yaml"
    p.write_text(
        """\
spec: board-spec/v0.1
project: {name: no-connect}
definitions:
  project:Thing:
    kind: physical
    reference_prefix: U
    pins:
      - {number: "1", name: OUT, type: output}
      - {number: "2", name: UNUSED, type: unspecified}
    footprint: TEST
    review: {status: project_reviewed, pin_type_authority: project_library}
instances:
  U1:
    part: project:Thing
    no_connects: ["#2"]
connections:
  - {net: N, endpoints: [U1.#1]}
""",
        encoding="utf-8",
    )

    _, expanded, _, errors, warnings = _process(str(p))

    assert errors == []
    assert warnings == []
    assert expanded["instances"]["U1"]["no_connects"] == ["#2"]


def test_connected_and_no_connect_pin_is_error(tmp_path):
    p = tmp_path / "conflicting-no-connect.yaml"
    p.write_text(
        """\
spec: board-spec/v0.1
project: {name: conflicting-no-connect}
definitions:
  project:Thing:
    kind: physical
    pins:
      - {number: "1", name: IO, type: bidirectional}
    footprint: TEST
instances:
  U1: {part: project:Thing, no_connects: ["#1"]}
connections:
  - {net: N, endpoints: [U1.#1]}
""",
        encoding="utf-8",
    )

    _, _, _, errors, _ = _process(str(p))

    assert any(e["code"] == "PIN_CONNECTED_AND_NO_CONNECT" for e in errors)


def test_duplicate_no_connect_pin_is_schema_error(tmp_path):
    p = tmp_path / "duplicate-no-connect.yaml"
    p.write_text(
        """\
spec: board-spec/v0.1
project: {name: duplicate-no-connect}
definitions:
  project:Thing:
    kind: physical
    pins:
      - {number: "1", name: IO, type: passive}
    footprint: TEST
instances:
  U1: {part: project:Thing, no_connects: ["#1", "#1"]}
connections: []
""",
        encoding="utf-8",
    )

    _, _, _, errors, _ = _process(str(p))

    assert any(e["code"] == "SCHEMA_INVALID" for e in errors)


def test_unknown_no_connect_pin_is_error(tmp_path):
    p = tmp_path / "unknown-no-connect.yaml"
    p.write_text(
        """\
spec: board-spec/v0.1
project: {name: unknown-no-connect}
definitions:
  project:Thing:
    kind: physical
    pins:
      - {number: "1", name: IO, type: passive}
    footprint: TEST
instances:
  U1: {part: project:Thing, no_connects: ["#2"]}
connections: []
""",
        encoding="utf-8",
    )

    _, _, _, errors, _ = _process(str(p))

    assert any(e["code"] == "UNKNOWN_PIN" for e in errors)


def test_connected_unspecified_pin_is_error(tmp_path):
    p = tmp_path / "unspecified.yaml"
    p.write_text(
        """\
spec: board-spec/v0.1
project: {name: unspecified}
definitions:
  project:Thing:
    kind: physical
    pins:
      - {number: "1", name: IO, type: unspecified}
    footprint: TEST
instances:
  U1: {part: project:Thing}
connections:
  - {net: N, endpoints: [U1.#1]}
""",
        encoding="utf-8",
    )

    _, _, _, errors, _ = _process(str(p))

    assert any(e["code"] == "UNSPECIFIED_PIN_CONNECTED" for e in errors)


def test_e2e_fixture_has_exact_physical_refs_and_supplier_ids():
    _, expanded, resolver, errors, warnings = _process(E2E_MOSFET_LED)

    assert errors == []
    assert warnings == []
    assert expanded["reference_map"] == {
        "C1": "C1",
        "C2": "C2",
        "C3": "C3",
        "C4": "C4",
        "C5": "C5",
        "J1": "J1",
        "STATUS1/LED": "LED1",
        "STATUS1/Q": "Q1",
        "STATUS1/R_LED": "R1",
        "STATUS1/R_PD": "R2",
        "U1": "U1",
    }
    bom = render_bom_csv(expanded, resolver)
    for supplier_id in (
        "C8734",
        "C49661",
        "C82153",
        "C8545",
        "C25879",
        "C25741",
        "C9900003727",
    ):
        assert supplier_id in bom
    assert len(bom.splitlines()) == 12


def test_protel2_golden_file(tmp_path):
    p = tmp_path / "golden.yaml"
    p.write_text(
        """\
spec: board-spec/v0.1
project: {name: golden}
definitions:
  project:R:
    kind: physical
    reference_prefix: R
    description: Resistor
    footprint: R0402
    pins:
      - {number: "1", name: "1", type: passive}
    source:
      provider: fixture
      device_name: R_DEV
      symbol_name: R_SYM
      supplier: LCSC
      supplier_id: C1
      manufacturer: Resistors Inc
      manufacturer_part_number: R-1K
instances:
  R1: {part: project:R, value: 1k}
connections:
  - {net: N, endpoints: [R1.#1]}
""",
        encoding="utf-8",
    )
    _, expanded, resolver, errors, warnings = _process(str(p))

    assert errors == []
    assert warnings == []
    expected_path = os.path.join(FIXTURES, "..", "golden", "protel2-minimal.net")
    with open(expected_path, encoding="utf-8") as stream:
        expected = stream.read()
    assert render_protel2_netlist(expanded, resolver) == expected
