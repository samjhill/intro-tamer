"""LUFS loudness measurement utilities."""

import subprocess
from pathlib import Path
from typing import Optional


def measure_integrated_loudness(
    video_path: Path,
    start_time: Optional[float] = None,
    duration: Optional[float] = None,
    audio_stream_index: int = 0,
) -> float:
    """
    Measure integrated loudness (EBU R128) using ffmpeg ebur128 filter.

    Args:
        video_path: Path to video file
        start_time: Start time in seconds (None = from beginning)
        duration: Duration in seconds (None = to end)
        audio_stream_index: Audio stream index

    Returns:
        Integrated loudness in LUFS

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails
        ValueError: If loudness cannot be parsed
    """
    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-map",
        f"0:{audio_stream_index}",
    ]

    if start_time is not None:
        cmd.extend(["-ss", str(start_time)])
    if duration is not None:
        cmd.extend(["-t", str(duration)])

    cmd.extend(
        [
            "-af",
            "ebur128=peak=true:dualmono=true:target=-16:meter=18",
            "-f",
            "null",
            "-",
        ]
    )

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    # Parse output for I value (integrated loudness)
    for line in result.stdout.split("\n"):
        if "I:" in line:
            # Extract I value: "I:         -16.2 LUFS"
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "I:":
                    if i + 1 < len(parts):
                        try:
                            return float(parts[i + 1])
                        except (ValueError, IndexError):
                            pass

    # Try stderr if stdout didn't have it
    for line in result.stderr.split("\n"):
        if "I:" in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "I:":
                    if i + 1 < len(parts):
                        try:
                            return float(parts[i + 1])
                        except (ValueError, IndexError):
                            pass

    raise ValueError("Could not parse integrated loudness from ffmpeg output")


def compute_gain_from_target_lufs(current_lufs: float, target_lufs: float) -> float:
    """
    Compute gain adjustment in dB to reach target LUFS.

    Args:
        current_lufs: Current integrated loudness in LUFS
        target_lufs: Target integrated loudness in LUFS

    Returns:
        Gain adjustment in dB (negative = reduce, positive = increase)
    """
    return target_lufs - current_lufs

