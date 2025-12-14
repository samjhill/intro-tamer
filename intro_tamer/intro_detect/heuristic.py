"""Heuristic-based intro detection fallback."""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from pydantic import BaseModel

from intro_tamer.intro_detect.fingerprint import IntroBoundaries


class HeuristicDetector:
    """Detect intro using loudness jump and timing heuristics."""

    def __init__(
        self,
        search_window_seconds: float = 150.0,
        min_intro_seconds: float = 15.0,
        max_intro_seconds: float = 90.0,
        loudness_threshold_db: float = 3.0,
    ):
        """
        Initialize heuristic detector.

        Args:
            search_window_seconds: Maximum time to search from start
            min_intro_seconds: Minimum intro duration
            max_intro_seconds: Maximum intro duration
            loudness_threshold_db: Minimum loudness jump to consider
        """
        self.search_window_seconds = search_window_seconds
        self.min_intro_seconds = min_intro_seconds
        self.max_intro_seconds = max_intro_seconds
        self.loudness_threshold_db = loudness_threshold_db

    def _measure_short_term_loudness(
        self, video_path: Path, start_time: float, duration: float, audio_stream_index: int = 0
    ) -> float:
        """
        Measure short-term integrated loudness using ffmpeg ebur128 filter.

        Args:
            video_path: Path to video file
            start_time: Start time in seconds
            duration: Duration in seconds
            audio_stream_index: Audio stream index

        Returns:
            Integrated loudness in LUFS
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)

        try:
            cmd = [
                "ffmpeg",
                "-i",
                str(video_path),
                "-map",
                f"0:a:{audio_stream_index}",
                "-ss",
                str(start_time),
                "-t",
                str(duration),
                "-af",
                "ebur128=peak=true:dualmono=true:target=-16:meter=18",
                "-f",
                "null",
                "-",
            ]

            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )

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
                                except ValueError:
                                    pass

            # Fallback: return a default value if parsing fails
            return -20.0

        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def detect(
        self,
        video_path: Path,
        audio_stream_index: int = 0,
    ) -> Optional[IntroBoundaries]:
        """
        Detect intro using loudness jump heuristic.

        Args:
            video_path: Path to video file
            audio_stream_index: Audio stream index

        Returns:
            IntroBoundaries if detected, None otherwise
        """
        # Measure loudness in overlapping windows
        window_size = 5.0  # seconds
        hop_size = 2.0  # seconds
        windows = []

        search_end = min(self.search_window_seconds, 300.0)  # Cap at 5 minutes

        for t in np.arange(0.0, search_end - window_size, hop_size):
            loudness = self._measure_short_term_loudness(
                video_path, t, window_size, audio_stream_index
            )
            windows.append((t, loudness))

        if len(windows) < 2:
            return None

        # Find significant loudness jump
        times, loudnesses = zip(*windows)
        loudnesses = np.array(loudnesses)

        # Look for jump: current window significantly louder than previous
        for i in range(1, len(loudnesses)):
            jump_db = loudnesses[i] - loudnesses[i - 1]
            if jump_db >= self.loudness_threshold_db:
                # Potential intro start
                intro_start = times[i]

                # Estimate intro end (use max_intro_seconds as default)
                intro_end = min(intro_start + self.max_intro_seconds, search_end)

                # Refine end by looking for loudness drop
                for j in range(i + 1, len(loudnesses)):
                    drop_db = loudnesses[i] - loudnesses[j]
                    if drop_db >= self.loudness_threshold_db:
                        intro_end = times[j] + window_size
                        break

                # Ensure minimum duration
                if intro_end - intro_start < self.min_intro_seconds:
                    intro_end = intro_start + self.min_intro_seconds

                return IntroBoundaries(
                    start=intro_start,
                    end=intro_end,
                    confidence=0.6,  # Lower confidence for heuristic
                    method="heuristic",
                )

        return None

