"""Preview window for detected intro/outro segments."""

import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np

from intro_tamer.cli import process_video_file
from intro_tamer.intro_detect.fingerprint import FingerprintDetector, IntroBoundaries
from intro_tamer.intro_detect.heuristic import HeuristicDetector
from intro_tamer.media_probe import get_default_audio_stream_index, probe_media
from intro_tamer.presets import load_preset


class PreviewWindow:
    """Preview window showing detected segments and allowing A/B comparison."""
    
    def __init__(self, parent, video_file: Path, preset: str, duck_db: float, fade_ms: int):
        self.parent = parent
        self.video_file = video_file
        self.preset = preset
        self.duck_db = duck_db
        self.fade_ms = fade_ms
        
        self.intro_boundaries = None
        self.outro_boundaries = None
        self.media_info = None
        self.audio_stream_index = 0
        
        self.window = tk.Toplevel(parent)
        self.window.title(f"Preview: {video_file.name}")
        self.window.geometry("900x700")
        
        self.setup_ui()
        self.detect_segments()
        
    def setup_ui(self):
        """Set up the preview UI."""
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # File info
        info_frame = ttk.LabelFrame(main_frame, text="File Information", padding="10")
        info_frame.pack(fill=tk.X, pady=5)
        
        self.info_label = ttk.Label(info_frame, text=f"File: {self.video_file.name}")
        self.info_label.pack(anchor=tk.W)
        
        # Detected segments
        segments_frame = ttk.LabelFrame(main_frame, text="Detected Segments", padding="10")
        segments_frame.pack(fill=tk.X, pady=5)
        
        # Intro
        intro_frame = ttk.Frame(segments_frame)
        intro_frame.pack(fill=tk.X, pady=5)
        ttk.Label(intro_frame, text="Intro:", width=10).pack(side=tk.LEFT)
        self.intro_label = ttk.Label(intro_frame, text="Detecting...")
        self.intro_label.pack(side=tk.LEFT, padx=5)
        
        # Outro
        outro_frame = ttk.Frame(segments_frame)
        outro_frame.pack(fill=tk.X, pady=5)
        ttk.Label(outro_frame, text="Outro:", width=10).pack(side=tk.LEFT)
        self.outro_label = ttk.Label(outro_frame, text="Detecting...")
        self.outro_label.pack(side=tk.LEFT, padx=5)
        
        # Waveform visualization
        waveform_frame = ttk.LabelFrame(main_frame, text="Audio Waveform", padding="10")
        waveform_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.fig = Figure(figsize=(10, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, waveform_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Controls
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill=tk.X, pady=5)
        
        # Preview buttons
        preview_frame = ttk.LabelFrame(controls_frame, text="Preview", padding="10")
        preview_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(preview_frame, text="Play Intro (Original)", command=self.play_intro_original).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_frame, text="Play Intro (Processed)", command=self.play_intro_processed).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_frame, text="Play Outro (Original)", command=self.play_outro_original).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_frame, text="Play Outro (Processed)", command=self.play_outro_processed).pack(side=tk.LEFT, padx=5)
        
        # Action buttons
        action_frame = ttk.Frame(controls_frame)
        action_frame.pack(side=tk.RIGHT, padx=10)
        
        ttk.Button(action_frame, text="Process File", command=self.process_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Close", command=self.window.destroy).pack(side=tk.LEFT, padx=5)
        
    def detect_segments(self):
        """Detect intro and outro segments."""
        def _detect():
            try:
                # Probe media
                self.media_info = probe_media(self.video_file)
                self.audio_stream_index = get_default_audio_stream_index(self.media_info)
                
                # Load preset
                loaded_preset = load_preset(self.preset)
                
                # Detect intro
                if loaded_preset.reference_fingerprint:
                    fingerprint_path = Path(loaded_preset.reference_fingerprint)
                    if not fingerprint_path.is_absolute():
                        fingerprint_path = Path(__file__).parent.parent / fingerprint_path
                    
                    detector = FingerprintDetector(
                        reference_fingerprint_path=fingerprint_path,
                        similarity_threshold=loaded_preset.similarity_threshold,
                    )
                    self.intro_boundaries = detector.detect(
                        self.video_file,
                        search_start=0.0,
                        search_duration=loaded_preset.search_window_seconds,
                        audio_stream_index=self.audio_stream_index,
                    )
                    
                    # Detect outro
                    self.outro_boundaries = detector.detect(
                        self.video_file,
                        search_start=0.0,
                        search_duration=min(loaded_preset.search_window_seconds, self.media_info.duration),
                        audio_stream_index=self.audio_stream_index,
                        search_from_end=True,
                    )
                
                # Update UI
                self.window.after(0, self._update_ui)
                
            except Exception as e:
                self.window.after(0, lambda: self._show_error(str(e)))
        
        threading.Thread(target=_detect, daemon=True).start()
    
    def _update_ui(self):
        """Update UI with detected segments."""
        if self.intro_boundaries:
            self.intro_label.config(
                text=f"{self.intro_boundaries.start:.2f}s - {self.intro_boundaries.end:.2f}s "
                     f"(confidence: {self.intro_boundaries.confidence:.2f})"
            )
        else:
            self.intro_label.config(text="Not detected")
            
        if self.outro_boundaries:
            self.outro_label.config(
                text=f"{self.outro_boundaries.start:.2f}s - {self.outro_boundaries.end:.2f}s "
                     f"(confidence: {self.outro_boundaries.confidence:.2f})"
            )
        else:
            self.outro_label.config(text="Not detected")
        
        # Draw waveform
        self.draw_waveform()
    
    def _show_error(self, error_msg: str):
        """Show error message."""
        self.intro_label.config(text=f"Error: {error_msg}")
        self.outro_label.config(text="Error")
    
    def draw_waveform(self):
        """Draw audio waveform with detected segments highlighted."""
        self.ax.clear()
        
        if not self.media_info:
            self.ax.text(0.5, 0.5, "Loading waveform...", ha='center', va='center', transform=self.ax.transAxes)
            self.canvas.draw()
            return
        
        # Extract audio for waveform (first 5 minutes or full duration, whichever is shorter)
        duration = min(300.0, self.media_info.duration)
        
        try:
            from intro_tamer.extract_audio import extract_audio_segment
            audio, sr = extract_audio_segment(
                self.video_file,
                start_time=0.0,
                duration=duration,
                audio_stream_index=self.audio_stream_index,
                sample_rate=22050,
            )
            
            # Downsample for display
            downsample_factor = max(1, len(audio) // 10000)
            audio_display = audio[::downsample_factor]
            time_axis = np.arange(len(audio_display)) * downsample_factor / sr
            
            # Plot waveform
            self.ax.plot(time_axis, audio_display, alpha=0.7, linewidth=0.5)
            self.ax.axhline(y=0, color='k', linestyle='-', linewidth=0.5)
            self.ax.set_xlabel('Time (seconds)')
            self.ax.set_ylabel('Amplitude')
            self.ax.set_title('Audio Waveform (First 5 minutes)')
            self.ax.grid(True, alpha=0.3)
            
            # Highlight intro segment
            if self.intro_boundaries and self.intro_boundaries.end <= duration:
                self.ax.axvspan(
                    self.intro_boundaries.start,
                    self.intro_boundaries.end,
                    alpha=0.3,
                    color='red',
                    label='Intro'
                )
            
            # Highlight outro segment (if visible in first 5 min, which is unlikely)
            if self.outro_boundaries and self.outro_boundaries.start < duration:
                end_time = min(self.outro_boundaries.end, duration)
                self.ax.axvspan(
                    self.outro_boundaries.start,
                    end_time,
                    alpha=0.3,
                    color='blue',
                    label='Outro'
                )
            
            self.ax.legend()
            self.canvas.draw()
            
        except Exception as e:
            self.ax.text(0.5, 0.5, f"Error loading waveform: {str(e)}", ha='center', va='center', transform=self.ax.transAxes)
            self.canvas.draw()
    
    def play_intro_original(self):
        """Play intro segment from original file."""
        if not self.intro_boundaries:
            return
        self._play_segment(self.intro_boundaries.start, self.intro_boundaries.end, processed=False)
    
    def play_intro_processed(self):
        """Play intro segment with processing applied."""
        if not self.intro_boundaries:
            return
        self._play_segment(self.intro_boundaries.start, self.intro_boundaries.end, processed=True)
    
    def play_outro_original(self):
        """Play outro segment from original file."""
        if not self.outro_boundaries:
            return
        self._play_segment(self.outro_boundaries.start, self.outro_boundaries.end, processed=False)
    
    def play_outro_processed(self):
        """Play outro segment with processing applied."""
        if not self.outro_boundaries:
            return
        self._play_segment(self.outro_boundaries.start, self.outro_boundaries.end, processed=True)
    
    def _play_segment(self, start: float, end: float, processed: bool):
        """Play audio segment."""
        duration = end - start
        
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
        
        try:
            cmd = [
                "ffmpeg",
                "-i", str(self.video_file),
                "-map", f"0:{self.audio_stream_index}",
                "-ss", str(start),
                "-t", str(duration),
            ]
            
            if processed:
                from intro_tamer.ffmpeg_render import RenderConfig, build_audio_filtergraph
                
                # Create config for the segment we're previewing
                # Adjust boundaries relative to segment start for filter
                segment_config = RenderConfig(
                    intro_start=max(0, (self.intro_boundaries.start if self.intro_boundaries else 0) - start),
                    intro_end=max(0, (self.intro_boundaries.end if self.intro_boundaries else 0) - start),
                    outro_start=max(0, (self.outro_boundaries.start if self.outro_boundaries else 0) - start) if self.outro_boundaries else None,
                    outro_end=max(0, (self.outro_boundaries.end if self.outro_boundaries else 0) - start) if self.outro_boundaries else None,
                    gain_db=self.duck_db,
                    fade_ms=self.fade_ms,
                    audio_stream_index=self.audio_stream_index,
                )
                
                # Only apply filter if segment overlaps with intro/outro
                if (self.intro_boundaries and start < self.intro_boundaries.end and end > self.intro_boundaries.start) or \
                   (self.outro_boundaries and start < self.outro_boundaries.end and end > self.outro_boundaries.start):
                    cmd.extend(["-af", build_audio_filtergraph(segment_config)])
            
            cmd.extend(["-acodec", "aac", "-y", str(tmp_path)])
            
            subprocess.run(cmd, capture_output=True, check=True)
            
            # Play audio
            subprocess.Popen(["afplay", str(tmp_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Clean up temp file after a delay
            threading.Timer(10.0, lambda: tmp_path.unlink() if tmp_path.exists() else None).start()
            
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("Preview Error", f"Could not preview segment: {str(e)}")
            if tmp_path.exists():
                tmp_path.unlink()
    
    def process_file(self):
        """Process the file with current settings."""
        # This would trigger processing in the main GUI
        # For now, just close and let user process from main window
        self.window.destroy()

