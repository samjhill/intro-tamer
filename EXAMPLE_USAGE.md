# Example Usage

## Creating a Fingerprint from a Reference Episode

Before using fingerprint detection, you need to create a reference fingerprint from a known episode:

```python
from pathlib import Path
from intro_tamer.intro_detect.fingerprint import FingerprintDetector

# Extract fingerprint from a reference episode where you know the intro times
FingerprintDetector.create_fingerprint_from_reference(
    video_path=Path("The.Office.S05E03.mkv"),
    start_time=18.0,  # Intro start in seconds
    end_time=68.0,    # Intro end in seconds
    output_path=Path("presets/office-us.fp.npz"),
    sample_rate=22050,
)
```

## Basic Processing

Process a single episode:

```bash
intro-tamer process "The Office S02E01.mkv" --preset office-us
```

## Manual Intro Boundaries

If detection fails, specify boundaries manually:

```bash
intro-tamer process "ep.mkv" \
  --intro-start 00:00:18.0 \
  --intro-end 00:01:08.5 \
  --duck-db -10
```

## Target LUFS Mode

Instead of a fixed dB reduction, target a specific loudness:

```bash
intro-tamer process "ep.mkv" \
  --preset office-us \
  --target-intro-lufs -24
```

## Analyze Mode (Dry Run)

Check what would be detected without processing:

```bash
intro-tamer analyze "ep.mkv" --preset office-us
```

## Batch Processing

Process all episodes in a directory:

```bash
intro-tamer batch "./Season 2" --preset office-us --recursive
```

## Generate Report

Create a JSON report with processing details:

```bash
intro-tamer process "ep.mkv" \
  --preset office-us \
  --report-json
```

