"""Column-encoding compatibility rules for precision index producers.

Declared position encodings are authoritative. When an index producer omits
that declaration, CodeCortex may apply a narrow compatibility profile keyed by
the producer's generic tool suffix and verified version. Unknown combinations
fall back to code points and are reported as assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from codecortex.precision.schema import PositionEncoding


class EncodingSource(StrEnum):
    DECLARED = "declared"
    COMPATIBILITY = "compatibility-profile"
    ASSUMED = "assumed-code-points"


@dataclass(frozen=True, slots=True)
class CompatibilityProfile:
    tool_suffix: str
    encoding: PositionEncoding
    verified_versions: frozenset[str]
    note: str


COMPATIBILITY_PROFILES: tuple[CompatibilityProfile, ...] = (
    CompatibilityProfile(
        tool_suffix="-python",
        encoding=PositionEncoding.UTF16_CODE_UNIT,
        verified_versions=frozenset({"0.6.6"}),
        note="uses UTF-16 code-unit offsets when no encoding is declared",
    ),
    CompatibilityProfile(
        tool_suffix="-typescript",
        encoding=PositionEncoding.UTF16_CODE_UNIT,
        verified_versions=frozenset({"0.4.0"}),
        note="uses UTF-16 code-unit offsets when no encoding is declared",
    ),
)


@dataclass(frozen=True, slots=True)
class ResolvedEncoding:
    encoding: PositionEncoding
    source: EncodingSource
    detail: str = ""

    @property
    def authoritative(self) -> bool:
        return self.source in {EncodingSource.DECLARED, EncodingSource.COMPATIBILITY}


def resolve_encoding(
    declared: PositionEncoding, tool_name: str, tool_version: str
) -> ResolvedEncoding:
    if declared is not PositionEncoding.UNSPECIFIED:
        return ResolvedEncoding(declared, EncodingSource.DECLARED)

    normalized = tool_name.strip().lower()
    profile = next(
        (item for item in COMPATIBILITY_PROFILES if normalized.endswith(item.tool_suffix)),
        None,
    )
    if profile is not None and tool_version.strip() in profile.verified_versions:
        return ResolvedEncoding(
            profile.encoding,
            EncodingSource.COMPATIBILITY,
            f"{tool_name or 'indexer'} {tool_version}: {profile.note}",
        )

    detail = "the index declares no position encoding"
    if profile is not None:
        detail = (
            f"{tool_name or 'indexer'} {tool_version or '(no version)'} declares no "
            f"position encoding and is outside the verified versions "
            f"({', '.join(sorted(profile.verified_versions))})"
        )
    return ResolvedEncoding(PositionEncoding.UTF32_CODE_UNIT, EncodingSource.ASSUMED, detail)
