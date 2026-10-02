"""Finding YouTube URLs in text and fetching video transcripts."""

import re
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

YOUTUBE_URL_PATTERN = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?\S+|shorts/\S+|embed/\S+)|youtu\.be/\S+)"
)


def find_youtube_url(text: str) -> str | None:
    """Return the first YouTube URL in `text`, if any."""
    match = YOUTUBE_URL_PATTERN.search(text)
    return match.group(0) if match else None


def parse_video_id(youtube_url: str) -> str:
    """Extract the video id from watch, youtu.be, shorts and embed URLs."""
    parsed = urlparse(youtube_url)
    host = parsed.netloc.removeprefix("www.").removeprefix("m.")
    path_parts = [part for part in parsed.path.split("/") if part]

    if host == "youtu.be" and path_parts:
        return path_parts[0]
    if host == "youtube.com":
        if parsed.path == "/watch" and (video_ids := parse_qs(parsed.query).get("v")):
            return video_ids[0]
        if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed"}:
            return path_parts[1]
    raise ValueError(f"Not a recognised YouTube video URL: {youtube_url!r}")


def fetch_transcript(video_id: str) -> str:
    """Fetch the English transcript of a video as one string (blocking network call)."""
    transcript = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
    return " ".join(snippet.text for snippet in transcript)
