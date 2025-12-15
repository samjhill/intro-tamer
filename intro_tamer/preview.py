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
        self.window_closed = False
        
        self.window = tk.Toplevel(parent)
        self.window.title(f"Preview: {video_file.name}")
        self.window.geometry("900x700")
        
        # Track if window is still open
        self.window.protocol("WM_DELETE_WINDOW", lambda: setattr(self, 'window_closed', True) or self.window.destroy())
        
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
        self.intro_label = ttk.Label(intro_frame, text="Detecting...", foreground="blue")
        self.intro_label.pack(side=tk.LEFT, padx=5)
        
        # Outro
        outro_frame = ttk.Frame(segments_frame)
        outro_frame.pack(fill=tk.X, pady=5)
        ttk.Label(outro_frame, text="Outro:", width=10).pack(side=tk.LEFT)
        self.outro_label = ttk.Label(outro_frame, text="Detecting...", foreground="blue")
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
        
        # Action buttons
        action_frame = ttk.Frame(controls_frame)
        action_frame.pack(side=tk.RIGHT, padx=10)
        
        ttk.Button(action_frame, text="Close", command=self.window.destroy).pack(side=tk.LEFT, padx=5)
        
    def detect_segments(self):
        """Detect intro and outro segments."""
        def _update_status(msg):
            """Update status label."""
            if self.window_closed:
                return
            def _update():
                if self.window_closed:
                    return
                try:
                    self.intro_label.config(text=msg, foreground="blue")
                    self.window.update_idletasks()
                except:
                    pass  # Window might be closed
            try:
                self.window.after(0, _update)
            except:
                pass
        
        def _detect():
            try:
                _update_status("Probing media...")
                # Probe media
                self.media_info = probe_media(self.video_file)
                self.audio_stream_index = get_default_audio_stream_index(self.media_info)
                
                _update_status("Loading preset...")
                # Load preset
                loaded_preset = load_preset(self.preset)
                
                # Detect intro
                if loaded_preset.reference_fingerprint:
                    _update_status("Loading fingerprint...")
                    fingerprint_path = Path(loaded_preset.reference_fingerprint)
                    if not fingerprint_path.is_absolute():
                        # Resolve relative to project root (same as cli.py)
                        fingerprint_path = Path(__file__).parent.parent / fingerprint_path
                    
                    if not fingerprint_path.exists():
                        raise FileNotFoundError(f"Fingerprint file not found: {fingerprint_path}")
                    
                    _update_status("Detecting intro (this may take 30-60 seconds)...")
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
                    
                    _update_status("Detecting outro (this may take 30-60 seconds)...")
                    # Detect outro
                    self.outro_boundaries = detector.detect(
                        self.video_file,
                        search_start=0.0,
                        search_duration=min(loaded_preset.search_window_seconds, self.media_info.duration),
                        audio_stream_index=self.audio_stream_index,
                        search_from_end=True,
                    )
                else:
                    _update_status("Using heuristic detection...")
                    # No fingerprint, try heuristic
                    detector = HeuristicDetector(
                        search_window_seconds=loaded_preset.search_window_seconds if loaded_preset else 150.0,
                        min_intro_seconds=15.0,
                        max_intro_seconds=90.0,
                    )
                    self.intro_boundaries = detector.detect(
                        self.video_file,
                        audio_stream_index=self.audio_stream_index,
                    )
                
                # Update UI
                if not self.window_closed:
                    def _finish():
                        if not self.window_closed:
                            self._update_ui()
                    self.window.after(0, _finish)
                
            except Exception as e:
                if not self.window_closed:
                    import traceback
                    error_msg = f"{str(e)}\n{traceback.format_exc()}"
                    def _error():
                        if not self.window_closed:
                            self._show_error(error_msg)
                    self.window.after(0, _error)
        
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
        # Truncate long error messages
        display_msg = error_msg[:100] + "..." if len(error_msg) > 100 else error_msg
        self.intro_label.config(text=f"Error: {display_msg}")
        self.outro_label.config(text="Error - see intro label")
        
        # Also show in a messagebox for full error
        import tkinter.messagebox as mb
        mb.showerror("Detection Error", f"Failed to detect segments:\n\n{error_msg}")
        
        # Draw empty waveform
        self.ax.clear()
        self.ax.text(0.5, 0.5, f"Error: {display_msg}", ha='center', va='center', transform=self.ax.transAxes, wrap=True)
        self.canvas.draw()
    
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
    

