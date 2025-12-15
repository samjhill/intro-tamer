"""Simple GUI for Intro Tamer."""

import contextlib
import io
import json
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from intro_tamer.cli import process_video_file
from intro_tamer.preview import PreviewWindow


class IntroTamerGUI:
    """Main GUI application for Intro Tamer."""

    def __init__(self, root):
        self.root = root
        self.root.title("Intro Tamer")
        self.root.geometry("800x700")
        
        # Config file path
        self.config_file = Path.home() / ".intro_tamer_config.json"
        
        self.input_folder = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.preset = tk.StringVar(value="office-us")
        self.duck_db = tk.DoubleVar(value=-10.0)
        self.fade_ms = tk.IntVar(value=120)
        self.thread_count = tk.IntVar(value=4)
        
        self.is_processing = False
        self.processing_thread = None
        self.executor = None
        self.video_files = []
        self.current_file_index = 0
        self.processed_count = 0
        self.successful_count = 0
        self.failed_count = 0
        self.lock = threading.Lock()
        
        # Load saved config
        self.load_config()
        
        self.setup_ui()
        
        # Save config when window closes
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def setup_ui(self):
        """Set up the user interface."""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # Title
        title_label = ttk.Label(main_frame, text="Intro Tamer", font=("Arial", 16, "bold"))
        title_label.grid(row=row, column=0, columnspan=3, pady=(0, 20))
        row += 1
        
        # Input folder selection
        ttk.Label(main_frame, text="Input Folder:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.input_folder, width=50).grid(
            row=row, column=1, sticky=(tk.W, tk.E), padx=5, pady=5
        )
        ttk.Button(main_frame, text="Browse...", command=self.select_input_folder).grid(
            row=row, column=2, pady=5
        )
        row += 1
        
        # Output folder selection
        ttk.Label(main_frame, text="Output Folder:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_folder, width=50).grid(
            row=row, column=1, sticky=(tk.W, tk.E), padx=5, pady=5
        )
        ttk.Button(main_frame, text="Browse...", command=self.select_output_folder).grid(
            row=row, column=2, pady=5
        )
        row += 1
        
        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding="10")
        settings_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        settings_frame.columnconfigure(1, weight=1)
        
        settings_row = 0
        
        # Preset selection
        ttk.Label(settings_frame, text="Preset:").grid(row=settings_row, column=0, sticky=tk.W, pady=5)
        self.preset_combo = ttk.Combobox(settings_frame, textvariable=self.preset, width=30, state="readonly")
        self.preset_combo["values"] = ("office-us",)
        self.preset_combo.grid(row=settings_row, column=1, sticky=tk.W, padx=5, pady=5)
        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: self.save_config())
        settings_row += 1
        
        # Duck dB
        ttk.Label(settings_frame, text="Gain Reduction (dB):").grid(row=settings_row, column=0, sticky=tk.W, pady=5)
        duck_frame = ttk.Frame(settings_frame)
        duck_frame.grid(row=settings_row, column=1, sticky=tk.W, padx=5, pady=5)
        duck_scale = ttk.Scale(
            duck_frame,
            from_=-30,
            to=-5,
            variable=self.duck_db,
            orient=tk.HORIZONTAL,
            length=200,
            command=lambda v: self.save_config(),
        )
        duck_scale.pack(side=tk.LEFT)
        ttk.Label(duck_frame, textvariable=self.duck_db, width=6).pack(side=tk.LEFT, padx=5)
        settings_row += 1
        
        # Fade duration
        ttk.Label(settings_frame, text="Fade Duration (ms):").grid(row=settings_row, column=0, sticky=tk.W, pady=5)
        fade_frame = ttk.Frame(settings_frame)
        fade_frame.grid(row=settings_row, column=1, sticky=tk.W, padx=5, pady=5)
        fade_scale = ttk.Scale(
            fade_frame,
            from_=50,
            to=500,
            variable=self.fade_ms,
            orient=tk.HORIZONTAL,
            length=200,
            command=lambda v: self.save_config(),
        )
        fade_scale.pack(side=tk.LEFT)
        ttk.Label(fade_frame, textvariable=self.fade_ms, width=6).pack(side=tk.LEFT, padx=5)
        settings_row += 1
        
        # Thread count
        ttk.Label(settings_frame, text="Threads:").grid(row=settings_row, column=0, sticky=tk.W, pady=5)
        thread_frame = ttk.Frame(settings_frame)
        thread_frame.grid(row=settings_row, column=1, sticky=tk.W, padx=5, pady=5)
        thread_scale = ttk.Scale(
            thread_frame,
            from_=1,
            to=8,
            variable=self.thread_count,
            orient=tk.HORIZONTAL,
            length=200,
            command=lambda v: self.save_config(),
        )
        thread_scale.pack(side=tk.LEFT)
        ttk.Label(thread_frame, textvariable=self.thread_count, width=6).pack(side=tk.LEFT, padx=5)
        settings_row += 1
        
        row += 1
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=10)
        
        self.preview_button = ttk.Button(button_frame, text="Preview First File", command=self.preview_first_file)
        self.preview_button.pack(side=tk.LEFT, padx=5)
        
        self.start_button = ttk.Button(button_frame, text="Start Processing", command=self.start_processing)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        row += 1
        
        # Progress frame
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        progress_frame.columnconfigure(0, weight=1)
        progress_frame.rowconfigure(2, weight=1)
        
        # Current file label
        self.current_file_label = ttk.Label(progress_frame, text="Ready to process...", wraplength=700)
        self.current_file_label.grid(row=0, column=0, sticky=tk.W, pady=5)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            length=700,
        )
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # Status label
        self.status_label = ttk.Label(progress_frame, text="Waiting...")
        self.status_label.grid(row=2, column=0, sticky=tk.W, pady=5)
        
        # Log text area
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10")
        log_frame.grid(row=row + 1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(row + 1, weight=1)
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(log_frame)
        text_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        
        self.log_text = tk.Text(text_frame, height=10, wrap=tk.WORD, font=("Courier", 9))
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
    def load_config(self):
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    if 'input_folder' in config:
                        self.input_folder.set(config['input_folder'])
                    if 'output_folder' in config:
                        self.output_folder.set(config['output_folder'])
                    if 'preset' in config:
                        self.preset.set(config['preset'])
                    if 'duck_db' in config:
                        self.duck_db.set(config['duck_db'])
                    if 'fade_ms' in config:
                        self.fade_ms.set(config['fade_ms'])
                    if 'thread_count' in config:
                        self.thread_count.set(config['thread_count'])
            except Exception as e:
                # If config file is corrupted, just use defaults
                pass
    
    def save_config(self):
        """Save configuration to file."""
        try:
            config = {
                'input_folder': self.input_folder.get(),
                'output_folder': self.output_folder.get(),
                'preset': self.preset.get(),
                'duck_db': self.duck_db.get(),
                'fade_ms': self.fade_ms.get(),
                'thread_count': self.thread_count.get(),
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            # Silently fail if we can't save config
            pass
    
    def on_closing(self):
        """Handle window closing event."""
        self.save_config()
        self.root.destroy()
    
    def select_input_folder(self):
        """Open folder picker for input directory."""
        folder = filedialog.askdirectory(title="Select Input Folder")
        if folder:
            self.input_folder.set(folder)
            self.log(f"Selected input folder: {folder}")
            self.save_config()
            
    def select_output_folder(self):
        """Open folder picker for output directory."""
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder.set(folder)
            self.log(f"Selected output folder: {folder}")
            self.save_config()
    
    def preview_first_file(self):
        """Open preview window for the first file in the input folder."""
        if not self.input_folder.get():
            messagebox.showerror("Error", "Please select an input folder")
            return
        
        # Find first video file
        input_path = Path(self.input_folder.get())
        video_extensions = {".mkv", ".mp4", ".avi", ".mov", ".m4v"}
        video_files = []
        
        for ext in video_extensions:
            video_files.extend(input_path.rglob(f"*{ext}"))
        
        if not video_files:
            messagebox.showwarning("Warning", "No video files found in input folder")
            return
        
        video_files.sort()
        first_file = video_files[0]
        
        # Open preview window
        PreviewWindow(
            self.root,
            first_file,
            self.preset.get(),
            self.duck_db.get(),
            self.fade_ms.get(),
        )
            
    def log(self, message):
        """Add message to log."""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def start_processing(self):
        """Start processing videos."""
        if not self.input_folder.get():
            messagebox.showerror("Error", "Please select an input folder")
            return
            
        if not self.output_folder.get():
            messagebox.showerror("Error", "Please select an output folder")
            return
            
        # Find video files
        input_path = Path(self.input_folder.get())
        video_extensions = {".mkv", ".mp4", ".avi", ".mov", ".m4v"}
        self.video_files = []
        
        for ext in video_extensions:
            self.video_files.extend(input_path.rglob(f"*{ext}"))
            
        self.video_files.sort()
        
        if not self.video_files:
            messagebox.showwarning("Warning", "No video files found in input folder")
            return
            
        self.log(f"Found {len(self.video_files)} video file(s)")
        
        # Update UI
        self.is_processing = True
        self.current_file_index = 0
        self.processed_count = 0
        self.successful_count = 0
        self.failed_count = 0
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self.update_progress(0, len(self.video_files), "Starting processing...")
        
        # Start processing in background thread
        self.processing_thread = threading.Thread(target=self.process_videos, daemon=True)
        self.processing_thread.start()
        
    def stop_processing(self):
        """Stop processing videos."""
        self.is_processing = False
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
        self.log("Stopping processing...")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
    def process_single_file(self, video_file, input_path, output_path):
        """Process a single video file (for multithreading)."""
        if not self.is_processing:
            return None, "stopped"
            
        # Calculate relative path
        try:
            rel_path = video_file.relative_to(input_path)
        except ValueError:
            rel_path = Path(video_file.name)
            
        # Determine output path preserving structure
        output_file = output_path / rel_path.parent / f"{video_file.stem}.intro_tamed{video_file.suffix}"
        
        # Create output directory if needed
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Skip if already processed (resume capability)
        if output_file.exists():
            with self.lock:
                self.processed_count += 1
                self.successful_count += 1
            return rel_path, "skipped"
            
        try:
            # Suppress console output during processing
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                process_video_file(
                    input_file=video_file,
                    output_file=output_file,
                    preset=self.preset.get(),
                    duck_db=self.duck_db.get(),
                    fade_ms=self.fade_ms.get(),
                    report_json=True,
                    keep_codecs=True,
                    allow_fallback=True,
                )
            with self.lock:
                self.processed_count += 1
                self.successful_count += 1
            return rel_path, "success"
        except Exception as e:
            with self.lock:
                self.processed_count += 1
                self.failed_count += 1
            return rel_path, f"error: {str(e)}"
    
    def process_videos(self):
        """Process all video files using multithreading."""
        input_path = Path(self.input_folder.get())
        output_path = Path(self.output_folder.get())
        
        # Filter out already processed files for resume capability
        remaining_files = []
        skipped_count = 0
        
        for video_file in self.video_files:
            try:
                rel_path = video_file.relative_to(input_path)
            except ValueError:
                rel_path = Path(video_file.name)
                
            output_file = output_path / rel_path.parent / f"{video_file.stem}.intro_tamed{video_file.suffix}"
            
            if output_file.exists():
                skipped_count += 1
                with self.lock:
                    self.processed_count += 1
                    self.successful_count += 1
                self.log(f"Skipping (already exists): {rel_path}")
            else:
                remaining_files.append(video_file)
        
        if skipped_count > 0:
            self.log(f"Resuming: {skipped_count} already processed, {len(remaining_files)} remaining")
            # Update progress for skipped files
            self.update_progress(skipped_count, len(self.video_files), f"Resuming: {skipped_count} already processed")
        
        if not remaining_files:
            self.log("All files already processed!")
            self.is_processing = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.update_progress(len(self.video_files), len(self.video_files), "All files already processed!")
            self.status_label.config(text=f"Complete! All {len(self.video_files)} files already processed")
            messagebox.showinfo("Complete", f"All {len(self.video_files)} files are already processed!")
            return
        
        # Process remaining files with multithreading
        thread_count = self.thread_count.get()
        self.log(f"Processing {len(remaining_files)} files with {thread_count} thread(s)...")
        self.update_progress(skipped_count, len(self.video_files), f"Starting processing with {thread_count} thread(s)...")
        
        self.executor = ThreadPoolExecutor(max_workers=thread_count)
        futures = {}
        
        for video_file in remaining_files:
            if not self.is_processing:
                break
            future = self.executor.submit(self.process_single_file, video_file, input_path, output_path)
            futures[future] = video_file
        
        # Process completed tasks
        for future in as_completed(futures):
            if not self.is_processing:
                break
                
            rel_path, result = future.result()
            
            if result == "stopped":
                break
            elif result == "skipped":
                # Already logged and counted
                pass
            elif result == "success":
                self.log(f"✓ Success: {rel_path.name}")
            elif result.startswith("error"):
                error_msg = result.split(":", 1)[1] if ":" in result else result
                self.log(f"✗ Error processing {rel_path.name}: {error_msg}")
            
            # Update progress after each completion
            with self.lock:
                current = self.processed_count
            rel_name = rel_path.name if isinstance(rel_path, Path) else str(rel_path)
            self.update_progress(current, len(self.video_files), f"Processing: {rel_name}")
        
        # Shutdown executor
        if self.executor:
            self.executor.shutdown(wait=True)
            self.executor = None
                
        # Processing complete
        self.is_processing = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        with self.lock:
            successful = self.successful_count
            failed = self.failed_count
        
        self.log(f"\nProcessing complete!")
        self.log(f"  Successful: {successful}")
        self.log(f"  Failed: {failed}")
        self.log(f"  Total: {len(self.video_files)}")
        
        self.status_label.config(text=f"Complete! {successful} successful, {failed} failed")
        messagebox.showinfo("Complete", f"Processing complete!\n\nSuccessful: {successful}\nFailed: {failed}")
        
    def update_progress(self, current, total, message):
        """Update progress bar and status (thread-safe)."""
        def _update():
            try:
                percentage = (current / total) * 100 if total > 0 else 0
                self.progress_var.set(percentage)
                self.current_file_label.config(text=message)
                self.status_label.config(text=f"Processing {current} of {total} files ({percentage:.1f}%)")
            except Exception as e:
                # Silently handle any UI update errors
                pass
        
        # Schedule UI update on main thread
        self.root.after(0, _update)


def main():
    """Launch the GUI application."""
    root = tk.Tk()
    app = IntroTamerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

