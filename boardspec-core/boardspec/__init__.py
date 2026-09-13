"""BoardSpec: EDA-neutral declarative board connectivity DSL.

Declares what components exist and which pins share a net; deterministic tools
validate, resolve part libraries, expand modules, run conservative ERC, and
export netlists / BOM. Coordinates, routing, and symbol/footprint graphics are
deliberately out of scope.
"""

from .core import analyze, build_flat, build_resolver, expand, load_yaml, process
from .diag import diag
from .part_db import PartDB, Resolver

__all__ = [
    "analyze",
    "build_flat",
    "build_resolver",
    "diag",
    "expand",
    "load_yaml",
    "process",
    "PartDB",
    "Resolver",
]

__version__ = "0.1.0"
