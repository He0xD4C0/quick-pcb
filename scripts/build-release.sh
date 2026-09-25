#!/bin/sh

set -eu

usage() {
  printf '%s\n' "Usage: $0 [--allow-dirty]"
}

allow_dirty=false
case "${1:-}" in
  "") ;;
  --allow-dirty) allow_dirty=true ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
cd "$repo_dir"

for command_name in git npm shasum tar; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$command_name" >&2
    exit 1
  fi
done

core_python="$repo_dir/boardspec-core/.venv/bin/python"
mcp_python="$repo_dir/mcp-server/.venv/bin/python"
if [ ! -x "$core_python" ] || [ ! -x "$mcp_python" ]; then
  printf '%s\n' 'Missing development environments. Follow README.md -> Development environment first.' >&2
  exit 1
fi

release_version=$(tr -d '[:space:]' < "$repo_dir/VERSION")
case "$release_version" in
  ""|*[!0-9A-Za-z.-]*)
    printf 'Invalid release version in VERSION: %s\n' "$release_version" >&2
    exit 1
    ;;
esac

dirty=false
if [ -n "$(git status --short)" ]; then
  dirty=true
  if [ "$allow_dirty" != true ]; then
    printf '%s\n' 'The worktree is dirty. Commit or remove pending files first, or use --allow-dirty for a non-publishable test build.' >&2
    exit 1
  fi
fi

core_version=$(sed -n 's/^version = "\([^"]*\)"/\1/p' boardspec-core/pyproject.toml | sed -n '1p')
mcp_version=$(sed -n 's/^version = "\([^"]*\)"/\1/p' mcp-server/pyproject.toml | sed -n '1p')
extension_version=$(
  "$core_python" -c 'import json; print(json.load(open("eda-extension/extension.json", encoding="utf-8"))["version"])'
)
plugin_version=$(
  "$core_python" -c 'import json; print(json.load(open("plugins/quick-pcb/plugin.json", encoding="utf-8"))["version"])'
)
if [ "$mcp_version" != "$release_version" ] || [ "$plugin_version" != "$release_version" ]; then
  printf 'Release, MCP, and plugin versions must match: release=%s mcp=%s plugin=%s\n' \
    "$release_version" "$mcp_version" "$plugin_version" >&2
  exit 1
fi

bundle_name="quick-pcb-v$release_version"
release_dir="$repo_dir/release"
bundle_dir="$release_dir/$bundle_name"
archive_path="$release_dir/$bundle_name.tar.gz"
plugin_archive="$release_dir/quick-pcb-plugin-v$release_version.zip"
release_sums="$release_dir/SHA256SUMS"

if [ -e "$bundle_dir" ] || [ -e "$archive_path" ] || [ -e "$plugin_archive" ] || [ -e "$release_sums" ]; then
  printf 'Release output already exists for v%s. Remove these exact outputs before rebuilding:\n' "$release_version" >&2
  printf '  %s\n  %s\n  %s\n  %s\n' "$bundle_dir" "$archive_path" "$plugin_archive" "$release_sums" >&2
  exit 1
fi

mkdir -p "$bundle_dir/python" "$bundle_dir/extension" "$bundle_dir/source" "$bundle_dir/plugin"

printf '%s\n' 'Running Python tests...'
"$core_python" -m pytest boardspec-core/tests
"$mcp_python" -m pytest mcp-server/tests

printf '%s\n' 'Checking and packaging the EDA extension...'
npm --prefix eda-extension run lint
npm --prefix eda-extension run build

printf '%s\n' 'Building Python wheels...'
"$core_python" -m pip wheel --disable-pip-version-check --no-deps \
  --wheel-dir "$bundle_dir/python" ./boardspec-core
"$core_python" -m pip wheel --disable-pip-version-check --no-deps \
  --wheel-dir "$bundle_dir/python" ./mcp-server

extension_file="eda-extension/build/dist/boardspec-eda-extension_v$extension_version.eext"
if [ ! -f "$extension_file" ]; then
  printf 'Expected extension artifact was not created: %s\n' "$extension_file" >&2
  exit 1
fi
cp "$extension_file" "$bundle_dir/extension/"
cp README.md "$bundle_dir/README.md"
cp -R plugins/quick-pcb "$bundle_dir/plugin/"

commit=$(git rev-parse HEAD)
source_archive="$bundle_dir/source/$bundle_name-source.tar.gz"
git archive --format=tar.gz --prefix="$bundle_name/" HEAD > "$source_archive"

{
  printf 'release=%s\n' "$release_version"
  printf 'commit=%s\n' "$commit"
  printf 'dirty=%s\n' "$dirty"
  printf 'boardspec-core=%s\n' "$core_version"
  printf 'boardspec-mcp=%s\n' "$mcp_version"
  printf 'quick-pcb-plugin=%s\n' "$plugin_version"
  printf 'boardspec-eda-extension=%s\n' "$extension_version"
  printf 'python=%s\n' "$("$core_python" --version 2>&1)"
  printf 'node=%s\n' "$(node --version)"
} > "$bundle_dir/RELEASE-MANIFEST.txt"

: > "$bundle_dir/SHA256SUMS"
for artifact in \
  "$bundle_dir"/python/*.whl \
  "$bundle_dir"/extension/*.eext \
  "$bundle_dir"/source/*.tar.gz; do
  relative_path=${artifact#"$bundle_dir/"}
  (cd "$bundle_dir" && shasum -a 256 "$relative_path") >> "$bundle_dir/SHA256SUMS"
done

tar -czf "$archive_path" -C "$release_dir" "$bundle_name"
"$core_python" - "$bundle_dir/plugin/quick-pcb" "$plugin_archive" <<'PY'
from pathlib import Path
import sys
import zipfile

source = Path(sys.argv[1])
target = Path(sys.argv[2])
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob("*")):
        if path.is_file():
            archive.write(path, Path("quick-pcb") / path.relative_to(source))
PY

: > "$release_sums"
for artifact in "$archive_path" "$plugin_archive"; do
  (cd "$release_dir" && shasum -a 256 "$(basename "$artifact")") >> "$release_sums"
done

printf '\nRelease created:\n'
printf '  %s\n' "$archive_path"
printf '  %s\n' "$plugin_archive"
printf '  %s\n' "$release_sums"
printf '\nComponents:\n'
printf '  boardspec-core %s\n' "$core_version"
printf '  boardspec-mcp %s\n' "$mcp_version"
printf '  quick-pcb-plugin %s\n' "$plugin_version"
printf '  boardspec-eda-extension %s\n' "$extension_version"
printf '  source commit %s\n' "$commit"
printf '  dirty %s\n' "$dirty"
