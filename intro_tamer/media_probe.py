"""Media probing utilities using ffprobe."""

import json
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class AudioStream(BaseModel):
    """Audio stream information."""

    index: int
    codec_name: str
    codec_long_name: str
    sample_rate: str
    channels: int
    channel_layout: str
    bit_rate: Optional[str] = None
    duration: Optional[float] = None


class VideoStream(BaseModel):
    """Video stream information."""

    index: int
    codec_name: str
    codec_long_name: str
    width: int
    height: int
    duration: Optional[float] = None
    bit_rate: Optional[str] = None


class MediaInfo(BaseModel):
    """Complete media file information."""

    duration: float
    audio_streams: list[AudioStream]
    video_streams: list[VideoStream]
    format_name: str
    format_long_name: str
    size: Optional[int] = None


def probe_media(file_path: Path) -> MediaInfo:
    """
    Probe media file using ffprobe.

    Args:
        file_path: Path to media file

    Returns:
        MediaInfo object with stream and format information

    Raises:
        subprocess.CalledProcessError: If ffprobe fails
        FileNotFoundError: If file doesn't exist
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,codec_long_name,width,height,sample_rate,channels,channel_layout,bit_rate,duration",
        "-show_entries",
        "format=duration,size,format_name,format_long_name",
        "-of",
        "json",
        str(file_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    # Extract streams
    audio_streams = []
    video_streams = []

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            audio_streams.append(
                AudioStream(
                    index=stream["index"],
                    codec_name=stream.get("codec_name", "unknown"),
                    codec_long_name=stream.get("codec_long_name", "unknown"),
                    sample_rate=stream.get("sample_rate", "0"),
                    channels=stream.get("channels", 0),
                    channel_layout=stream.get("channel_layout", "unknown"),
                    bit_rate=stream.get("bit_rate"),
                    duration=float(stream["duration"]) if stream.get("duration") else None,
                )
            )
        elif stream.get("codec_type") == "video":
            video_streams.append(
                VideoStream(
                    index=stream["index"],
                    codec_name=stream.get("codec_name", "unknown"),
                    codec_long_name=stream.get("codec_long_name", "unknown"),
                    width=stream.get("width", 0),
                    height=stream.get("height", 0),
                    duration=float(stream["duration"]) if stream.get("duration") else None,
                    bit_rate=stream.get("bit_rate"),
                )
            )

    format_info = data.get("format", {})
    duration = float(format_info.get("duration", 0))

    return MediaInfo(
        duration=duration,
        audio_streams=audio_streams,
        video_streams=video_streams,
        format_name=format_info.get("format_name", "unknown"),
        format_long_name=format_info.get("format_long_name", "unknown"),
        size=int(format_info["size"]) if format_info.get("size") else None,
    )


def get_default_audio_stream_index(media_info: MediaInfo) -> int:
    """Get the index of the default audio stream (first one)."""
    if not media_info.audio_streams:
        raise ValueError("No audio streams found in media file")
    return media_info.audio_streams[0].index

