#!/usr/bin/env python3
"""Process all seasons of The Office, preserving directory structure."""

import sys
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from intro_tamer.cli import process_video_file

console = Console()

def process_all_seasons(source_dir: Path, dest_dir: Path, preset: str = "office-us", duck_db: float = -10.0):
    """Process all episodes in season folders, preserving structure."""
    
    source_dir = Path(source_dir)
    dest_dir = Path(dest_dir)
    
    # Find all video files
    video_extensions = {".mkv", ".mp4", ".avi", ".mov", ".m4v"}
    video_files = []
    
    for ext in video_extensions:
        video_files.extend(source_dir.rglob(f"*{ext}"))
    
    video_files.sort()
    
    console.print(f"[green]Found {len(video_files)} video file(s)[/green]")
    
    if not video_files:
        console.print("[yellow]No video files found![/yellow]")
        return
    
    # Process each file
    successful = 0
    failed = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Processing episodes...", total=len(video_files))
        
        for video_file in video_files:
            # Calculate relative path from source
            rel_path = video_file.relative_to(source_dir)
            
            # Determine output path preserving structure
            output_file = dest_dir / rel_path.parent / f"{video_file.stem}.intro_tamed{video_file.suffix}"
            
            # Create output directory if needed
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Skip if already processed
            if output_file.exists():
                console.print(f"[yellow]Skipping (already exists):[/yellow] {rel_path}")
                progress.update(task, advance=1)
                successful += 1
                continue
            
            try:
                console.print(f"\n[bold cyan]Processing:[/bold cyan] {rel_path}")
                process_video_file(
                    input_file=video_file,
                    output_file=output_file,
                    preset=preset,
                    duck_db=duck_db,
                    fade_ms=120,
                    report_json=True,
                    keep_codecs=True,
                    allow_fallback=True,
                )
                successful += 1
                console.print(f"[green]✓ Success:[/green] {output_file.name}")
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted by user[/yellow]")
                raise
            except Exception as e:
                failed += 1
                console.print(f"[red]✗ Error processing {rel_path}:[/red] {e}")
            
            progress.update(task, advance=1)
    
    console.print(f"\n[green]Processing complete![/green]")
    console.print(f"  Successful: {successful}")
    console.print(f"  Failed: {failed}")
    console.print(f"  Total: {len(video_files)}")

if __name__ == "__main__":
    source = Path("/Volumes/media/tv/The Office (US)")
    dest = Path("/Volumes/media/tv/The Office - tamed")
    
    if len(sys.argv) > 1:
        source = Path(sys.argv[1])
    if len(sys.argv) > 2:
        dest = Path(sys.argv[2])
    
    process_all_seasons(source, dest, preset="office-us", duck_db=-10.0)

