import os
import shutil
import time
import json
import requests
import pylrc
import multiprocessing
from multiprocessing import Pool, Manager
from pathlib import Path
from tqdm import tqdm
from PIL import Image
from pydub import AudioSegment
from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, SYLT, Encoding, ID3
from mutagen.flac import Picture, FLAC


class MonsterSirenDownloader:
    def __init__(self, task, download_dir=None):
        """
        下載器建構子。

        :param download_dir: 指定下載路徑，若未給定則預設為當前目錄的 ./MonsterSiren/
        """
        if download_dir is None:
            download_dir = "./MonsterSiren/"
        self.directory = Path(download_dir)
        self.directory.mkdir(parents=True, exist_ok=True)

        self.all_albums = []

        # Queue 用來在下載完每張專輯後，通知「消費者」更新 completed_albums.json
        self.queue = task

        # 建立一個多進程共享的布林旗標
        # 當 self.be_stopped = True 時，下載程序應該優雅地停止
        self.be_stopped = False

    def make_valid(self, filename):
        # Make a filename valid in different OS
        f = filename.replace(":", "_")
        f = f.replace("/", "_")
        f = f.replace("<", "_")
        f = f.replace(">", "_")
        f = f.replace("'", "_")
        f = f.replace("\\", "_")
        f = f.replace("|", "_")
        f = f.replace("?", "_")
        f = f.replace("*", "_")
        f = f.replace(" ", "_")
        return f

    def lyric_file_to_text(self, filename):
        with open(filename, "r", encoding="utf-8") as lrc_file:
            lrc_string = lrc_file.read()
        subs = pylrc.parse(lrc_string)
        ret = []
        for sub in subs:
            time_ms = int(sub.time * 1000)
            text = sub.text
            ret.append((text, time_ms))
        return ret

    def update_downloaded_albums(self, queue, directory):
        """
        不斷從 queue 裏讀取完成的專輯名稱，並追加到 completed_albums.json。
        如若偵測到 None 或 be_stopped，就結束。
        """
        while True:
            if self.be_stopped:
                print("Stop flag detected, break update_downloaded_albums.")
                break

            album_name = queue.get()
            if album_name is None:
                print("Got sentinel (None), break update_downloaded_albums.")
                break

            try:
                with open(
                    directory / "completed_albums.json", "r", encoding="utf8"
                ) as f:
                    completed_albums = json.load(f)
            except:
                completed_albums = []

            completed_albums.append(album_name)
            with open(directory / "completed_albums.json", "w+", encoding="utf8") as f:
                json.dump(completed_albums, f)

    def fill_metadata(
        self,
        filename,
        filetype,
        album,
        title,
        albumartist,
        artist,
        tracknumber,
        albumcover,
        songlyricpath,
    ):
        if filetype == ".mp3":
            file = EasyID3(filename)
        else:
            file = FLAC(filename)

        file["album"] = album
        file["title"] = title
        file["albumartist"] = "".join(albumartist)
        file["artist"] = "".join(artist)
        file["tracknumber"] = str(tracknumber + 1)
        file.save()

        if filetype == ".mp3":
            file = ID3(filename)
            file.add(
                APIC(
                    mime="image/png",
                    type=3,
                    desc="Cover",
                    data=open(albumcover, "rb").read(),
                )
            )
            # Read and add lyrics
            if songlyricpath is not None:
                sylt = self.lyric_file_to_text(songlyricpath)
                file.setall(
                    "SYLT",
                    [
                        SYLT(
                            encoding=Encoding.UTF8,
                            lang="eng",
                            format=2,
                            type=1,
                            text=sylt,
                        )
                    ],
                )
            file.save()
        else:
            flac_file = file  # Renaming just for clarity
            image = Picture()
            image.type = 3
            image.desc = "Cover"
            image.mime = "image/png"
            with open(albumcover, "rb") as f:
                image.data = f.read()
            with Image.open(albumcover) as imagePil:
                image.width, image.height = imagePil.size
                image.depth = 24
            flac_file.add_picture(image)
            # Read and add lyrics
            if songlyricpath is not None:
                musiclrc = open(songlyricpath, "r", encoding="utf-8").read()
                flac_file["lyrics"] = musiclrc
            flac_file.save()

    def download_song(self, session, directory, name, url):
        """
        單首歌曲下載。回傳 (filename, filetype)，若失敗回傳 (None, None)。
        這裡也可以在迴圈中檢查 be_stopped，若想更即時停止，可在迴圈中檢查。
        """
        if self.be_stopped:
            return None, None

        source = session.get(url, stream=True)
        filename = Path(directory) / self.make_valid(name)
        filetype = ""

        content_type = source.headers.get("content-type", "")
        if content_type == "audio/mpeg":
            filename = filename.with_suffix(".mp3")
            filetype = ".mp3"
        else:
            filename = filename.with_suffix(".wav")
            filetype = ".wav"

        total = int(source.headers.get("content-length", 0))
        with open(filename, "wb") as f, tqdm(
            desc=name,
            total=total,
            unit="iB",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for data in source.iter_content(chunk_size=1024):
                # 若偵測到停止旗標，可在這裡中斷
                if self.be_stopped:
                    return None, None
                size = f.write(data)
                bar.update(size)

        # 如果是 wav 檔，需要轉成 flac
        if filetype == ".wav":
            try:
                AudioSegment.from_wav(str(filename)).export(
                    str(Path(directory) / f"{self.make_valid(name)}.flac"),
                    format="flac",
                )
            except Exception as e:
                print(f"Error converting {name} to flac: {e}")
                return None, None

            os.remove(filename)
            filename = Path(directory) / f"{self.make_valid(name)}.flac"
            filetype = ".flac"

        return filename, filetype

    def download_album(self, args):
        """
        下載單張專輯的所有歌曲。
        """
        if self.be_stopped:
            return  # 若一開始就檢查到停止旗標，直接返回

        session = requests.Session()
        directory = args["directory"]
        queue = args["queue"]

        album_cid = args["cid"]
        album_name = args["name"]
        album_coverUrl = args["coverUrl"]
        album_artistes = args["artistes"]
        album_url = f"https://monster-siren.hypergryph.com/api/album/{album_cid}/detail"

        album_directory = directory / self.make_valid(album_name)
        album_directory.mkdir(parents=True, exist_ok=True)

        # 下載專輯封面
        with open(album_directory / "cover.jpg", "wb") as f:
            f.write(session.get(album_coverUrl).content)

        # 轉成 png
        cover = Image.open(album_directory / "cover.jpg")
        cover.save(album_directory / "cover.png")
        os.remove(album_directory / "cover.jpg")

        # 取得專輯內歌曲清單
        songs = session.get(album_url, headers={"Accept": "application/json"}).json()[
            "data"
        ]["songs"]

        for song_track_number, song in enumerate(songs):
            if self.be_stopped:
                print(f"[{album_name}] Stop flag detected, break song loop.")
                return

            song_cid = song["cid"]
            song_name = song["name"]
            song_artists = song["artistes"]
            song_url = f"https://monster-siren.hypergryph.com/api/song/{song_cid}"
            song_detail = session.get(
                song_url, headers={"Accept": "application/json"}
            ).json()["data"]
            song_lyricUrl = song_detail["lyricUrl"]
            song_sourceUrl = song_detail["sourceUrl"]

            # 下載歌詞
            if song_lyricUrl is not None:
                songlyricpath = album_directory / f"{self.make_valid(song_name)}.lrc"
                with open(songlyricpath, "wb") as f:
                    f.write(session.get(song_lyricUrl).content)
            else:
                songlyricpath = None

            # 下載歌曲 (最多嘗試 5 次)
            max_retries = 5
            downloaded = False
            for attempt in range(max_retries):
                if self.be_stopped:
                    print(f"[{album_name} - {song_name}] Stop flag detected.")
                    return

                try:
                    filename, filetype = self.download_song(
                        session=session,
                        directory=album_directory,
                        name=song_name,
                        url=song_sourceUrl,
                    )

                    if filename is None or filetype is None:
                        raise ValueError(f"Failed to download/convert song {song_name}")

                    self.fill_metadata(
                        filename=filename,
                        filetype=filetype,
                        album=album_name,
                        title=song_name,
                        albumartist=album_artistes,
                        artist=song_artists,
                        tracknumber=song_track_number,
                        albumcover=album_directory / "cover.png",
                        songlyricpath=songlyricpath,
                    )
                    downloaded = True
                    break
                except Exception as e:
                    print(
                        f"[{album_name} - {song_name}] Download/metadata attempt {attempt+1} failed: {e}"
                    )
                    time.sleep(1)

            if not downloaded:
                # Giving up this album
                with open(directory / "error.log", "a", encoding="utf-8") as log:
                    log.write(
                        f"[{album_name} - {song_name}] Failed 5 times, giving up this album.\n"
                    )
                shutil.rmtree(album_directory, ignore_errors=True)
                return

        # 全部歌曲下載、Metadata 填寫完畢，放進 queue，讓消費者更新 completed_albums.json
        queue.put(album_name)

    def get_unfinished_albums(self, directory, albums):
        if not (directory / "completed_albums.json").exists():
            with open(directory / "completed_albums.json", "w+", encoding="utf8") as f:
                json.dump([], f)
            print("Adding all albums to download queue")
            return albums

        with open(directory / "completed_albums.json", "r", encoding="utf8") as f:
            completed_albums = json.load(f)

        unfinished_albums = []
        for album in albums:
            if album["name"] not in completed_albums:
                unfinished_albums.append(album)
                print(f"Adding {album['name']} to download queue")
        return unfinished_albums

    def run(self):
        """
        整個下載流程的進入點，啟動 Pool 並開始下載。
        通常可以在 GUI 中呼叫 this.run() 來執行。
        """
        # 重置停止旗標
        self.be_stopped = False

        # 取得所有專輯
        session = requests.Session()
        self.all_albums = session.get(
            "https://monster-siren.hypergryph.com/api/albums",
            headers={"Accept": "application/json"},
        ).json()["data"]

        unfinished_albums = self.get_unfinished_albums(self.directory, self.all_albums)
        if len(unfinished_albums) == 0:
            print("All albums have already been downloaded.")
            return

        # 製作每張專輯下載時所需的參數
        for album in unfinished_albums:
            album["directory"] = self.directory
            album["queue"] = self.queue

        # 建立進程池
        pool = Pool(os.cpu_count(), maxtasksperchild=1)

        # 先啟動消費者
        pool.apply_async(
            self.update_downloaded_albums,
            (
                self.queue,
                self.directory,
            ),
        )

        # 啟動主要下載流程 (生產者)
        downloader_result = pool.map_async(self.download_album, unfinished_albums)

        # 等待所有下載任務完成
        self.wait_for_finish(pool, downloader_result)

        print("All albums are downloaded.")

    def wait_for_finish(self, pool, downloader_result):
        """
        不斷等待 downloader_result 完成。
        若使用者在 GUI 端呼叫 stop()，則會把 self.be_stopped 設為 True，
        子行程在下一輪檢查時會自行結束。
        """
        try:
            while not downloader_result.ready():
                if self.be_stopped:
                    print("Detected be_stopped in loop. Will break.")
                    break
                print("Waiting for downloader...")
                downloader_result.wait()
            if downloader_result.successful():
                print("Download process successful.")
            else:
                print("Download process failed.")
                downloader_result.get()  # 這裡會拋出例外
        except KeyboardInterrupt:
            print("Keyboard interrupt. Terminating pool.")
            pool.terminate()
        finally:
            # 結束前，一定要送個 None，讓消費者 (update_downloaded_albums) 正常退出
            self.queue.put(None)

            # 關閉並等待所有子行程結束
            pool.close()
            pool.join()

    def stop(self):
        """
        供 GUI 中使用者點擊「停止下載」時呼叫。
        設定 be_stopped = True，並送一個 None 進 queue 讓消費者提早結束。
        之後在 wait_for_finish() 裏面會檢查子行程是否有結束。
        """
        print("Stop called. Set be_stopped = True.")
        self.be_stopped = True
        self.queue.put(None)  # 讓消費者退出


if __name__ == "__main__":
    # 建議加上 freeze_support() 以防在 Windows spawn 模式出現問題
    multiprocessing.freeze_support()
    queue = Manager().Queue()
    downloader = MonsterSirenDownloader(task=queue)
    downloader.run()
