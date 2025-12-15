#!/usr/bin/env python3
"""Process all seasons of The Office, preserving directory structure."""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from intro_tamer.cli import process_video_file

console = Console()

def process_all_seasons(source_dir: Path, dest_dir: Path, preset: str = "office-us", duck_db: float = -10.0, threads: int = 4):
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
    
    # Filter out already processed files (resume capability)
    remaining_files = []
    skipped_count = 0
    
    for video_file in video_files:
        rel_path = video_file.relative_to(source_dir)
        output_file = dest_dir / rel_path.parent / f"{video_file.stem}.intro_tamed{video_file.suffix}"
        
        if output_file.exists():
            skipped_count += 1
        else:
            remaining_files.append(video_file)
    
    if skipped_count > 0:
        console.print(f"[yellow]Resuming: {skipped_count} already processed, {len(remaining_files)} remaining[/yellow]")
    
    if not remaining_files:
        console.print("[green]All files already processed![/green]")
        return
    
    # Process remaining files with multithreading
    successful = skipped_count  # Count skipped as successful
    failed = 0
    processed_count = skipped_count
    lock = Lock()
    
    def process_file(video_file):
        """Process a single file."""
        rel_path = video_file.relative_to(source_dir)
        output_file = dest_dir / rel_path.parent / f"{video_file.stem}.intro_tamed{video_file.suffix}"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
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
            with lock:
                return rel_path, "success"
        except Exception as e:
            with lock:
                return rel_path, f"error: {str(e)}"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Processing episodes...", total=len(video_files))
        progress.update(task, advance=skipped_count)
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(process_file, video_file): video_file for video_file in remaining_files}
            
            for future in as_completed(futures):
                rel_path, result = future.result()
                
                with lock:
                    processed_count += 1
                    if result == "success":
                        successful += 1
                        console.print(f"[green]✓ Success:[/green] {rel_path.name}")
                    else:
                        failed += 1
                        error_msg = result.split(":", 1)[1] if ":" in result else result
                        console.print(f"[red]✗ Error processing {rel_path}:[/red] {error_msg}")
                    
                    progress.update(task, advance=1)
    
    console.print(f"\n[green]Processing complete![/green]")
    console.print(f"  Successful: {successful}")
    console.print(f"  Failed: {failed}")
    console.print(f"  Total: {len(video_files)}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Process all episodes with multithreading")
    parser.add_argument("source", nargs="?", default="/Volumes/media/tv/The Office (US)", help="Source directory")
    parser.add_argument("dest", nargs="?", default="/Volumes/media/tv/The Office - tamed", help="Destination directory")
    parser.add_argument("--preset", default="office-us", help="Preset name")
    parser.add_argument("--duck-db", type=float, default=-10.0, help="Gain reduction in dB")
    parser.add_argument("--threads", type=int, default=4, help="Number of threads (default: 4)")
    
    args = parser.parse_args()
    
    process_all_seasons(
        Path(args.source),
        Path(args.dest),
        preset=args.preset,
        duck_db=args.duck_db,
        threads=args.threads,
    )

