"""Precision code intelligence: exact symbol navigation from a compiler-grade index."""

from codecortex.precision.generator import (
    GenerationResult,
    PrecisionGeneratorError,
    PrecisionIndexGenerator,
)
from codecortex.precision.identity import SymbolIdentity, parse_symbol
from codecortex.precision.importer import import_index, normalize_index_path
from codecortex.precision.index import (
    DEFAULT_INDEX_LOCATIONS,
    PrecisionIndexStore,
    PrecisionStatus,
    default_index_path,
)
from codecortex.precision.merge import GraphFusionReport, PrecisionGraphFusion
from codecortex.precision.models import (
    PrecisionDocument,
    PrecisionIndex,
    PrecisionIndexError,
    PrecisionOccurrence,
    PrecisionSymbol,
    SourceRange,
)
from codecortex.precision.provider import PrecisionEvidenceProvider, PrecisionQuery

__all__ = [
    "DEFAULT_INDEX_LOCATIONS",
    "GenerationResult",
    "GraphFusionReport",
    "PrecisionDocument",
    "PrecisionEvidenceProvider",
    "PrecisionGeneratorError",
    "PrecisionGraphFusion",
    "PrecisionIndex",
    "PrecisionIndexError",
    "PrecisionIndexGenerator",
    "PrecisionIndexStore",
    "PrecisionOccurrence",
    "PrecisionQuery",
    "PrecisionStatus",
    "PrecisionSymbol",
    "SourceRange",
    "SymbolIdentity",
    "default_index_path",
    "import_index",
    "normalize_index_path",
    "parse_symbol",
]
