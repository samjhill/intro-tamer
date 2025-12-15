"""JSON reporting for processing results."""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class IntroInfo(BaseModel):
    """Intro detection information."""

    start: float
    end: float
    confidence: float
    method: str


class OutroInfo(BaseModel):
    """Outro detection information."""

    start: float
    end: float
    confidence: float
    method: str


class AudioInfo(BaseModel):
    """Audio processing information."""

    intro_lufs_before: Optional[float] = None
    intro_lufs_after: Optional[float] = None
    duck_db_applied: Optional[float] = None


class SettingsInfo(BaseModel):
    """Processing settings."""

    fade_ms: int
    preset: Optional[str] = None
    duck_db: Optional[float] = None
    target_intro_lufs: Optional[float] = None


class ProcessingReport(BaseModel):
    """Complete processing report."""

    input: str
    output: str
    intro: IntroInfo
    outro: Optional[OutroInfo] = None
    audio: AudioInfo
    settings: SettingsInfo

    def save(self, output_path: Path) -> None:
        """Save report to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(self.model_dump(exclude_none=True), f, indent=2)

