import os
import sys
import json
from PIL import Image
import requests
from tqdm import tqdm
from .my_logger import get_logger
from .MetadataManager import MetadataManager
from pydub import AudioSegment


class DownloadWorker:
    def __init__(self, directory, stop_event, mutex, log_queue=None):
        self.directory = directory
        self.stop_event = stop_event
        self.mutex = mutex
        self.logger = get_logger()

    def download_album(self, album_data):
        try:
            album_name = self.make_valid(album_data["name"])
            album_cid = album_data["cid"]
            album_url = (
                f"https://monster-siren.hypergryph.com/api/album/{album_cid}/detail"
            )

            album_directory = self.directory / album_name
            album_directory.mkdir(parents=True, exist_ok=True)
            session = requests.Session()

            self.logger.info(f"開始下載專輯: {album_name}")

            self.download_cover(session, album_directory, album_data["coverUrl"])

            # 取得專輯內歌曲清單
            songs_data = session.get(
                album_url, headers={"Accept": "application/json"}
            ).json()["data"]["songs"]
            for song_track_number, song_data in enumerate(songs_data):
                if self.stop_event.is_set():
                    self.logger.warning(f"檢測到停止指令，停止下載專輯: {album_name}")
                    return False
                song_data["tracknumber"] = song_track_number + 1
                self.download_song(session, album_directory, song_data, album_data)

            # 更新 completed_albums.json
            with self.mutex:
                try:
                    with open(
                        self.directory / "completed_albums.json", "r", encoding="utf8"
                    ) as f:
                        completed_albums = json.load(f)
                except:
                    completed_albums = []

                completed_albums.append(album_data["name"])
                with open(
                    self.directory / "completed_albums.json", "w+", encoding="utf8"
                ) as f:
                    json.dump(completed_albums, f)

            self.logger.info(f"專輯 {album_data['name']} 下載完成。")
            return True

        except Exception as e:
            self.logger.exception(f"專輯 {album_data['name']} 下載失敗: {e}")
            return False

    def download_cover(self, session, album_directory, cover_url):
        try:
            cover_path = album_directory / "cover.jpg"
            with open(cover_path, "wb") as f:
                f.write(session.get(cover_url).content)

            with Image.open(cover_path) as img:
                img.save(album_directory / "cover.png")
            os.remove(cover_path)

            self.logger.info(f"專輯封面下載完成: {cover_url}")
        except Exception as e:
            self.logger.exception(f"下載專輯封面失敗: {cover_url} - {e}")
            raise

    def download_song(self, session, album_directory, song_data, album_data):
        try:
            song_cid = song_data["cid"]
            song_name = self.make_valid(song_data["name"])
            song_url = (
                f"https://monster-siren.hypergryph.com/api/song/{song_cid}"
            )
            song_detail = session.get(
                song_url, headers={"Accept": "application/json"}
            ).json()["data"]
            song_sourceUrl = song_detail["sourceUrl"]
            song_lyricUrl = song_detail["lyricUrl"]

            # Download song
            song_file = self.download_file(
                session, album_directory, song_name, song_sourceUrl
            )
            self.logger.info(f"歌曲下載完成: {song_name} - {song_sourceUrl}")

            # Download lyric
            if song_lyricUrl:
                lyric_path = album_directory / f"{song_name}.lrc"
                with open(lyric_path, "wb") as f:
                    f.write(session.get(song_lyricUrl).content)
                self.logger.info(f"歌詞下載完成: {song_name} - {song_lyricUrl}")

            MetadataManager.fill_metadata(
                file_path=song_file,
                file_type=song_file.suffix,
                metadata={
                    "album": self.make_valid(album_data["name"]),
                    "title": song_name,
                    "artist": song_data["artistes"],
                    "albumartist": album_data["artistes"],
                    "tracknumber": song_data["tracknumber"],
                },
                cover_path=album_directory / "cover.png",
                lyrics_path=lyric_path if song_lyricUrl else None,
            )

        except Exception as e:
            self.logger.exception(f"下載歌曲失敗: {song_data['name']} - {e}")
            raise

    def download_file(self, session, directory, filename, url):
        try:
            file_path = directory / f"{filename}.tmp"
            response = session.get(url, stream=True)
            total_size = int(response.headers.get("content-length", 0))

            # 檢查是否有標準輸出，如果沒有則不使用 tqdm
            use_tqdm = sys.stdout is not None and sys.stdout.isatty()

            with open(file_path, "wb") as f:
                bar = (
                    tqdm(
                        desc=filename,
                        total=total_size,
                        unit="iB",
                        unit_scale=True,
                        unit_divisor=1024,
                    )
                    if use_tqdm
                    else None
                )

                for data in response.iter_content(chunk_size=1024):
                    if self.stop_event.is_set():
                        raise InterruptedError(f"下載被中斷: {filename}")
                    size = f.write(data)
                    if bar:
                        bar.update(size)

                if bar:
                    bar.close()

            return self._check_file_suffix(file_path, response)

        except InterruptedError:
            if bar:
                bar.close()
            self.logger.warning(f"檢測到停止指令，停止下載文件: {filename}")
            raise

        except Exception as e:
            if bar:
                bar.close()
            self.logger.exception(f"下載文件失敗: {url} - {e}")
            raise

    def _check_file_suffix(self, file_path, response):
        final_path = file_path
        content_type = response.headers.get("content-type", "")
        if content_type == "audio/mpeg":
            final_path = file_path.with_suffix(".mp3")
            file_path.rename(final_path)
        else:
            # 其餘是 wav 文件，需轉換為 flac
            try:
                final_path = file_path.with_suffix(".flac")
                wav_file = AudioSegment.from_wav(str(file_path))
                wav_file.export(str(final_path), format="flac")
                os.remove(file_path)
            except Exception as e:
                self.logger.exception(f"轉換 wav 文件失敗: {file_path} - {e}")
                raise
        return final_path

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
