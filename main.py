import os
import shutil
from pathlib import Path
import requests
import time
from tqdm import tqdm
import pylrc
import json

from PIL import Image
import multiprocessing
from multiprocessing import Pool, Manager
from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, SYLT, Encoding, ID3
from mutagen.flac import Picture, FLAC
from pydub import AudioSegment


def make_valid(filename):
    # Make a filename valid in different OSs
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


def lyric_file_to_text(filename):
    with open(filename, "r", encoding="utf-8") as lrc_file:
        lrc_string = lrc_file.read()
    subs = pylrc.parse(lrc_string)
    ret = []
    for sub in subs:
        time = int(sub.time * 1000)
        text = sub.text
        ret.append((text, time))
    return ret


def update_downloaded_albums(queue, directory, mutex):
    while 1:
        album_name = queue.get()
        # Final queue element, guaranteed to happen after all maps completed
        if album_name == None:
            break
        try:
            with mutex:
                with open(
                    directory / "completed_albums.json", "r", encoding="utf8"
                ) as f:
                    completed_albums = json.load(f)
        except:
            completed_albums = []
        completed_albums.append(album_name)
        with mutex:
            with open(directory / "completed_albums.json", "w+", encoding="utf8") as f:
                json.dump(completed_albums, f)


def fill_metadata(
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
        if songlyricpath != None:
            sylt = lyric_file_to_text(songlyricpath)
            file.setall(
                "SYLT",
                [SYLT(encoding=Encoding.UTF8, lang="eng", format=2, type=1, text=sylt)],
            )
        file.save()
    else:
        image = Picture()
        image.type = 3
        image.desc = "Cover"
        image.mime = "image/png"
        with open(albumcover, "rb") as f:
            image.data = f.read()
        with Image.open(albumcover) as imagePil:
            image.width, image.height = imagePil.size
            image.depth = 24
        file.add_picture(image)
        # Read and add lyrics
        if songlyricpath != None:
            musiclrc = open(songlyricpath, "r", encoding="utf-8").read()
            file["lyrics"] = musiclrc
        file.save()

    return


def download_song(session, directory, name, url):
    source = session.get(url, stream=True)
    filename = Path(directory) / make_valid(name)
    filetype = ""

    if source.headers["content-type"] == "audio/mpeg":
        filename = filename.with_suffix(".mp3")
        filetype = ".mp3"
    else:
        filename = filename.with_suffix(".wav")
        filetype = ".wav"

    # Download song
    total = int(source.headers.get("content-length", 0))
    with open(filename, "w+b") as f, tqdm(
        desc=name,
        total=total,
        unit="iB",
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in source.iter_content(chunk_size=1024):
            size = f.write(data)
            bar.update(size)

    # If file is .wav then export to .flac
    if filetype == ".wav":
        try:
            AudioSegment.from_wav(str(filename)).export(
                str(Path(directory) / f"{make_valid(name)}.flac"), format="flac"
            )
        except Exception as e:
            print(f"Error converting {name} to flac: {e}")
            return None, None

        os.remove(filename)
        filename = Path(directory) / f"{make_valid(name)}.flac"
        filetype = ".flac"

    return filename, filetype


def download_album(args):
    directory = args["directory"]
    session = args["session"]
    queue = args["queue"]

    album_cid = args["cid"]
    album_name = args["name"]
    album_coverUrl = args["coverUrl"]
    album_artistes = args["artistes"]
    album_url = f"https://monster-siren.hypergryph.com/api/album/{album_cid}/detail"

    album_directory = directory / make_valid(album_name)
    album_directory.mkdir(parents=True, exist_ok=True)  # 先確保目錄存在

    # Download album art
    with open(album_directory / "cover.jpg", "w+b") as f:
        f.write(session.get(album_coverUrl).content)

    # Change album art from .jpg to .png
    cover = Image.open(album_directory / "cover.jpg")
    cover.save(album_directory / "cover.png")
    os.remove(album_directory / "cover.jpg")

    songs = session.get(album_url, headers={"Accept": "application/json"}).json()[
        "data"
    ]["songs"]
    for song_track_number, song in enumerate(songs):
        # Get song details
        song_cid = song["cid"]
        song_name = song["name"]
        song_artists = song["artistes"]
        song_url = f"https://monster-siren.hypergryph.com/api/song/{song_cid}"
        song_detail = session.get(
            song_url, headers={"Accept": "application/json"}
        ).json()["data"]
        song_lyricUrl = song_detail["lyricUrl"]
        song_sourceUrl = song_detail["sourceUrl"]

        # Download lyric
        if song_lyricUrl != None:
            songlyricpath = album_directory / f"{make_valid(song_name)}.lrc"
            with open(songlyricpath, "w+b") as f:
                f.write(session.get(song_lyricUrl).content)
        else:
            songlyricpath = None

        # Download song and fill out metadata in case of failure retry 5 times
        max_retries = 5
        downloaded = False
        for attempt in range(max_retries):
            try:
                filename, filetype = download_song(
                    session=session,
                    directory=album_directory,
                    name=song_name,
                    url=song_sourceUrl,
                )

                if filename is None or filetype is None:
                    raise ValueError(f"Failed to download/convert song {song_name}")

                fill_metadata(
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

    # Mark album as downloaded
    queue.put(album_name)
    return


def get_unfinished_albums(directory, albums):
    if not (directory / "completed_albums.json").exists():
        with open(directory / "completed_albums.json", "w+", encoding="utf8") as f:
            json.dump([], f)
        print("Adding all albums to download queue")
        return albums

    completed_albums = []
    with open(directory / "completed_albums.json", "r", encoding="utf8") as f:
        completed_albums = json.load(f)

    unfinished_albums = []
    for album in albums:
        if album["name"] not in completed_albums:
            unfinished_albums.append(album)
            print(f"Adding {album['name']} to download queue")

    return unfinished_albums


def main():
    directory = Path("./MonsterSiren/")
    session = requests.Session()
    manager = Manager()
    queue = manager.Queue()
    mutex = manager.Lock()

    directory.mkdir(parents=True, exist_ok=True)

    # Get all albums
    albums = session.get(
        "https://monster-siren.hypergryph.com/api/albums",
        headers={"Accept": "application/json"},
    ).json()["data"]

    unfinished_albums = get_unfinished_albums(directory, albums)
    if len(unfinished_albums) == 0:
        print("All albums have already been downloaded")
        return

    for album in unfinished_albums:
        album["directory"] = directory
        album["session"] = session
        album["queue"] = queue
        album["mutex"] = mutex

    with Pool(maxtasksperchild=1) as pool:
        pool.apply_async(update_downloaded_albums, (queue, directory, mutex))
        pool.map(download_album, unfinished_albums)
        queue.put(None)
        pool.close()
        pool.join()

    print("All albums are downloaded")
    return


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
