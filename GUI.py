# GUI.py
import json
import requests
import threading
import tkinter as tk
from tkinter import filedialog
import ttkbootstrap as tb
from ttkbootstrap import ttk
from pathlib import Path
from multiprocessing import Manager

import MonsterSirenDownloader

import PIL.Image

# If CUBIC doesn't exist, alias it to BICUBIC
if not hasattr(PIL.Image, "CUBIC"):
    PIL.Image.CUBIC = PIL.Image.BICUBIC


class DownloadGUI(tb.Window):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("MonsterSiren Downloader")

        width = 350
        height = 400
        window_width = self.winfo_screenwidth()  # 取得螢幕寬度
        window_height = self.winfo_screenheight()  # 取得螢幕高度
        left = int((window_width - width) / 2)  # 計算左上 x 座標以置中
        top = int((window_height - height) / 2)  # 計算左上 y 座標以置中
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.resizable(False, False)

        # 載入 gif 圖片
        git_path = Path.cwd() / "resource/pepe.gif"
        self.photoimage_objects = self.get_git_frames(git_path)

        # 儲存下載路徑
        self.download_path = tk.StringVar(value=str(Path.cwd() / "MonsterSiren"))

        # 建立下載器
        queue = Manager().Queue()
        self.downloader = MonsterSirenDownloader.MonsterSirenDownloader(queue)

        # 下載中旗標、背景執行緒
        self.is_downloading = False
        self.download_thread = None

        # 取得總專輯數, 以及已完成的計數(用來更新進度)
        self.total_albums = len(self.downloader.all_albums)
        self.completed_count = 0

        # 介面佈局
        self.create_widgets()

    def create_widgets(self):
        # 路徑選擇 Frame
        frame_path = ttk.Frame(self)
        frame_path.pack(pady=10, fill="x", padx=10)

        label_path = ttk.Label(frame_path, text="下載資料夾:")
        label_path.pack(side="left")

        entry_path = ttk.Entry(frame_path, textvariable=self.download_path, width=20)
        entry_path.pack(side="left", padx=5)

        btn_browse = ttk.Button(frame_path, text="...", command=self.select_folder)
        btn_browse.pack(side="right")

        # 進度條區
        frame_progress = ttk.Frame(self)
        # 進度 Meter (圓形)
        self.meter = tb.Meter(
            frame_progress,
            bootstyle="primary",
            # meterstyle="primary",
            amounttotal=100,
            amountused=0,
            subtext="下載進度",
            interactive=False,
            stripethickness=5,
            metersize=250,
            textright="%",
        )
        self.meter.grid(row=0, column=1, pady=10)

        self.label_gif_1 = ttk.Label(frame_progress)
        self.label_gif_1.grid(row=0, column=0, sticky="s")
        self.label_gif_2 = ttk.Label(frame_progress)
        self.label_gif_2.grid(row=0, column=2, sticky="s")
        frame_progress.pack(pady=10)

        # 按鈕區
        frame_btn = ttk.Frame(self)

        self.btn_start = ttk.Button(
            frame_btn, text="開始下載", command=self.start_download
        )
        self.btn_start.grid(row=0, column=0, padx=5)

        self.btn_stop = ttk.Button(
            frame_btn, text="停止下載", command=self.stop_download, state="disabled"
        )
        self.btn_stop.grid(row=0, column=1, padx=5)
        frame_btn.pack(padx=10, pady=10)

        # 底部狀態顯示
        self.label_status = ttk.Label(self, text="尚未下載")
        self.label_status.pack(side="bottom", pady=10)

    def get_git_frames(self, gif_path):
        # 取得 gif 圖片的所有 frames
        file = Path(gif_path)
        info = PIL.Image.open(file)

        self.frames = info.n_frames
        photoimage_objects = []
        for i in range(self.frames):
            obj = tk.PhotoImage(file=file, format=f"gif -index {i}")
            photoimage_objects.append(obj)
        return photoimage_objects

    def animation(self, ttk_objects, current_frame=0):
        global loop
        image = self.photoimage_objects[current_frame]
        for ttk_object in ttk_objects:
            ttk_object.configure(image=image)
        current_frame = current_frame + 1

        if current_frame == self.frames:
            current_frame = 0

        loop = self.after(50, lambda: self.animation(ttk_objects, current_frame))

    def stop_animation(self, ttk_objects):
        self.after_cancel(loop)
        for ttk_object in ttk_objects:
            ttk_object.configure(image="")

    def select_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.download_path.set(path)

    def start_download(self):
        # 若已在下載中，則不重複開始
        if self.is_downloading:
            return

        self.is_downloading = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.label_status.config(text="開始下載...")

        # 清除舊的 completed_albums.json 進度 (選擇性)
        # path_json = Path(self.download_path.get()) / "completed_albums.json"
        # if path_json.exists():
        #     path_json.unlink()

        # 取得所有專輯
        session = requests.Session()
        all_albums = session.get(
            "https://monster-siren.hypergryph.com/api/albums",
            headers={"Accept": "application/json"},
        ).json()["data"]
        self.total_albums = len(all_albums)

        self.download_thread = threading.Thread(target=self.downloader.run, daemon=True)
        self.download_thread.start()

        # 啟動檢查緒程是否結束的輪詢
        self.animation((self.label_gif_1, self.label_gif_2))
        self.check_thread()

    def check_thread(self):
        """檢查下載緒程是否還活著。"""
        if self.download_thread.is_alive():
            # 如果還在下載，就更新一下進度
            self.update_progress()
            # 0.5 秒後再檢查
            self.after(500, self.check_thread)
        else:
            # 緒程結束，可能代表下載成功或中途停止
            self.update_progress()
            self.finish_download()

    def update_progress(self):
        """
        透過讀取 completed_albums.json 來更新已完成的專輯數量
        以 (completed_count / total_albums * 100) 進行圓形進度。
        """
        if not self.is_downloading:
            self.finish_download()
            return

        # 下載仍在進行 -> 判斷已完成幾張
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

        if self.total_albums > 0:
            percent = int((self.completed_count / self.total_albums) * 100)
        else:
            percent = 0

        self.meter.configure(amountused=percent)
        self.label_status.config(
            text=f"已完成 {self.completed_count}/{self.total_albums}"
        )

        if percent == 100:
            self.finish_download()

    def finish_download(self):
        """
        下載完成後，將進度條設為 100%，並顯示「下載完成」。
        """
        self.stop_animation((self.label_gif_1, self.label_gif_2))
        self.meter.configure(amountused=100)
        self.label_status.config(text="下載完成!")
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.is_downloading = False

    def stop_download(self):
        """
        使用者按下「停止」按鈕，呼叫 downloader 的 stop() 方法。
        """
        if not self.downloader.be_stopped:
            self.label_status.config(text="停止下載中...")
            self.downloader.stop()
            self.label_status.config(text="已強制停止")
            self.is_downloading = False

            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            print("Download stopped")


if __name__ == "__main__":
    # Windows + multiprocessing + tkinter 時，有時需要 freeze_support
    import multiprocessing

    multiprocessing.freeze_support()

    app = DownloadGUI(themename="darkly")
    app.mainloop()
