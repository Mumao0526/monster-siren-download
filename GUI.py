# GUI.py
import os
import sys
import json
import threading
import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
import ttkbootstrap as tb
from ttkbootstrap import ttk
from pathlib import Path

from downloader.MonsterSirenDownloader import MonsterSirenDownloader

import PIL.Image

# If CUBIC doesn't exist, alias it to BICUBIC
if not hasattr(PIL.Image, "CUBIC"):
    PIL.Image.CUBIC = PIL.Image.BICUBIC


def resource_path(relative_path):
    """Get absolute path of resource file. Used for PyInstaller.

    Args:
        relative_path (str): The relative path of resource file.

    Returns:
        str: The absolute path of resource file.
    """
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class DownloadGUI(tb.Window):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("MonsterSiren Downloader")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)  # close window event

        # Set favicon
        self.iconbitmap(Path.cwd() / resource_path("resource/favicon.ico"))  # Windows
        favicon = tk.PhotoImage(file=Path.cwd() / resource_path("resource/favicon.png"))
        self.iconphoto(True, favicon)  # Linux / macOS

        width = 350
        height = 400
        window_width = self.winfo_screenwidth()  # get screen width
        window_height = self.winfo_screenheight()  # get screen height
        # set window to center
        left = int((window_width - width) / 2)
        top = int((window_height - height) / 2)
        self.geometry(f"{width}x{height}+{left}+{top}")
        # self.resizable(False, False)

        # load gif image
        git_path = Path.cwd() / resource_path("resource/pepe.gif")
        self.animation_images = self.get_git_frames(git_path)

        # Where to download
        self.download_path = tk.StringVar(value=str(Path.cwd() / "MonsterSiren"))

        # flag
        self.is_downloading = False

        self.create_widgets()

    def create_widgets(self):
        # Frame of the download path area
        frame_path = ttk.Frame(self)
        frame_path.pack(pady=10, fill="x", padx=10)

        label_path = ttk.Label(frame_path, text="Save Path:")
        label_path.pack(side="left")

        entry_path = ttk.Entry(frame_path, textvariable=self.download_path)
        entry_path.pack(side="left", padx=5, fill="x", expand=True)

        btn_browse = ttk.Button(frame_path, text="...", command=self.select_folder)
        btn_browse.pack(side="right")

        # Frame of the progress area
        frame_progress = ttk.Frame(self)
        # progress circle bar
        self.meter = tb.Meter(
            frame_progress,
            bootstyle="primary",
            # meterstyle="primary",
            amounttotal=100,
            amountused=0,
            subtext="Progress",
            interactive=False,
            stripethickness=5,
            metersize=150,
            textright="%",
        )
        self.meter.grid(row=0, column=1, pady=10)

        self.label_gif_1 = ttk.Label(frame_progress)
        self.label_gif_1.grid(row=0, column=0, sticky="se")
        self.label_gif_2 = ttk.Label(frame_progress)
        self.label_gif_2.grid(row=0, column=2, sticky="sw")
        frame_progress.pack(pady=10)

        # Frame of the button area
        frame_btn = ttk.Frame(self)

        self.btn_start = ttk.Button(
            frame_btn, text="Start", command=self.start_download
        )
        self.btn_start.grid(row=0, column=0, padx=5)

        self.btn_stop = ttk.Button(
            frame_btn, text="Stop", command=self.stop_download, state="disabled"
        )
        self.btn_stop.grid(row=0, column=1, padx=5)
        frame_btn.pack(padx=10, pady=10)

        # Status label on the bottom
        self.label_status = ttk.Label(self, text="Waiting for download start...")
        self.label_status.pack(side="bottom", pady=10)

    def get_git_frames(self, gif_path):
        """Get all frames of gif image.

        Args:
            gif_path (str): The path of gif image.

        Returns:
            list: A list of PhotoImage objects.
        """
        # get gif frames
        file = Path(gif_path)
        info = PIL.Image.open(file)

        self.frames = info.n_frames
        photoimage_objects = []
        for i in range(self.frames):
            obj = tk.PhotoImage(file=file, format=f"gif -index {i}")
            photoimage_objects.append(obj)
        return photoimage_objects

    def animation(self, ttk_objects, current_frame=0):
        """Play gif animation.

        Args:
            ttk_objects (list): A list of ttk widgets.
            current_frame (int, optional): The current frame index. Defaults to 0.
        """
        global loop  # prevent garbage collection
        image = self.animation_images[current_frame]
        for ttk_object in ttk_objects:
            # update image
            ttk_object.configure(image=image)
        current_frame = current_frame + 1

        if current_frame == self.frames:
            current_frame = 0

        loop = self.after(50, lambda: self.animation(ttk_objects, current_frame))

    def stop_animation(self, ttk_objects):
        """Stop gif animation.

        Args:
            ttk_objects (list): A list of ttk widgets.
        """
        self.after_cancel(loop)
        for ttk_object in ttk_objects:
            ttk_object.configure(image="")

    def select_folder(self):
        """Select download folder"""
        path = filedialog.askdirectory()
        if path:
            self.download_path.set(path)

    def start_download(self):
        """Start download thread."""
        if self.is_downloading:
            return

        self.is_downloading = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.label_status.config(text="Downloading...")

        # create downloader
        self.downloader = MonsterSirenDownloader(self.download_path.get())
        self.total_albums = len(self.downloader.get_albums())

        # create download thread and start
        self.download_thread = threading.Thread(target=self.downloader.run, daemon=True)
        self.download_thread.start()

        # play gif animation
        self.animation((self.label_gif_1, self.label_gif_2))
        self.check_thread()  # check download thread status

    def check_thread(self):
        """Check download thread status."""
        if self.download_thread.is_alive():
            # is downloading -> update progress
            self.update_progress()
            # 0.5 sec check once
            self.after(500, self.check_thread)
        else:
            # download thread is finished
            self.update_progress()
            self.finish_download()

    def update_progress(self):
        """Update download progress."""
        if not self.is_downloading:
            return

        # count completed albums
        path_json = Path(self.download_path.get()) / "completed_albums.json"
        if path_json.exists():
            try:
                with open(path_json, "r", encoding="utf-8") as f:
                    completed_albums = json.load(f)
                self.completed_count = len(completed_albums)
            except:
                self.completed_count = 0
        else:
            self.completed_count = 0

        # update progress bar
        if self.total_albums > 0:
            percent = int((self.completed_count / self.total_albums) * 100)
        else:
            percent = 0

        self.meter.configure(amountused=percent)
        self.label_status.config(
            text=f"{self.completed_count}/{self.total_albums} completed."
        )

        if percent == 100:
            self.finish_download()

    def finish_download(self):
        """Finish download."""
        self.stop_animation((self.label_gif_1, self.label_gif_2))
        self.meter.configure(amountused=100)
        self.label_status.config(text="Completed.")
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.is_downloading = False

    def stop_download(self):
        """Stop download thread."""
        if self.download_thread.is_alive():
            self.label_status.config(text="Stopping...")
            self.downloader.stop()  # stop downloader
            self.label_status.config(text="Download stopped.")
            self.is_downloading = False

            self.stop_animation((self.label_gif_1, self.label_gif_2))
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")

    def on_closing(self):
        """Close window event."""
        if self.is_downloading and messagebox.askyesno(
            "Warn", "In downloading, are you sure to exit?"
        ):
            self.stop_download()
        self.destroy()  # close window


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()  # For Windows

    app = DownloadGUI(themename="darkly")
    app.mainloop()
