"""Measured column-encoding behaviour of real indexers.

The schema requires a conforming indexer to declare ``Document.position_encoding``
and says the value "should not be used" by new indexers. Real indexers in wide
use do not declare it at all, and they do not all use the unit the schema's own
guidance suggests for their implementation language.

Both entries below were measured, not assumed: a fixture line places a
non-ASCII character before a referenced identifier, the pinned indexer runs
over it, and the emitted column is compared against that identifier's UTF-8,
UTF-16, and code-point offsets. ``tests/test_real_index_conformance.py``
re-derives the measurement from the committed indexes, so a wrong entry here
fails a test rather than silently shifting every column on a non-ASCII line.

Where an index declares an encoding, the declaration always wins. This table is
consulted only for indexes that declare none, and only for tools it has an
entry for; anything else falls back to code points and is reported as an
assumption rather than as exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from codecortex.precision.schema import PositionEncoding


class EncodingSource(StrEnum):
    """Where the encoding used to interpret a document's columns came from."""

    #: The index declared it. Authoritative.
    DECLARED = "declared"
    #: The index declared nothing, and the producing tool's behaviour has been
    #: measured against a pinned revision at a version this entry covers.
    MEASURED = "measured-tool-behaviour"
    #: The index declared nothing and the tool is unknown. Columns are read as
    #: code points, which is right for ASCII and a guess otherwise.
    ASSUMED = "assumed-code-points"


@dataclass(frozen=True, slots=True)
class IndexerBehaviour:
    """What one indexer was measured to emit when it declared nothing."""

    tool: str
    encoding: PositionEncoding
    verified_versions: frozenset[str]
    note: str


MEASURED_INDEXERS: dict[str, IndexerBehaviour] = {
    "scip-python": IndexerBehaviour(
        tool="scip-python",
        encoding=PositionEncoding.UTF16_CODE_UNIT,
        verified_versions=frozenset({"0.6.6"}),
        note=(
            "Emits UTF-16 code-unit offsets and declares no position encoding, "
            "although the schema suggests UTF-32 for a Python indexer."
        ),
    ),
    "scip-typescript": IndexerBehaviour(
        tool="scip-typescript",
        encoding=PositionEncoding.UTF16_CODE_UNIT,
        verified_versions=frozenset({"0.4.0"}),
        note="Emits UTF-16 code-unit offsets and declares no position encoding.",
    ),
}


@dataclass(frozen=True, slots=True)
class ResolvedEncoding:
    """The encoding a document's columns will actually be read in."""

    encoding: PositionEncoding
    source: EncodingSource
    detail: str = ""

    @property
    def authoritative(self) -> bool:
        """Whether a column read in this encoding may be reported as exact.

        A declared encoding is authoritative. A measured one is authoritative
        only for a tool version the measurement covers: a later release may
        change the unit, and guessing that it did not is exactly the kind of
        silent wrongness this module exists to prevent.
        """
        return self.source in {EncodingSource.DECLARED, EncodingSource.MEASURED}


def resolve_encoding(
    declared: PositionEncoding, tool_name: str, tool_version: str
) -> ResolvedEncoding:
    """Decide how to read a document's columns."""
    if declared is not PositionEncoding.UNSPECIFIED:
        return ResolvedEncoding(declared, EncodingSource.DECLARED)

    behaviour = MEASURED_INDEXERS.get(tool_name.strip())
    if behaviour is not None and tool_version.strip() in behaviour.verified_versions:
        return ResolvedEncoding(
            behaviour.encoding,
            EncodingSource.MEASURED,
            f"{behaviour.tool} {tool_version}: {behaviour.note}",
        )

    detail = "the index declares no position encoding"
    if behaviour is not None:
        detail = (
            f"{behaviour.tool} {tool_version or '(no version)'} declares no position "
            f"encoding and is outside the measured versions "
            f"({', '.join(sorted(behaviour.verified_versions))})"
        )
    return ResolvedEncoding(PositionEncoding.UTF32_CODE_UNIT, EncodingSource.ASSUMED, detail)
