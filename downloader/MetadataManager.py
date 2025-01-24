import logging
import pylrc
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, SYLT, Encoding
from mutagen.flac import FLAC, Picture
from PIL import Image


class MetadataManager:
    @staticmethod
    def fill_metadata(
        file_path, file_type, metadata, cover_path=None, lyrics_path=None
    ):
        """
        填寫音樂文件的元數據。
        :param file_path: 音樂文件的完整路徑。
        :param file_type: 文件類型，支持 ".mp3" 和 ".flac"。
        :param metadata: 包含元數據的字典（如專輯、標題、歌手等）。
        :param cover_path: 專輯封面圖片的路徑（選填）。
        :param lyrics_path: 歌詞文件的路徑（選填）。
        """
        try:
            if file_type == ".mp3":
                MetadataManager._fill_mp3_metadata(
                    file_path, metadata, cover_path, lyrics_path
                )
            elif file_type == ".flac":
                MetadataManager._fill_flac_metadata(
                    file_path, metadata, cover_path, lyrics_path
                )
            else:
                raise ValueError(f"不支持的文件類型: {file_type}")

            logging.info(f"成功填寫元數據: {file_path}")
        except Exception as e:
            logging.exception(f"填寫元數據時發生錯誤: {file_path} - {e}")
            raise

    @staticmethod
    def _lyric_file_to_text(self, filename):
        with open(filename, "r", encoding="utf-8") as lrc_file:
            lrc_string = lrc_file.read()
        subs = pylrc.parse(lrc_string)
        ret = []
        for sub in subs:
            time_ms = int(sub.time * 1000)
            text = sub.text
            ret.append((text, time_ms))
        return ret

    @staticmethod
    def _fill_mp3_metadata(file_path, metadata, cover_path, lyrics_path):
        mp3_file = EasyID3(file_path)
        mp3_file["album"] = metadata.get("album", "")
        mp3_file["title"] = metadata.get("title", "")
        mp3_file["artist"] = metadata.get("artist", "")
        mp3_file["albumartist"] = metadata.get("albumartist", "")
        mp3_file["tracknumber"] = str(metadata.get("tracknumber", 1))
        mp3_file.save()

        id3_file = ID3(file_path)
        if cover_path:
            with open(cover_path, "rb") as cover_file:
                id3_file.add(
                    APIC(
                        mime="image/png",
                        type=3,
                        desc="Cover",
                        data=cover_file.read(),
                    )
                )
        if lyrics_path:
            with open(lyrics_path, "r", encoding="utf-8") as lyrics_file:
                lyrics = MetadataManager._lyric_file_to_text(lyrics_file)
                id3_file.setall(
                    "SYLT",
                    [
                        SYLT(
                            encoding=Encoding.UTF8,
                            lang="eng",
                            format=2,
                            type=1,
                            text=lyrics,
                        )
                    ],
                )
        id3_file.save()

    @staticmethod
    def _fill_flac_metadata(file_path, metadata, cover_path, lyrics_path):
        flac_file = FLAC(file_path)
        flac_file["album"] = metadata.get("album", "")
        flac_file["title"] = metadata.get("title", "")
        flac_file["artist"] = metadata.get("artist", "")
        flac_file["albumartist"] = metadata.get("albumartist", "")
        flac_file["tracknumber"] = str(metadata.get("tracknumber", 1))

        if cover_path:
            image = Picture()
            with open(cover_path, "rb") as cover_file:
                image.data = cover_file.read()
            with Image.open(cover_path) as img:
                image.width, image.height = img.size
                image.type = 3
                image.mime = "image/png"
                image.depth = 24
            flac_file.add_picture(image)

        if lyrics_path:
            with open(lyrics_path, "r", encoding="utf-8") as lyrics_file:
                flac_file["lyrics"] = lyrics_file.read()

        flac_file.save()
