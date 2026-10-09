#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
py="${QPCB_PYTHON:-$here/.venv/bin/python}"
command -v ngspice >/dev/null
"$py" "$here/scripts/fit_tube.py"
"$py" "$here/scripts/build_circuit.py"
"$py" "$here/scripts/simulate_audio.py"
"$py" "$here/scripts/simulate_limits.py"
"$py" "$here/scripts/simulate_power.py"
"$py" "$here/scripts/simulate_sweeps.py"
"$py" "$here/scripts/summarize_ripple.py"
"$py" "$here/scripts/simulate_protection.py"
"$py" "$here/scripts/simulate_startup.py"
"$py" "$here/scripts/simulate_overload.py"
"$py" "$here/scripts/simulate_stereo.py"
"$py" "$here/scripts/build_schematic.py"
"$py" "$here/scripts/verify_artifacts.py"
"$py" "$here/scripts/build_report.py"
