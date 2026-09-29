"""A part of a YouTube video that SponsorBlock's users have marked."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SponsorSegment:
    """Where the part starts and ends, and what it was marked as.

    A highlight is a point rather than a stretch, and starts and ends in the
    same place.
    """

    start_ms: int
    end_ms: int
    # SponsorBlock's own name for it, "sponsor", "selfpromo" and so on
    category: str
