import os
import shutil
import threading
import queue
import random
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
import yt_dlp

# --- Configuration ---
APP_TITLE = "Pro YouTube Audio Downloader"
APP_SIZE = "780x580"

# --- Logic / Backend ---

def is_ffmpeg_installed():
    """Checks if FFmpeg is available in the system PATH."""
    return shutil.which("ffmpeg") is not None

def make_ydl_opts(
    out_dir: str,
    to_mp3: bool,
    audio_quality: str,
    allow_playlist: bool,
    filename_template: str,
    embed_metadata: bool,
    embed_thumbnail: bool,
    safe_mode: bool,
    progress_hook,
    cancel_event: threading.Event,
):
    """Generates the dictionary of options for yt-dlp."""
    
    # Path construction
    outtmpl = os.path.join(out_dir, filename_template)

    # Post-processing (Conversion/Metadata)
    postprocessors = []
    if to_mp3:
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": audio_quality,
        })
    
    if embed_metadata:
        postprocessors.append({"key": "FFmpegMetadata"})
        
    if embed_thumbnail:
        postprocessors.append({"key": "EmbedThumbnail"})

    # Hook to handle cancellation
    def guarded_hook(d):
        if cancel_event.is_set():
            raise yt_dlp.utils.DownloadError("Cancelled by user")
        progress_hook(d)

    # Rate Limiting / Sleep Logic
    # If Safe Mode is ON, we sleep between videos to avoid YouTube bans (HTTP 429)
    sleep_opts = {}
    if safe_mode:
        sleep_opts = {
            "sleep_interval": 5,      # Minimum sleep seconds
            "max_sleep_interval": 15, # Maximum sleep seconds
            "sleep_requests": 1.5,    # Sleep between metadata requests
        }

    return {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": not allow_playlist,
        "ignoreerrors": True,  # Skip errors (like deleted videos in playlist)
        "retries": 10,
        "fragment_retries": 10,
        # Reduce concurrency to look less like a bot
        "concurrent_fragment_downloads": 1, 
        "overwrites": False,
        "windowsfilenames": True,
        "progress_hooks": [guarded_hook],
        "postprocessors": postprocessors,
        "writethumbnail": embed_thumbnail,
        "quiet": True,
        "no_warnings": True,
        **sleep_opts
    }

