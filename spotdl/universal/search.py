"""
Universal search module.
Aggregates search results from all available audio providers
and deduplicates them.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from spotdl.download.downloader import AUDIO_PROVIDERS
from spotdl.providers.audio.base import AudioProvider
from spotdl.types.song import Song
from spotdl.universal.dedup import DuplicateDetector
from spotdl.universal.types import SearchSource, SourceType, UniversalSearchResult

__all__ = ["UniversalSearch"]

logger = logging.getLogger(__name__)


class UniversalSearch:
    """
    Universal search aggregator that queries all available audio providers
    in parallel and deduplicates results.
    """

    def __init__(
        self,
        providers: Optional[List[str]] = None,
        max_workers: int = 5,
        dedup_threshold: float = 0.85,
    ):
        if providers is None:
            providers = list(AUDIO_PROVIDERS.keys())

        self.providers = providers
        self.max_workers = max_workers
        self.dedup_threshold = dedup_threshold
        self.detector = DuplicateDetector()

    def _create_provider(self, provider_name: str) -> AudioProvider:
        provider_class = AUDIO_PROVIDERS.get(provider_name)
        if provider_class is None:
            raise ValueError(f"Unknown provider: {provider_name}")
        return provider_class()

    def _search_provider(
        self, provider_name: str, search_term: str
    ) -> List[SearchSource]:
        """Search a single provider for the given term."""
        try:
            provider = self._create_provider(provider_name)
            song = Song.from_search_term(search_term)
            url = provider.search(song, only_verified=False)
            if not url:
                return []

            results = provider.get_results(search_term)
            sources: List[SearchSource] = []

            for result in results:
                source_type = self._map_provider_to_source_type(provider_name)
                bitrate = self._estimate_bitrate(result)

                quality_score = self._calculate_quality_score(result)

                sources.append(
                    SearchSource(
                        source_type=source_type,
                        url=result.url,
                        name=result.name,
                        artist=result.author or "",
                        duration=result.duration or 0,
                        isrc=getattr(result, "isrc", None),
                        quality_score=quality_score,
                        verified=result.verified,
                        views=result.views or 0,
                        bitrate=bitrate,
                        album=getattr(result, "album", None),
                    )
                )

            logger.debug(
                "[%s] Found %d results for '%s'",
                provider_name,
                len(sources),
                search_term,
            )
            return sources

        except Exception as exc:
            logger.debug("Provider %s failed to search: %s", provider_name, exc)
            return []

    def _map_provider_to_source_type(self, provider_name: str) -> SourceType:
        mapping = {
            "youtube": SourceType.YOUTUBE,
            "youtube-music": SourceType.YOUTUBE_MUSIC,
            "soundcloud": SourceType.SOUNDCLOUD,
            "bandcamp": SourceType.BANDCAMP,
            "piped": SourceType.GENERIC,
        }
        return mapping.get(provider_name, SourceType.UNKNOWN)

    def _estimate_bitrate(self, result) -> Optional[int]:
        abr = getattr(result, "abr", None)
        if abr:
            try:
                return int(abr)
            except (ValueError, TypeError):
                pass
        return None

    def _calculate_quality_score(self, result) -> float:
        score = 50.0
        if result.verified:
            score += 20.0
        views = getattr(result, "views", 0) or 0
        if views > 1_000_000:
            score += 15.0
        elif views > 100_000:
            score += 10.0
        elif views > 10_000:
            score += 5.0
        bitrate = self._estimate_bitrate(result)
        if bitrate and bitrate >= 320:
            score += 10.0
        elif bitrate and bitrate >= 192:
            score += 5.0
        isrc = getattr(result, "isrc", None)
        if isrc:
            score += 5.0
        return min(score, 100.0)

    def search(
        self, query: str, deduplicate: bool = True
    ) -> UniversalSearchResult:
        """
        Search for a query across all configured providers.

        ### Arguments
        - query: The search term.
        - deduplicate: Whether to deduplicate results.

        ### Returns
        - UniversalSearchResult with all sources and best match.
        """
        logger.info("Universal search for: %s", query)

        all_sources: List[SearchSource] = []

        if self.max_workers <= 1:
            for provider_name in self.providers:
                sources = self._search_provider(provider_name, query)
                all_sources.extend(sources)
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(
                        self._search_provider, provider_name, query
                    ): provider_name
                    for provider_name in self.providers
                }
                for future in as_completed(futures):
                    sources = future.result()
                    all_sources.extend(sources)

        if deduplicate:
            unique_sources, duplicates = self.detector.deduplicate(all_sources)
        else:
            unique_sources = all_sources
            duplicates = []

        ranked_sources = self.detector.rank_sources(unique_sources)
        best_source = ranked_sources[0] if ranked_sources else None

        logger.info(
            "Universal search complete: %d unique sources found",
            len(ranked_sources),
        )

        return UniversalSearchResult(
            query=query,
            sources=ranked_sources,
            best_source=best_source,
            is_duplicate=bool(duplicates),
            duplicate_of=duplicates[0]["reason"] if duplicates else None,
        )

    def search_and_download(
        self,
        query: str,
        downloader,
        deduplicate: bool = True,
    ) -> Optional[SearchSource]:
        """
        Search for a query, pick the best source, and download it.

        ### Arguments
        - query: The search term.
        - downloader: The Downloader instance.
        - deduplicate: Whether to deduplicate results.

        ### Returns
        - The SearchSource that was downloaded, or None if failed.
        """
        result = self.search(query, deduplicate=deduplicate)

        if not result.best_source:
            logger.error("No results found for: %s", query)
            return None

        best = result.best_source
        logger.info(
            "Best source for '%s': %s (%s)",
            query,
            best.display_name,
            best.source_type.value,
        )

        try:
            song = Song.from_search_term(query)
            song.download_url = best.url

            _, path = downloader.pool_download(song)
            if path is None:
                logger.error("Download failed for: %s", best.display_name)
                return None

            return best

        except Exception as exc:
            logger.error("Download error for '%s': %s", query, exc)
            return None
