"""
Universal search types.
"""

from enum import Enum
from typing import Any, Dict, List, Optional


__all__ = ["SourceType", "SearchSource", "UniversalSearchResult"]


class SourceType(str, Enum):
    """Supported source types for universal search."""

    YOUTUBE = "youtube"
    YOUTUBE_MUSIC = "youtube_music"
    SOUNDCLOUD = "soundcloud"
    BANDCAMP = "bandcamp"
    DEEZER = "deezer"
    APPLE_MUSIC = "apple_music"
    SPOTIFY = "spotify"
    GENERIC = "generic"
    UNKNOWN = "unknown"


class SearchSource:
    """Represents a search result from a specific source."""

    def __init__(
        self,
        source_type: SourceType,
        url: str,
        name: str,
        artist: str,
        duration: int,
        isrc: Optional[str] = None,
        quality_score: float = 0.0,
        verified: bool = False,
        views: int = 0,
        bitrate: Optional[int] = None,
        album: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.source_type = source_type
        self.url = url
        self.name = name
        self.artist = artist
        self.duration = duration
        self.isrc = isrc
        self.quality_score = quality_score
        self.verified = verified
        self.views = views
        self.bitrate = bitrate
        self.album = album
        self.extra = extra or {}

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.name}"

    @property
    def dedup_key(self) -> str:
        return f"{self.isrc or self.display_name.lower()}:{self.duration}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type.value,
            "url": self.url,
            "name": self.name,
            "artist": self.artist,
            "duration": self.duration,
            "isrc": self.isrc,
            "quality_score": self.quality_score,
            "verified": self.verified,
            "views": self.views,
            "bitrate": self.bitrate,
            "album": self.album,
            "display_name": self.display_name,
        }


class UniversalSearchResult:
    """Aggregated result from universal search with all sources and dedup info."""

    def __init__(
        self,
        query: str,
        sources: List[SearchSource],
        best_source: Optional[SearchSource] = None,
        is_duplicate: bool = False,
        duplicate_of: Optional[str] = None,
    ):
        self.query = query
        self.sources = sources
        self.best_source = best_source
        self.is_duplicate = is_duplicate
        self.duplicate_of = duplicate_of

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "sources": [s.to_dict() for s in self.sources],
            "best_source": self.best_source.to_dict() if self.best_source else None,
            "is_duplicate": self.is_duplicate,
            "duplicate_of": self.duplicate_of,
        }
