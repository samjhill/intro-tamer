"""CLI interface for Intro Tamer."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from intro_tamer import __version__
from intro_tamer.ffmpeg_render import RenderConfig, render_video
from intro_tamer.intro_detect.fingerprint import FingerprintDetector, IntroBoundaries
from intro_tamer.intro_detect.heuristic import HeuristicDetector
from intro_tamer.loudness import compute_gain_from_target_lufs, measure_integrated_loudness
from intro_tamer.media_probe import get_default_audio_stream_index, probe_media
from intro_tamer.presets import load_preset, Preset
from intro_tamer.reporting import AudioInfo, IntroInfo, ProcessingReport, SettingsInfo

app = typer.Typer(help="Intro Tamer - Automatic TV Intro Loudness Reduction")
console = Console()


def parse_time(time_str: str) -> float:
    """Parse time string (HH:MM:SS.mmm or seconds) to float."""
    if ":" in time_str:
        parts = time_str.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
        elif len(parts) == 2:
            minutes, seconds = parts
            return float(minutes) * 60 + float(seconds)
    return float(time_str)


def process_video_file(
    input_file: Path,
    output_file: Optional[Path] = None,
    preset: Optional[str] = None,
    intro_start: Optional[str] = None,
    intro_end: Optional[str] = None,
    duck_db: Optional[float] = None,
    target_intro_lufs: Optional[float] = None,
    fade_ms: int = 120,
    max_intro_seconds: float = 120.0,
    dry_run: bool = False,
    report_json: bool = False,
    force_reencode: bool = False,
    keep_codecs: bool = True,
    allow_fallback: bool = True,
    all_audio: bool = False,
) -> None:
    """Core video processing logic (extracted for reuse)."""
    if not input_file.exists():
        console.print(f"[red]Error:[/red] File not found: {input_file}")
        raise typer.Exit(1)

    # Determine output path
    if output_file is None:
        stem = input_file.stem
        suffix = input_file.suffix
        output_file = input_file.parent / f"{stem}.intro_tamed{suffix}"

    # Load preset if provided
    loaded_preset: Optional[Preset] = None
    if preset:
        try:
            loaded_preset = load_preset(preset)
            console.print(f"[green]Loaded preset:[/green] {preset}")
        except FileNotFoundError:
            console.print(f"[yellow]Warning:[/yellow] Preset '{preset}' not found, continuing without preset")
            preset = None

    # Probe media
    with console.status("[bold green]Probing media..."):
        try:
            media_info = probe_media(input_file)
            audio_stream_index = get_default_audio_stream_index(media_info)
        except Exception as e:
            console.print(f"[red]Error probing media:[/red] {e}")
            raise typer.Exit(1)

    # Detect intro boundaries
    intro_boundaries: Optional[IntroBoundaries] = None

    if intro_start and intro_end:
        # Manual boundaries
        intro_boundaries = IntroBoundaries(
            start=parse_time(intro_start),
            end=parse_time(intro_end),
            confidence=1.0,
            method="manual",
        )
        console.print(f"[green]Using manual boundaries:[/green] {intro_boundaries.start:.2f}s - {intro_boundaries.end:.2f}s")
    else:
        # Auto-detect
        with console.status("[bold green]Detecting intro..."):
            if loaded_preset and loaded_preset.reference_fingerprint:
                # Try fingerprint detection
                fingerprint_path = Path(loaded_preset.reference_fingerprint)
                if not fingerprint_path.is_absolute():
                    fingerprint_path = Path(__file__).parent.parent / fingerprint_path

                try:
                    detector = FingerprintDetector(
                        reference_fingerprint_path=fingerprint_path,
                        similarity_threshold=loaded_preset.similarity_threshold,
                    )
                    intro_boundaries = detector.detect(
                        input_file,
                        search_start=0.0,
                        search_duration=loaded_preset.search_window_seconds,
                        audio_stream_index=audio_stream_index,
                    )
                except Exception as e:
                    console.print(f"[yellow]Fingerprint detection failed:[/yellow] {e}")
                    intro_boundaries = None

            # Fallback to heuristic
            if intro_boundaries is None and allow_fallback:
                try:
                    heuristic_detector = HeuristicDetector(
                        search_window_seconds=loaded_preset.search_window_seconds
                        if loaded_preset
                        else 150.0,
                        min_intro_seconds=loaded_preset.min_intro_seconds if loaded_preset else 15.0,
                        max_intro_seconds=loaded_preset.max_intro_seconds if loaded_preset else 90.0,
                    )
                    intro_boundaries = heuristic_detector.detect(input_file, audio_stream_index)
                except Exception as e:
                    console.print(f"[yellow]Heuristic detection failed:[/yellow] {e}")

        if intro_boundaries is None:
            console.print("[red]Error:[/red] Could not detect intro boundaries")
            console.print("[yellow]Suggestion:[/yellow] Use --intro-start and --intro-end to specify manually")
            raise typer.Exit(1)

        console.print(
            f"[green]Detected intro:[/green] {intro_boundaries.start:.2f}s - {intro_boundaries.end:.2f}s "
            f"(confidence: {intro_boundaries.confidence:.2f}, method: {intro_boundaries.method})"
        )

    # Validate intro duration
    intro_duration = intro_boundaries.end - intro_boundaries.start
    if intro_duration > max_intro_seconds:
        console.print(f"[yellow]Warning:[/yellow] Intro duration ({intro_duration:.1f}s) exceeds max ({max_intro_seconds}s)")
        console.print("[yellow]Consider using manual boundaries[/yellow]")

    # Determine gain adjustment
    gain_db: float
    intro_lufs_before: Optional[float] = None
    intro_lufs_after: Optional[float] = None

    if target_intro_lufs is not None:
        # Measure current loudness and compute gain
        with console.status("[bold green]Measuring intro loudness..."):
            try:
                intro_lufs_before = measure_integrated_loudness(
                    input_file,
                    intro_boundaries.start,
                    intro_duration,
                    audio_stream_index,
                )
                gain_db = compute_gain_from_target_lufs(intro_lufs_before, target_intro_lufs)
                intro_lufs_after = target_intro_lufs
            except Exception as e:
                console.print(f"[red]Error measuring loudness:[/red] {e}")
                raise typer.Exit(1)
    else:
        # Use fixed duck amount
        if duck_db is not None:
            gain_db = duck_db
        elif loaded_preset:
            gain_db = loaded_preset.default_duck_db
        else:
            gain_db = -9.0  # Default

        # Optionally measure before/after for report
        if report_json:
            try:
                intro_lufs_before = measure_integrated_loudness(
                    input_file,
                    intro_boundaries.start,
                    intro_duration,
                    audio_stream_index,
                )
                # Estimate after (approximate)
                intro_lufs_after = intro_lufs_before + gain_db
            except Exception:
                pass

    console.print(f"[green]Gain adjustment:[/green] {gain_db:.1f} dB")
    if intro_lufs_before:
        console.print(f"[green]Intro loudness:[/green] {intro_lufs_before:.1f} LUFS → {intro_lufs_after:.1f} LUFS")

    # Detect outro boundaries (using same fingerprint, searching from end)
    outro_boundaries: Optional[IntroBoundaries] = None
    
    with console.status("[bold green]Detecting outro..."):
        if loaded_preset and loaded_preset.reference_fingerprint:
            try:
                fingerprint_path = Path(loaded_preset.reference_fingerprint)
                if not fingerprint_path.is_absolute():
                    fingerprint_path = Path(__file__).parent.parent / fingerprint_path

                detector = FingerprintDetector(
                    reference_fingerprint_path=fingerprint_path,
                    similarity_threshold=loaded_preset.similarity_threshold,
                )
                # Search backwards from the end
                outro_boundaries = detector.detect(
                    input_file,
                    search_start=0.0,
                    search_duration=min(loaded_preset.search_window_seconds, media_info.duration),
                    audio_stream_index=audio_stream_index,
                    search_from_end=True,
                )
                if outro_boundaries:
                    console.print(
                        f"[green]Detected outro:[/green] {outro_boundaries.start:.2f}s - {outro_boundaries.end:.2f}s "
                        f"(confidence: {outro_boundaries.confidence:.2f})"
                    )
            except Exception as e:
                console.print(f"[yellow]Outro detection failed:[/yellow] {e}")

    # Build render config
    render_config = RenderConfig(
        intro_start=intro_boundaries.start,
        intro_end=intro_boundaries.end,
        outro_start=outro_boundaries.start if outro_boundaries else None,
        outro_end=outro_boundaries.end if outro_boundaries else None,
        gain_db=gain_db,
        fade_ms=fade_ms,
        audio_stream_index=audio_stream_index,
        all_audio_tracks=all_audio,
    )

    if dry_run:
        console.print("[yellow]Dry run mode - no output file will be created[/yellow]")
        console.print(f"[cyan]Would create:[/cyan] {output_file}")
        return

    # Render video
    with console.status("[bold green]Rendering video..."):
        try:
            render_video(
                input_file,
                output_file,
                render_config,
                force_reencode=force_reencode,
                keep_codecs=keep_codecs,
            )
            console.print(f"[green]Success![/green] Output: {output_file}")
        except Exception as e:
            console.print(f"[red]Error rendering video:[/red] {e}")
            raise typer.Exit(1)

    # Write report
    if report_json:
        report_path = output_file.with_suffix(".json")
        report = ProcessingReport(
            input=str(input_file),
            output=str(output_file),
            intro=IntroInfo(
                start=intro_boundaries.start,
                end=intro_boundaries.end,
                confidence=intro_boundaries.confidence,
                method=intro_boundaries.method,
            ),
            audio=AudioInfo(
                intro_lufs_before=intro_lufs_before,
                intro_lufs_after=intro_lufs_after,
                duck_db_applied=gain_db,
            ),
            settings=SettingsInfo(
                fade_ms=fade_ms,
                preset=preset,
                duck_db=duck_db if duck_db else None,
                target_intro_lufs=target_intro_lufs,
            ),
        )
        report.save(report_path)
        console.print(f"[green]Report saved:[/green] {report_path}")


@app.command()
def process(
    input_file: Path = typer.Argument(..., help="Input video file"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    preset: Optional[str] = typer.Option(None, "--preset", help="Preset name (e.g., office-us)"),
    intro_start: Optional[str] = typer.Option(None, "--intro-start", help="Manual intro start (HH:MM:SS.mmm)"),
    intro_end: Optional[str] = typer.Option(None, "--intro-end", help="Manual intro end (HH:MM:SS.mmm)"),
    duck_db: Optional[float] = typer.Option(None, "--duck-db", help="Gain reduction in dB (negative)"),
    target_intro_lufs: Optional[float] = typer.Option(None, "--target-intro-lufs", help="Target LUFS for intro"),
    fade_ms: int = typer.Option(120, "--fade-ms", help="Fade duration in milliseconds"),
    max_intro_seconds: float = typer.Option(120.0, "--max-intro-seconds", help="Maximum intro duration"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't create output file"),
    report_json: bool = typer.Option(False, "--report-json", help="Write JSON report"),
    force_reencode: bool = typer.Option(False, "--force-reencode", help="Force re-encoding"),
    keep_codecs: bool = typer.Option(True, "--keep-codecs/--no-keep-codecs", help="Attempt stream copy"),
    allow_fallback: bool = typer.Option(True, "--allow-fallback/--no-allow-fallback", help="Allow heuristic fallback"),
    all_audio: bool = typer.Option(False, "--all-audio", help="Process all audio tracks"),
) -> None:
    """Process a video file to reduce intro loudness."""
    process_video_file(
        input_file=input_file,
        output_file=output_file,
        preset=preset,
        intro_start=intro_start,
        intro_end=intro_end,
        duck_db=duck_db,
        target_intro_lufs=target_intro_lufs,
        fade_ms=fade_ms,
        max_intro_seconds=max_intro_seconds,
        dry_run=dry_run,
        report_json=report_json,
        force_reencode=force_reencode,
        keep_codecs=keep_codecs,
        allow_fallback=allow_fallback,
        all_audio=all_audio,
    )


@app.command()
def analyze(
    input_file: Path = typer.Argument(..., help="Input video file"),
    preset: Optional[str] = typer.Option(None, "--preset", help="Preset name"),
    intro_start: Optional[str] = typer.Option(None, "--intro-start", help="Manual intro start"),
    intro_end: Optional[str] = typer.Option(None, "--intro-end", help="Manual intro end"),
) -> None:
    """Analyze video file and print detected intro boundaries and loudness."""
    if not input_file.exists():
        console.print(f"[red]Error:[/red] File not found: {input_file}")
        raise typer.Exit(1)

    # Load preset
    loaded_preset: Optional[Preset] = None
    if preset:
        try:
            loaded_preset = load_preset(preset)
        except FileNotFoundError:
            console.print(f"[yellow]Warning:[/yellow] Preset '{preset}' not found")

    # Probe media
    with console.status("[bold green]Probing media..."):
        media_info = probe_media(input_file)
        audio_stream_index = get_default_audio_stream_index(media_info)

    # Detect intro
    intro_boundaries: Optional[IntroBoundaries] = None

    if intro_start and intro_end:
        intro_boundaries = IntroBoundaries(
            start=parse_time(intro_start),
            end=parse_time(intro_end),
            confidence=1.0,
            method="manual",
        )
    else:
        with console.status("[bold green]Detecting intro..."):
            if loaded_preset and loaded_preset.reference_fingerprint:
                fingerprint_path = Path(loaded_preset.reference_fingerprint)
                if not fingerprint_path.is_absolute():
                    fingerprint_path = Path(__file__).parent.parent / fingerprint_path

                try:
                    detector = FingerprintDetector(
                        reference_fingerprint_path=fingerprint_path,
                        similarity_threshold=loaded_preset.similarity_threshold,
                    )
                    intro_boundaries = detector.detect(
                        input_file,
                        search_start=0.0,
                        search_duration=loaded_preset.search_window_seconds,
                        audio_stream_index=audio_stream_index,
                    )
                except Exception as e:
                    console.print(f"[yellow]Fingerprint detection failed:[/yellow] {e}")

            if intro_boundaries is None:
                heuristic_detector = HeuristicDetector(
                    search_window_seconds=loaded_preset.search_window_seconds if loaded_preset else 150.0,
                )
                intro_boundaries = heuristic_detector.detect(input_file, audio_stream_index)

    # Display results
    table = Table(title="Analysis Results")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("File", str(input_file))
    table.add_row("Duration", f"{media_info.duration:.2f} seconds")
    table.add_row("Audio Streams", str(len(media_info.audio_streams)))
    table.add_row("Video Streams", str(len(media_info.video_streams)))

    if intro_boundaries:
        table.add_row("Intro Start", f"{intro_boundaries.start:.2f} s")
        table.add_row("Intro End", f"{intro_boundaries.end:.2f} s")
        table.add_row("Intro Duration", f"{intro_boundaries.end - intro_boundaries.start:.2f} s")
        table.add_row("Confidence", f"{intro_boundaries.confidence:.2f}")
        table.add_row("Method", intro_boundaries.method)

        # Measure loudness
        with console.status("[bold green]Measuring loudness..."):
            try:
                intro_lufs = measure_integrated_loudness(
                    input_file,
                    intro_boundaries.start,
                    intro_boundaries.end - intro_boundaries.start,
                    audio_stream_index,
                )
                table.add_row("Intro LUFS", f"{intro_lufs:.1f} LUFS")
            except Exception as e:
                console.print(f"[yellow]Could not measure loudness:[/yellow] {e}")
    else:
        table.add_row("Intro Detection", "[red]Failed[/red]")

    console.print(table)


@app.command()
def batch(
    input_dir: Path = typer.Argument(..., help="Input directory"),
    preset: str = typer.Option(..., "--preset", help="Preset name"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Process recursively"),
    duck_db: Optional[float] = typer.Option(None, "--duck-db", help="Gain reduction in dB"),
    fade_ms: int = typer.Option(120, "--fade-ms", help="Fade duration in milliseconds"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't create output files"),
) -> None:
    """Batch process multiple video files in a directory."""
    if not input_dir.exists():
        console.print(f"[red]Error:[/red] Directory not found: {input_dir}")
        raise typer.Exit(1)

    # Find video files
    video_extensions = {".mkv", ".mp4", ".avi", ".mov", ".m4v"}
    video_files = []

    if recursive:
        for ext in video_extensions:
            video_files.extend(input_dir.rglob(f"*{ext}"))
    else:
        for ext in video_extensions:
            video_files.extend(input_dir.glob(f"*{ext}"))

    if not video_files:
        console.print(f"[yellow]No video files found in[/yellow] {input_dir}")
        return

    console.print(f"[green]Found {len(video_files)} video file(s)[/green]")

    # Process each file
    for video_file in video_files:
        console.print(f"\n[bold cyan]Processing:[/bold cyan] {video_file.name}")
        try:
            process_video_file(
                input_file=video_file,
                preset=preset,
                duck_db=duck_db,
                fade_ms=fade_ms,
                dry_run=dry_run,
            )
        except Exception as e:
            console.print(f"[red]Error processing {video_file.name}:[/red] {e}")
            continue

    console.print("\n[green]Batch processing complete![/green]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"Intro Tamer version {__version__}")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()

