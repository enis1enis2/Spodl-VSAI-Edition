"""
Universal search module for spotDL.
Provides search and download from all supported audio sources
with duplicate protection across platforms.
"""

from spotdl.universal.dedup import DuplicateDetector
from spotdl.universal.search import UniversalSearch
from spotdl.universal.types import (
    UniversalSearchResult,
    SearchSource,
    SourceType,
)

__all__ = [
    "DuplicateDetector",
    "UniversalSearch",
    "UniversalSearchResult",
    "SearchSource",
    "SourceType",
]
