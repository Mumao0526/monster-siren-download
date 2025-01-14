import json
import requests
import logging
from multiprocessing import Manager
from pathlib import Path
from .TaskManager import TaskManager
from .DownloadWorker import DownloadWorker


class MonsterSirenDownloader:
    def __init__(self, download_dir="./MonsterSiren/", max_workers=None):
        self.directory = Path(download_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.task_manager = TaskManager(max_workers)
        logging.basicConfig(
            filename=self.directory / "downloader.log",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def run(self):
        # 初始化下載任務
        self.all_albums = self.get_albums()
        self.unfinished_albums = self.compare_ablums(
            self.all_albums, self.directory / "completed_albums.json"
        )
        tasks = self.unfinished_albums

        # 開始下載
        worker = DownloadWorker(
            directory=self.directory,
            stop_event=self.task_manager.stop_event,
            mutex=self.task_manager.mutex
        )
        try:
            self.task_manager.start(tasks, worker.download_album)
        except KeyboardInterrupt:
            print("Interrupted! Stopping downloads...")
            self.task_manager.stop()

    def get_albums(self):
        # 從 API 獲取專輯列表
        session = requests.Session()
        response = session.get(
            "https://monster-siren.hypergryph.com/api/albums",
            headers={"Accept": "application/json"},
        )
        return response.json()["data"]

    def compare_ablums(self, all_albums, completed_list_path):
        # 比較已下載的專輯和所有專輯，返回未完成的專輯
        if not completed_list_path.exists():
            with open(completed_list_path, "w+", encoding="utf8") as f:
                json.dump([], f)
            logging.info("Adding all albums to download queue")
            return all_albums

        with open(completed_list_path, "r", encoding="utf8") as f:
            completed_albums = json.load(f)

        unfinished_albums = []
        for album in all_albums:
            if album["name"] not in completed_albums:
                unfinished_albums.append(album)
        logging.info(f"Adding {len(unfinished_albums)} albums to download queue")
        return unfinished_albums

    def stop(self):
        self.task_manager.stop()
