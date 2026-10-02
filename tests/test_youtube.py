import pytest

from itinerary_planner.youtube import find_youtube_url, parse_video_id


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://www.youtube.com/watch?v=abc123XYZ_-&t=42s", "abc123XYZ_-"),
        ("https://m.youtube.com/watch?v=abc123XYZ_-", "abc123XYZ_-"),
        ("https://youtu.be/abc123XYZ_-?si=share", "abc123XYZ_-"),
        ("https://youtube.com/shorts/abc123XYZ_-", "abc123XYZ_-"),
        ("https://www.youtube.com/embed/abc123XYZ_-", "abc123XYZ_-"),
    ],
)
def test_parse_video_id_supported_formats(url: str, video_id: str) -> None:
    assert parse_video_id(url) == video_id


@pytest.mark.parametrize(
    "url",
    ["https://www.youtube.com/watch?t=42s", "https://youtu.be/", "https://vimeo.com/123", "not a url"],
)
def test_parse_video_id_rejects_malformed(url: str) -> None:
    with pytest.raises(ValueError, match="Not a recognised YouTube video URL"):
        parse_video_id(url)


def test_find_youtube_url_in_text() -> None:
    assert find_youtube_url("Plan this trip https://youtu.be/abc123 please") == "https://youtu.be/abc123"


def test_find_youtube_url_absent() -> None:
    assert find_youtube_url("Trip to Kyoto from Chicago") is None
