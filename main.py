from downloader.MonsterSirenDownloader import MonsterSirenDownloader

if __name__ == "__main__":
    # 初始化 MonsterSirenDownloader
    downloader = MonsterSirenDownloader(max_workers=4)

    try:
        print("開始執行下載...")
        downloader.run()
    except KeyboardInterrupt:
        print("檢測到中斷信號，正在停止下載...")
        downloader.stop()
    finally:
        print("下載結束。")
