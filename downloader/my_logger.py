# my_logger.py
import logging
import sys
import multiprocessing
from logging.handlers import QueueHandler, QueueListener


def get_mp_main_logger(
    log_queue=None, name="MainLogger", level=logging.INFO, to_console=True, to_file=None
):
    """
    讓「主程式」呼叫，建立/啟動 QueueListener 並回傳:
      (main_logger, queue_listener, final_queue)

    參數：
      - log_queue: 若已有 multiprocessing.Manager.Queue，直接傳進來；
                   若為 None，函式內會自動建立一個新的 Queue。
      - name      : 主程式 logger 名稱 (預設 "MainLogger")
      - level     : 日誌等級 (INFO, DEBUG, 等)
      - to_console: 是否輸出到終端 (True/False)
      - to_file   : 若指定路徑字串，則輸出到該檔案

    回傳：
      - main_logger      : 主程式可直接 logger.info(...) 的物件
      - queue_listener   : QueueListener (在程式結束前可自行 .stop())
      - final_queue      : 真正使用的 Queue (給子行程共用)
    """

    # 1. 若沒有給 log_queue，就在這裡建立
    if log_queue is None:
        log_queue = multiprocessing.Manager().Queue(-1)

    # 2. 準備最終輸出的 handler 列表 (可同時多個)
    handlers = []
    if to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        handlers.append(console_handler)

    if to_file is not None:
        file_handler = logging.FileHandler(to_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    # 3. 建立 QueueListener，統一負責從 queue 讀 log，再交給 handlers
    queue_listener = QueueListener(log_queue, *handlers, respect_handler_level=True)
    queue_listener.start()

    # 4. 建立主程式 logger，把自己的 log 也丟到同一個 queue
    main_logger = logging.getLogger(name)
    main_logger.setLevel(level)
    # 先清空可能的舊 handler，避免重複
    main_logger.handlers.clear()

    qhandler = QueueHandler(log_queue)
    main_logger.addHandler(qhandler)

    return main_logger, queue_listener, log_queue


def get_mp_child_logger(log_queue, name="ChildLogger", level=logging.INFO):
    """
    讓「子行程」呼叫，從指定的 log_queue 建立一個 logger，
    再透過 QueueHandler 把日誌丟回 main process 的 QueueListener。

    回傳：子行程 logger
    """
    child_logger = logging.getLogger(name)
    child_logger.setLevel(level)
    # 避免重複
    child_logger.handlers.clear()

    qhandler = QueueHandler(log_queue)
    child_logger.addHandler(qhandler)
    return child_logger
