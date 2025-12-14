"""Preset management for different shows."""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Preset(BaseModel):
    """Show preset configuration."""

    name: str
    search_window_seconds: float = 240.0
    min_intro_seconds: float = 15.0
    max_intro_seconds: float = 90.0
    similarity_threshold: float = 0.82
    default_duck_db: float = -9.0
    reference_fingerprint: Optional[str] = None


def load_preset(preset_name: str, presets_dir: Optional[Path] = None) -> Preset:
    """
    Load preset from file.

    Args:
        preset_name: Name of preset (e.g., "office-us")
        presets_dir: Directory containing presets (default: ./presets)

    Returns:
        Preset object

    Raises:
        FileNotFoundError: If preset file doesn't exist
    """
    if presets_dir is None:
        presets_dir = Path(__file__).parent.parent / "presets"

    preset_path = presets_dir / f"{preset_name}.json"

    if not preset_path.exists():
        raise FileNotFoundError(f"Preset not found: {preset_path}")

    with open(preset_path, "r") as f:
        data = json.load(f)

    return Preset(**data)


def save_preset(preset: Preset, presets_dir: Optional[Path] = None) -> None:
    """
    Save preset to file.

    Args:
        preset: Preset object
        presets_dir: Directory to save preset (default: ./presets)
    """
    if presets_dir is None:
        presets_dir = Path(__file__).parent.parent / "presets"

    presets_dir.mkdir(parents=True, exist_ok=True)
    preset_path = presets_dir / f"{preset.name}.json"

    with open(preset_path, "w") as f:
        json.dump(preset.model_dump(exclude_none=True), f, indent=2)

