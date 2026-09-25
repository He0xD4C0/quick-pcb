#!/usr/bin/env python3
"""Verify the checked-in QuickPCB v0.3.1 acceptance example."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / "boardspec-core"))

from boardspec import process  # noqa: E402
from boardspec.exporters.netlist_protel2 import parse_protel2_netlist  # noqa: E402

EXPECTED_REFS = {"C1", "J1", "J2", "J3", "LED1", "Q1", "R1", "R2", "R3"}
EXPECTED_NETS = {"5V", "GND", "LED_A", "LED_K_SW", "CTRL_IN", "GATE"}
MANUFACTURING = ROOT / "manufacturing"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def xlsx_rows(path: Path) -> list[list[str]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        archive.testzip()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", ns):
                shared.append("".join(node.text or "" for node in item.iterfind(".//m:t", ns)))
        sheet_name = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet"))[0]
        root = ET.fromstring(archive.read(sheet_name))
        rows: list[list[str]] = []
        for row in root.findall(".//m:sheetData/m:row", ns):
            values: list[str] = []
            for cell in row.findall("m:c", ns):
                cell_type = cell.attrib.get("t")
                value = cell.find("m:v", ns)
                inline = cell.find("m:is", ns)
                text = ""
                if cell_type == "s" and value is not None:
                    text = shared[int(value.text or 0)]
                elif inline is not None:
                    text = "".join(node.text or "" for node in inline.iterfind(".//m:t", ns))
                elif value is not None:
                    text = value.text or ""
                values.append(text)
            rows.append(values)
        return rows


def main() -> int:
    spec_path = ROOT / "QuickPCB_5V_MOSFET_LED_Demo.yaml"
    _, expanded, _, errors, warnings = process(str(spec_path))
    check(not errors, f"BoardSpec errors: {errors}")
    check(not warnings, f"BoardSpec warnings: {warnings}")
    check(set(expanded["instances"]) == EXPECTED_REFS, "BoardSpec component set differs")
    check({row["net"] for row in expanded["connections"]} == EXPECTED_NETS, "BoardSpec net set differs")
    check(sum(len(row["endpoints"]) for row in expanded["connections"]) == 19, "BoardSpec node count differs")

    netlist = parse_protel2_netlist((ROOT / "generated/QuickPCB_5V_MOSFET_LED_Demo-live.net").read_text())
    check(set(netlist["components"]) == EXPECTED_REFS, "generated netlist component set differs")
    check(set(netlist["nets"]) == EXPECTED_NETS, "generated netlist net set differs")
    check(sum(map(len, netlist["nets"].values())) == 19, "generated netlist node count differs")

    with (ROOT / "generated/QuickPCB_5V_MOSFET_LED_Demo-bom.csv").open(newline="") as handle:
        bom_refs = {row["reference"] for row in csv.DictReader(handle)}
    check(bom_refs == EXPECTED_REFS, "generated BOM CSV component set differs")

    project = ROOT / "QuickPCB_5V_MOSFET_LED_Demo_v031.eprj2"
    connection = sqlite3.connect(project)
    check(connection.execute("pragma integrity_check").fetchone()[0] == "ok", "native project database is corrupt")
    connection.close()

    bom_rows = xlsx_rows(MANUFACTURING / "QuickPCB_5V_MOSFET_LED_Demo-BOM.xlsx")
    check(sum(int(row[1]) for row in bom_rows[1:] if len(row) > 1 and row[1].isdigit()) == 9, "EasyEDA BOM quantity differs")
    cpl_rows = xlsx_rows(MANUFACTURING / "QuickPCB_5V_MOSFET_LED_Demo-CPL.xlsx")
    check({row[0] for row in cpl_rows[1:] if row} == EXPECTED_REFS, "CPL component set differs")

    with zipfile.ZipFile(MANUFACTURING / "QuickPCB_5V_MOSFET_LED_Demo-Gerber.zip") as archive:
        check(archive.testzip() is None, "Gerber archive is corrupt")
        members = set(archive.namelist())
    required = {
        "Gerber_TopLayer.GTL", "Gerber_BottomLayer.GBL", "Gerber_TopSilkscreenLayer.GTO",
        "Gerber_TopSolderMaskLayer.GTS", "Gerber_BottomSolderMaskLayer.GBS",
        "Gerber_BoardOutlineLayer.GKO", "Drill_PTH_Through.DRL", "FlyingProbeTesting.json",
    }
    check(required <= members, f"Gerber members missing: {sorted(required - members)}")
    check((MANUFACTURING / "QuickPCB_5V_MOSFET_LED_Demo-Schematic.pdf").read_bytes().startswith(b"%PDF"), "schematic PDF invalid")
    check((MANUFACTURING / "QuickPCB_5V_MOSFET_LED_Demo-PCB.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), "PCB PNG invalid")

    acceptance = json.loads((ROOT / "acceptance/verification.json").read_text())
    check(acceptance["schematic"]["strict_drc_violations"] == 0, "schematic DRC evidence failed")
    check(acceptance["pcb"]["strict_drc_violations"] == 0, "PCB DRC evidence failed")
    check(acceptance["pcb"]["native_drc_problems"] == 0, "native PCB DRC evidence failed")
    check(acceptance["roundtrip"]["passed"], "BoardSpec-to-PCB roundtrip evidence failed")

    manifest = {}
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        manifest[name] = digest
    for name, digest in manifest.items():
        check(sha256(ROOT / name) == digest, f"SHA-256 mismatch: {name}")

    print("PASS: QuickPCB 5 V MOSFET LED example integrity and acceptance checks")
    print("9 components, 6 nets, 19 nodes; schematic DRC 0; PCB DRC 0")
    print("Physical bench test: pending fabricated hardware; see TESTING.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
