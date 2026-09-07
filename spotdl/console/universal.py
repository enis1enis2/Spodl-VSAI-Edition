"""
Universal search and download console module.
"""

import argparse
import logging
import sys
from typing import List, Optional

from spotdl.download.downloader import Downloader
from spotdl.types.options import DownloaderOptions
from spotdl.universal.search import UniversalSearch

__all__ = ["universal"]


logger = logging.getLogger(__name__)


def universal(
    query: List[str],
    downloader: Optional[Downloader] = None,
    downloader_settings: Optional[DownloaderOptions] = None,
    **kwargs,
):
    """
    Search for songs across all supported platforms and optionally download them.

    ### Arguments
    - query: List of search terms or URLs.
    - downloader: The Downloader instance.
    - downloader_settings: The downloader settings.
    - kwargs: Additional arguments.
    """
    from spotdl.utils.console import ACTIONS
    from spotdl.utils.arguments import parse_arguments

    if not query:
        print(
            "Usage: spotdl universal <search_term_or_url> [search_term_or_url...]"
        )
        sys.exit(1)

    universal_search = UniversalSearch()

    if downloader is None:
        if downloader_settings is None:
            args = parse_arguments()
            downloader_settings = args.downloader_settings

        downloader = Downloader(settings=downloader_settings)

    terms = " ".join(query)
    result = universal_search.search(terms)

    if not result.best_source:
        print(f"No results found for: {terms}")
        sys.exit(1)

    print(f"\nUniversal search results for: {terms}")
    print("=" * 60)

    for idx, source in enumerate(result.sources, 1):
        quality = "HD" if source.quality_score >= 80 else "SD" if source.quality_score >= 50 else "LQ"
        verified = "[V]" if source.verified else "[ ]"
        print(
            f"{idx:2}. {verified} [{source.source_type.value.upper():15}] "
            f"{source.display_name[:50]:50} "
            f"{quality} ({source.quality_score:.0f}%)"
        )
        if source.album:
            print(f"     Album: {source.album}")
        print(f"     URL: {source.url}")

    print("=" * 60)
    print(f"\nBest match: {result.best_source.display_name}")
    print(f"Source: {result.best_source.source_type.value}")
    print(f"URL: {result.best_source.url}")

    if kwargs.get("auto_download", False):
        print("\nDownloading...")
        universal_search.search_and_download(terms, downloader)
    else:
        response = input("\nDownload this? [Y/n]: ").strip().lower()
        if response in ("", "y", "yes"):
            universal_search.search_and_download(terms, downloader)
