"""
Universal audio provider module.
Leverages yt-dlp's universal extraction to search and download
from any supported platform.
"""

import logging
from typing import Any, Dict, List

from yt_dlp import YoutubeDL

from spotdl.providers.audio.base import AudioProvider
from spotdl.types.result import Result
from spotdl.universal.types import SourceType

__all__ = ["UniversalProvider"]

logger = logging.getLogger(__name__)


class UniversalProvider(AudioProvider):
    """
    Universal audio provider that can search and download from
    any platform supported by yt-dlp extractors.

    This provider falls back to yt-dlp's generic extraction when
    other providers fail, enabling downloads from Deezer, Apple Music,
    and hundreds of other platforms.
    """

    SUPPORTS_ISRC = False
    GET_RESULTS_OPTS: List[Dict[str, Any]] = [
        {"default_search": "ytsearch", "max_downloads": 10},
        {"default_search": "scsearch", "max_downloads": 10},
    ]

    def get_results(self, search_term: str, **_kwargs) -> List[Result]:
        """
        Get results using yt-dlp's universal extraction.

        ### Arguments
        - search_term: The search term.

        ### Returns
        - A list of results from multiple platforms.
        """
        results: List[Result] = []

        search_prefixes = [
            f"ytsearch10:{search_term}",
            f"scsearch10:{search_term}",
        ]

        search_opts: Dict[str, Any] = {
            **self.audio_handler.params,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
        }

        for search_query in search_prefixes:
            try:
                with YoutubeDL(search_opts) as ydl:
                    info = ydl.extract_info(search_query, download=False)

                if not info or "entries" not in info:
                    continue

                for entry in info["entries"]:
                    if not entry:
                        continue

                    video_id = entry.get("id")
                    if not video_id:
                        continue

                    extractor = entry.get("extractor_key", "generic").lower()
                    source_type = self._map_extractor_to_source_type(extractor)

                    url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
                    if "youtube.com" not in url and "youtu.be" not in url:
                        url = entry.get("webpage_url") or entry.get("original_url") or url

                    results.append(
                        Result(
                            source="Universal",
                            url=url,
                            verified=False,
                            name=entry.get("title", ""),
                            duration=entry.get("duration") or 0,
                            author=entry.get("uploader") or "",
                            search_query=search_term,
                            views=entry.get("view_count") or 0,
                            result_id=video_id,
                        )
                    )

            except Exception as exc:
                logger.debug(
                    "UniversalProvider search failed for '%s': %s",
                    search_query,
                    exc,
                )

        return results

    def _map_extractor_to_source_type(self, extractor: str) -> SourceType:
        mapping = {
            "youtube": SourceType.YOUTUBE,
            "youtubemusic": SourceType.YOUTUBE_MUSIC,
            "soundcloud": SourceType.SOUNDCLOUD,
            "bandcamp": SourceType.BANDCAMP,
            "deezer": SourceType.DEEZER,
            "apple_music": SourceType.APPLE_MUSIC,
            "spotify": SourceType.SPOTIFY,
        }
        return mapping.get(extractor, SourceType.GENERIC)

    @property
    def name(self) -> str:
        return "UniversalProvider"
