"""Match a resolved dependency version against the versions a provider offers.

The provider publishes a list of version labels per library and accepts a
pinned library id in either ``/owner/repo/<version>`` or ``/owner/repo@<version>``
form. Its labels and a lockfile's versions are written differently — ``v15.1.8``
against ``15.1.8``, ``=1.2.3`` against ``1.2.3`` — so a literal comparison
reports "no match" for versions that plainly are the same one.

Normalisation here is deliberately narrow. It strips presentation (a leading
``v``, an ``=`` pin operator, surrounding whitespace) and nothing else. In
particular a prerelease or build suffix is preserved in full: ``2.0.0-rc.1`` is
not ``2.0.0``, and quietly treating it as such would return documentation for
an API the repository does not run.

Whether documentation is exact-version evidence or a fallback is decided here
and recorded, so that ranking can tell the two apart instead of assuming.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

#: Leading pin operators a manifest may carry on an otherwise exact version.
_PIN_PREFIX = re.compile(r"^(==|=|v|V)+")

#: Trailing metadata a provider label may carry that a lockfile version will not.
_TRAILING_NOISE = re.compile(r"[\s]+$")


class VersionMatch(StrEnum):
    """How closely the documentation matches the version in the repository."""

    #: The provider offers exactly this version.
    EXACT = "exact"
    #: The provider offers the same release under a different spelling.
    NORMALIZED = "normalized"
    #: No version was requested; unversioned documentation was used.
    UNVERSIONED = "unversioned"
    #: A version was requested, the provider does not offer it, and
    #: unversioned documentation was used instead.
    FALLBACK = "fallback"
    #: A version was requested and the provider offers no documentation at all.
    UNMATCHED = "unmatched"


@dataclass(frozen=True, slots=True)
class VersionSelection:
    """The version to request, and how honestly it can be described."""

    match: VersionMatch
    #: The provider's own label, when one was matched. Never a version the
    #: repository asked for but the provider does not offer.
    provider_version: str | None = None
    requested: str | None = None
    detail: str = ""

    @property
    def is_exact(self) -> bool:
        """Whether the documentation may be presented as version-exact."""
        return self.match in {VersionMatch.EXACT, VersionMatch.NORMALIZED}

    def to_dict(self) -> dict[str, object]:
        return {
            "version_match": self.match.value,
            "requested_version": self.requested,
            "provider_version": self.provider_version,
            "exact_version": self.is_exact,
            "detail": self.detail,
        }


def normalize_version(value: str) -> str:
    """Reduce a version label to a comparable form without losing meaning.

    Strips a leading ``v`` or pin operator and surrounding whitespace. Keeps
    prerelease and build metadata: they distinguish real releases.
    """
    text = _TRAILING_NOISE.sub("", value.strip())
    return _PIN_PREFIX.sub("", text)


def select_version(requested: str | None, available: tuple[str, ...]) -> VersionSelection:
    """Choose the provider version label to pin, and classify the match."""
    wanted = (requested or "").strip()
    if not wanted:
        return VersionSelection(
            match=VersionMatch.UNVERSIONED,
            requested=None,
            detail="no resolved version was available, so unversioned documentation was used",
        )

    for candidate in available:
        if candidate == wanted:
            return VersionSelection(VersionMatch.EXACT, candidate, wanted)

    normalized = normalize_version(wanted)
    for candidate in available:
        if normalize_version(candidate) == normalized:
            return VersionSelection(
                VersionMatch.NORMALIZED,
                candidate,
                wanted,
                detail=f"provider labels this version {candidate!r}",
            )

    if not available:
        return VersionSelection(
            match=VersionMatch.UNMATCHED,
            requested=wanted,
            detail="the provider published no version list for this library",
        )
    return VersionSelection(
        match=VersionMatch.FALLBACK,
        requested=wanted,
        detail=(
            f"the provider does not document version {wanted!r}; "
            f"unversioned documentation was used instead"
        ),
    )


def pin_library_id(library_id: str, version: str | None) -> str:
    """Return the library id to request, pinned to ``version`` when given.

    The provider accepts ``/owner/repo/<version>`` and ``/owner/repo@<version>``.
    The path form is used. An id that already carries a pin is left alone
    rather than being pinned twice.
    """
    if not version:
        return library_id
    base = library_id.rstrip("/")
    tail = base.rsplit("/", 1)[-1]
    if "@" in base.rsplit("/", 1)[-1] or normalize_version(tail) == normalize_version(version):
        return base
    return f"{base}/{version}"
