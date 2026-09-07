"""
Tests for the universal search module.
"""

import pytest

from spotdl.universal.dedup import DuplicateDetector
from spotdl.universal.types import SearchSource, SourceType, UniversalSearchResult


class TestDuplicateDetector:
    """Tests for DuplicateDetector."""

    def test_isrc_duplicate_detection(self):
        """Test that ISRC matching detects duplicates."""
        detector = DuplicateDetector()

        source1 = SearchSource(
            source_type=SourceType.YOUTUBE_MUSIC,
            url="https://music.youtube.com/watch?v=abc123",
            name="Test Song",
            artist="Test Artist",
            duration=180,
            isrc="USABC1234567",
            quality_score=90.0,
        )

        source2 = SearchSource(
            source_type=SourceType.SOUNDCLOUD,
            url="https://soundcloud.com/user/test-song",
            name="Test Song (Remix)",
            artist="Test Artist",
            duration=180,
            isrc="USABC1234567",
            quality_score=70.0,
        )

        assert not detector.is_duplicate(source1)[0]
        detector.register(source1)
        assert detector.is_duplicate(source2)[0]

    def test_metadata_duplicate_detection(self):
        """Test that metadata hash detects duplicates."""
        detector = DuplicateDetector()

        source1 = SearchSource(
            source_type=SourceType.YOUTUBE,
            url="https://youtube.com/watch?v=abc123",
            name="Song Name",
            artist="Artist Name",
            duration=200,
            quality_score=80.0,
        )

        source2 = SearchSource(
            source_type=SourceType.BANDCAMP,
            url="https://artist.bandcamp.com/track/song-name",
            name="Song Name",
            artist="Artist Name",
            duration=200,
            quality_score=60.0,
        )

        assert not detector.is_duplicate(source1)[0]
        detector.register(source1)
        assert detector.is_duplicate(source2)[0]

    def test_non_duplicate_different_duration(self):
        """Test that different durations are not duplicates."""
        detector = DuplicateDetector()

        source1 = SearchSource(
            source_type=SourceType.YOUTUBE,
            url="https://youtube.com/watch?v=abc123",
            name="Song Name",
            artist="Artist Name",
            duration=200,
            quality_score=80.0,
        )

        source2 = SearchSource(
            source_type=SourceType.YOUTUBE,
            url="https://youtube.com/watch?v=def456",
            name="Song Name",
            artist="Artist Name",
            duration=210,
            quality_score=80.0,
        )

        assert not detector.is_duplicate(source1)[0]
        assert not detector.is_duplicate(source2)[0]

    def test_rank_sources(self):
        """Test that sources are ranked correctly."""
        detector = DuplicateDetector()

        sources = [
            SearchSource(
                source_type=SourceType.YOUTUBE,
                url="https://youtube.com/watch?v=abc123",
                name="Song",
                artist="Artist",
                duration=180,
                quality_score=50.0,
                views=5000,
            ),
            SearchSource(
                source_type=SourceType.YOUTUBE_MUSIC,
                url="https://music.youtube.com/watch?v=def456",
                name="Song",
                artist="Artist",
                duration=180,
                quality_score=70.0,
                views=100000,
            ),
            SearchSource(
                source_type=SourceType.SOUNDCLOUD,
                url="https://soundcloud.com/user/song",
                name="Song",
                artist="Artist",
                duration=180,
                quality_score=60.0,
                views=1000000,
            ),
        ]

        ranked = detector.rank_sources(sources)
        assert ranked[0].source_type == SourceType.YOUTUBE_MUSIC


class TestUniversalSearchResult:
    """Tests for UniversalSearchResult."""

    def test_empty_result(self):
        """Test empty search result."""
        result = UniversalSearchResult(query="test", sources=[])
        assert result.best_source is None
        assert not result.is_duplicate

    def test_to_dict(self):
        """Test serialization."""
        source = SearchSource(
            source_type=SourceType.YOUTUBE,
            url="https://youtube.com/watch?v=abc123",
            name="Song",
            artist="Artist",
            duration=180,
            quality_score=80.0,
        )
        result = UniversalSearchResult(
            query="test", sources=[source], best_source=source
        )
        data = result.to_dict()
        assert data["query"] == "test"
        assert len(data["sources"]) == 1
        assert data["best_source"]["url"] == "https://youtube.com/watch?v=abc123"
