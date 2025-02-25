# myLogger.py
import logging
import sys


def get_logger(name: str = __name__, default_output: bool = True) -> logging.Logger:
    """
    取得指定名稱的 logger。
    - 若 logger 尚未配置任何 handler，且 default_output=False，則自動加入 NullHandler (不輸出)。
    - 若 logger 尚未配置任何 handler，且 default_output=True，則自動加入一個 StreamHandler 輸出至 console。
    """
    logger = logging.getLogger(name)

    if not logger.hasHandlers():
        if default_output:
            # 預設輸出到 console
            logger.setLevel(logging.INFO)
            ch = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            ch.setFormatter(formatter)
            logger.addHandler(ch)
        else:
            # 預設不輸出
            logger.addHandler(logging.NullHandler())

    return logger
