"""Audio extraction utilities for analysis."""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import librosa
import numpy as np


def extract_audio_segment(
    video_path: Path,
    start_time: float = 0.0,
    duration: Optional[float] = None,
    audio_stream_index: int = 0,
    sample_rate: int = 22050,
    mono: bool = True,
) -> tuple[np.ndarray, int]:
    """
    Extract audio segment from video file for analysis.

    Args:
        video_path: Path to video file
        start_time: Start time in seconds
        duration: Duration in seconds (None = to end)
        audio_stream_index: Audio stream index to extract
        sample_rate: Target sample rate for analysis
        mono: Convert to mono

    Returns:
        Tuple of (audio_array, actual_sample_rate)
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-map",
            f"0:{audio_stream_index}",
            "-ss",
            str(start_time),
        ]

        if duration:
            cmd.extend(["-t", str(duration)])

        cmd.extend(
            [
                "-ar",
                str(sample_rate),
                "-ac",
                "1" if mono else "2",
                "-y",
                str(tmp_path),
            ]
        )

        subprocess.run(cmd, capture_output=True, check=True)

        # Load with librosa
        audio, sr = librosa.load(str(tmp_path), sr=sample_rate, mono=mono)

        return audio, sr

    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def extract_reference_audio(
    video_path: Path,
    start_time: float,
    end_time: float,
    audio_stream_index: int = 0,
    sample_rate: int = 22050,
) -> np.ndarray:
    """
    Extract reference audio segment for fingerprinting.

    Args:
        video_path: Path to video file
        start_time: Start time in seconds
        end_time: End time in seconds
        audio_stream_index: Audio stream index
        sample_rate: Target sample rate

    Returns:
        Audio array
    """
    duration = end_time - start_time
    audio, _ = extract_audio_segment(
        video_path, start_time, duration, audio_stream_index, sample_rate
    )
    return audio