# --- GUI / Frontend ---

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Setup Window
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.minsize(700, 500)

        # State Variables
        self.event_q = queue.Queue()
        self.worker_thread = None
        self.cancel_event = threading.Event()
        self.ffmpeg_ready = is_ffmpeg_installed()

        # UI Variables
        self.url_var = tk.StringVar()
        self.path_var = tk.StringVar(value=os.path.expanduser("~/Music"))
        self.status_var = tk.StringVar(value="Ready.")
        self.progress_val = tk.DoubleVar(value=0.0)
        
        # Options Variables
        self.opt_playlist = tk.BooleanVar(value=True)
        self.opt_mp3 = tk.BooleanVar(value=True)
        self.opt_metadata = tk.BooleanVar(value=True)
        self.opt_thumbnail = tk.BooleanVar(value=False)
        self.opt_safe_mode = tk.BooleanVar(value=True) # Defaults to Safe Mode ON
        self.opt_quality = tk.StringVar(value="0") # 0 = Best
        self.opt_template = tk.StringVar(value="%(title)s.%(ext)s")

        self.draw_ui()
        self.check_ffmpeg_status()
        self.after(100, self.process_events)

    def draw_ui(self):
        # Grid Configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- 1. Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        title = ctk.CTkLabel(header, text="YouTube Audio Downloader", font=("Roboto", 24, "bold"))
        title.pack(side="left")
        
        if not self.ffmpeg_ready:
            warn = ctk.CTkLabel(header, text="⚠️ FFmpeg Missing!", text_color="#FF5555", font=("Arial", 14, "bold"))
            warn.pack(side="right")
        
        # --- 2. Input Section ---
        input_frame = ctk.CTkFrame(self)
        input_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        input_frame.grid_columnconfigure(1, weight=1)

        # URL Input
        ctk.CTkLabel(input_frame, text="URL:").grid(row=0, column=0, padx=15, pady=15, sticky="w")
        self.entry_url = ctk.CTkEntry(input_frame, textvariable=self.url_var, placeholder_text="Paste Video or Playlist Link...")
        self.entry_url.grid(row=0, column=1, padx=(0, 10), pady=15, sticky="ew")
        
        btn_paste = ctk.CTkButton(input_frame, text="Paste", width=60, command=self.paste_clipboard)
        btn_paste.grid(row=0, column=2, padx=(0, 15), pady=15)

        # Folder Input
        ctk.CTkLabel(input_frame, text="Save to:").grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
        self.entry_path = ctk.CTkEntry(input_frame, textvariable=self.path_var)
        self.entry_path.grid(row=1, column=1, padx=(0, 10), pady=(0, 15), sticky="ew")
        
        btn_browse = ctk.CTkButton(input_frame, text="Browse", width=60, command=self.browse_folder)
        btn_browse.grid(row=1, column=2, padx=(0, 15), pady=(0, 15))

        # --- 3. Options & Log Section ---
        center_frame = ctk.CTkFrame(self)
        center_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        center_frame.grid_columnconfigure(0, weight=1)
        center_frame.grid_rowconfigure(1, weight=1)

        # Options Row
        opts_box = ctk.CTkFrame(center_frame, fg_color="transparent")
        opts_box.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        # Checkboxes
        ctk.CTkCheckBox(opts_box, text="Playlist", variable=self.opt_playlist).pack(side="left", padx=10)
        ctk.CTkCheckBox(opts_box, text="Convert to MP3", variable=self.opt_mp3).pack(side="left", padx=10)
        
        # Safe Mode Switch (Important for Rate Limit)
        safe_switch = ctk.CTkSwitch(opts_box, text="Safe Mode (Anti-Ban)", variable=self.opt_safe_mode)
        safe_switch.pack(side="right", padx=10)

        # Console Log
        self.console = ctk.CTkTextbox(center_frame, font=("Consolas", 12))
        self.console.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.log("System Ready.")
        if not self.ffmpeg_ready:
            self.log("CRITICAL ERROR: FFmpeg not found. Please install FFmpeg to convert audio.")

        # --- 4. Controls & Progress ---
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")
        bottom_frame.grid_columnconfigure(0, weight=1)

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(bottom_frame)
        self.progress_bar.grid(row=0, column=0, columnspan=2, padx=0, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)

        # Status Label
        self.lbl_status = ctk.CTkLabel(bottom_frame, textvariable=self.status_var, anchor="w", text_color="gray")
        self.lbl_status.grid(row=1, column=0, sticky="w")

        # Buttons
        self.btn_start = ctk.CTkButton(bottom_frame, text="Start Download", command=self.start_download, height=40, font=("Arial", 14, "bold"))
        self.btn_start.grid(row=1, column=1, padx=(0, 10), sticky="e")
        
        self.btn_cancel = ctk.CTkButton(bottom_frame, text="Cancel", command=self.cancel_download, height=40, fg_color="#C62828", hover_color="#B71C1C", state="disabled")
        self.btn_cancel.grid(row=1, column=2, sticky="e")

    # --- Actions ---

    def check_ffmpeg_status(self):
        if not self.ffmpeg_ready:
            messagebox.showwarning("FFmpeg Missing", "FFmpeg was not found on your system.\n\nDownloads will work, but conversion to MP3 will fail.\nPlease install FFmpeg and restart the app.")
            self.opt_mp3.set(False)

    def paste_clipboard(self):
        try:
            self.url_var.set(self.clipboard_get())
        except:
            pass

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)

    def log(self, message):
        self.console.insert("end", f"> {message}\n")
        self.console.see("end")

    def toggle_inputs(self, enable: bool):
        state = "normal" if enable else "disabled"
        self.btn_start.configure(state=state)
        self.btn_cancel.configure(state="disabled" if enable else "normal")
        self.entry_url.configure(state=state)
        # We generally don't disable the log or other tabs so user can read them

    # --- Threading Logic ---

    def start_download(self):
        url = self.url_var.get().strip()
        path = self.path_var.get().strip()
        
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL.")
            return
        if not os.path.isdir(path):
            messagebox.showerror("Error", "Invalid output directory.")
            return

        self.toggle_inputs(False)
        self.cancel_event.clear()
        self.progress_bar.set(0)
        self.progress_val.set(0)
        self.status_var.set("Initializing...")
        self.log("-" * 40)
        self.log(f"Starting download: {url}")
        
        if self.opt_safe_mode.get():
            self.log("Safe Mode ON: Downloads will be slower to prevent rate-limits.")

        # Run in separate thread
        self.worker_thread = threading.Thread(target=self.run_downloader, args=(url, path), daemon=True)
        self.worker_thread.start()

    def cancel_download(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.cancel_event.set()
            self.status_var.set("Cancelling...")
            self.log("Requesting cancellation...")
            # Button logic handled in process_events when thread dies

    def run_downloader(self, url, path):
        try:
            opts = make_ydl_opts(
                out_dir=path,
                to_mp3=self.opt_mp3.get(),
                audio_quality=self.opt_quality.get(),
                allow_playlist=self.opt_playlist.get(),
                filename_template=self.opt_template.get(),
                embed_metadata=self.opt_metadata.get(),
                embed_thumbnail=self.opt_thumbnail.get(),
                safe_mode=self.opt_safe_mode.get(),
                progress_hook=lambda d: self.event_q.put(("progress", d)),
                cancel_event=self.cancel_event
            )

            with yt_dlp.YoutubeDL(opts) as ydl:
                # Pre-fetch info to log title
                try:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', 'Unknown')
                    self.event_q.put(("log", f"Found: {title}"))
                except:
                    pass # Continue to download attempt anyway
                
                ydl.download([url])
            
            self.event_q.put(("done", "All tasks completed successfully."))

        except Exception as e:
            self.event_q.put(("error", str(e)))

    def process_events(self):
        try:
            while True:
                msg, data = self.event_q.get_nowait()
                
                if msg == "progress":
                    status = data.get('status')
                    if status == 'downloading':
                        # Calculate percentage
                        total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
                        downloaded = data.get('downloaded_bytes') or 0
                        if total > 0:
                            percent = downloaded / total
                            self.progress_bar.set(percent)
                            self.status_var.set(f"Downloading: {percent:.1%}")
                    elif status == 'finished':
                        self.progress_bar.set(1)
                        self.status_var.set("Processing audio (FFmpeg)...")
                        self.log("Download complete. Converting...")

                elif msg == "log":
                    self.log(data)

                elif msg == "done":
                    self.status_var.set("Finished.")
                    self.log(data)
                    self.toggle_inputs(True)
                    messagebox.showinfo("Success", "Download Complete!")

                elif msg == "error":
                    # Check if it was a user cancel
                    if "Cancelled by user" in data:
                        self.status_var.set("Cancelled.")
                        self.log("Operation cancelled by user.")
                    else:
                        self.status_var.set("Error occurred.")
                        self.log(f"ERROR: {data}")
                        messagebox.showerror("Error", f"An error occurred:\n{data}")
                    self.toggle_inputs(True)
                    self.progress_bar.set(0)

        except queue.Empty:
            pass
        
        self.after(100, self.process_events)

if __name__ == "__main__":
    app = App()
    app.mainloop()
