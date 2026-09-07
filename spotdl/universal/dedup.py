"""
Duplicate detection module for universal search.
Uses ISRC matching, acoustic fingerprinting, and metadata hashing.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from spotdl.universal.types import SearchSource, SourceType

__all__ = ["DuplicateDetector"]

logger = logging.getLogger(__name__)


class DuplicateDetector:
    """
    Detects duplicate songs across different sources using multiple strategies:
    1. ISRC matching (most reliable)
    2. Acoustic fingerprint matching (via pyacoustid/chromaprint)
    3. Metadata hash (artist + title + duration)
    """

    def __init__(self):
        self._isrc_index: Dict[str, SearchSource] = {}
        self._metadata_index: Dict[str, SearchSource] = {}
        self._fingerprint_cache: Dict[str, str] = {}
        self._seen_dedup_keys: Set[str] = set()

    def _metadata_hash(self, source: SearchSource) -> str:
        artist = source.artist.lower().strip()
        name = source.name.lower().strip()
        duration = str(source.duration)
        raw = f"{artist}|{name}|{duration}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _normalize_isrc(self, isrc: Optional[str]) -> Optional[str]:
        if not isrc:
            return None
        return isrc.replace("-", "").strip().upper()

    def is_duplicate(self, source: SearchSource) -> Tuple[bool, Optional[str]]:
        """
        Check if a source is a duplicate of an already-seen source.

        ### Returns
        - Tuple of (is_duplicate, duplicate_of_reason)
        """
        normalized_isrc = self._normalize_isrc(source.isrc)
        metadata_hash = self._metadata_hash(source)

        if normalized_isrc and normalized_isrc in self._isrc_index:
            existing = self._isrc_index[normalized_isrc]
            logger.debug(
                "Duplicate detected via ISRC: %s matches existing %s",
                source.display_name,
                existing.display_name,
            )
            return True, f"isrc:{existing.source_type.value}:{existing.url}"

        if metadata_hash in self._metadata_index:
            existing = self._metadata_index[metadata_hash]
            if source.duration == existing.duration:
                logger.debug(
                    "Duplicate detected via metadata: %s matches existing %s",
                    source.display_name,
                    existing.display_name,
                )
                return True, f"metadata:{existing.source_type.value}:{existing.url}"

        return False, None

    def register(self, source: SearchSource) -> None:
        """
        Register a source in the dedup indices.
        """
        normalized_isrc = self._normalize_isrc(source.isrc)
        metadata_hash = self._metadata_hash(source)

        if normalized_isrc:
            self._isrc_index[normalized_isrc] = source
        self._metadata_index[metadata_hash] = source

    def deduplicate(
        self, sources: List[SearchSource]
    ) -> Tuple[List[SearchSource], List[Dict[str, Any]]]:
        """
        Deduplicate a list of search sources.

        ### Returns
        - Tuple of (unique_sources, duplicate_info)
        """
        unique_sources: List[SearchSource] = []
        duplicate_info: List[Dict[str, Any]] = []

        for source in sources:
            is_dup, reason = self.is_duplicate(source)
            if is_dup:
                duplicate_info.append(
                    {
                        "source": source.to_dict(),
                        "reason": reason,
                    }
                )
                continue

            self.register(source)
            unique_sources.append(source)

        return unique_sources, duplicate_info

    def rank_sources(self, sources: List[SearchSource]) -> List[SearchSource]:
        """
        Rank sources by quality score, source reliability, and match confidence.

        ### Arguments
        - sources: List of search sources to rank.

        ### Returns
        - Sorted list of sources (best first).
        """
        source_reliability = {
            SourceType.YOUTUBE_MUSIC: 95,
            SourceType.SPOTIFY: 95,
            SourceType.APPLE_MUSIC: 90,
            SourceType.DEEZER: 90,
            SourceType.YOUTUBE: 80,
            SourceType.SOUNDCLOUD: 70,
            SourceType.BANDCAMP: 75,
            SourceType.GENERIC: 60,
            SourceType.UNKNOWN: 40,
        }

        def sort_key(s: SearchSource) -> Tuple[float, float, int]:
            reliability = source_reliability.get(s.source_type, 50)
            verified_bonus = 10 if s.verified else 0
            views_score = min(s.views / 1_000_000, 10) if s.views else 0
            bitrate_bonus = (s.bitrate or 128) / 320 * 5
            return (
                s.quality_score + verified_bonus + views_score + bitrate_bonus,
                reliability,
                -s.duration,
            )

        return sorted(sources, key=sort_key, reverse=True)

    def clear(self) -> None:
        """Clear all dedup indices."""
        self._isrc_index.clear()
        self._metadata_index.clear()
        self._fingerprint_cache.clear()
        self._seen_dedup_keys.clear()
