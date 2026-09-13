"""YAML 1.2 input/output helpers for BoardSpec documents."""

from __future__ import annotations

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError


def _yaml() -> YAML:
    parser = YAML(typ="safe", pure=True)
    parser.version = (1, 2)
    parser.allow_duplicate_keys = False
    return parser


def load_yaml_file(path: str):
    with open(path, encoding="utf-8") as stream:
        return _yaml().load(stream)


def load_yaml_text(text: str):
    return _yaml().load(text)


def dump_yaml(data, stream) -> None:
    writer = _yaml()
    writer.default_flow_style = False
    writer.allow_unicode = True
    writer.dump(data, stream)


def format_yaml_error(exc: YAMLError) -> str:
    mark = getattr(exc, "problem_mark", None)
    location = ""
    if mark is not None:
        location = f" at line {mark.line + 1}, column {mark.column + 1}"
    problem = getattr(exc, "problem", None) or str(exc)
    return f"invalid YAML{location}: {problem}"
