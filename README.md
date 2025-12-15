# Intro Tamer

Automatic TV Intro Loudness Reduction Tool

## Overview

Intro Tamer automatically detects and reduces the loudness of TV show intro segments, making them quieter while leaving the rest of the episode unchanged. Perfect for shows like The Office where the intro is significantly louder than dialogue.

## Installation

### Prerequisites

- Python 3.11 or higher
- FFmpeg installed and available in PATH

### Install from source

```bash
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

## Usage

### GUI Application (Recommended)

Launch the graphical user interface:

```bash
intro-tamer-gui
```

Or:

```bash
python -m intro_tamer.gui
```

The GUI provides:
- Folder picker for input/output directories
- Real-time progress tracking
- Adjustable settings (preset, gain reduction, fade duration)
- Log output
- Start/stop controls

### Command Line

#### Basic processing

```bash
intro-tamer process "The Office S02E01.mkv" --preset office-us
```

### Manual intro boundaries

```bash
intro-tamer process "ep.mkv" --intro-start 00:00:18.0 --intro-end 00:01:08.5 --duck-db -10
```

### Batch processing

```bash
intro-tamer batch "./Season 2" --preset office-us --recursive
```

### Analyze mode (dry run)

```bash
intro-tamer analyze "ep.mkv" --preset office-us
```

## Features

- Audio fingerprint-based intro detection
- LUFS-based loudness measurement (EBU R128)
- Configurable presets for different shows
- Batch processing support
- JSON reporting
- Smooth fade transitions to avoid clicks

## Project Structure

```
intro-tamer/
├── intro_tamer/
│   ├── cli.py              # CLI interface
│   ├── media_probe.py      # FFprobe wrappers
│   ├── extract_audio.py    # Audio extraction for analysis
│   ├── intro_detect/       # Intro detection modules
│   ├── loudness.py         # LUFS measurement
│   ├── ffmpeg_render.py    # FFmpeg filtergraph builder
│   ├── presets.py          # Preset management
│   └── reporting.py        # JSON reporting
├── presets/                # Show presets
└── tests/                  # Test suite
```

## License

MIT

