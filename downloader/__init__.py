# # 不輸出任何日誌
# import logging

# logger = logging.getLogger(__name__)
# logger.addHandler(logging.NullHandler())
import subprocess


class NoWindowPopen(subprocess.Popen):
    def __init__(self, *args, **kwargs):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags = (
            subprocess.CREATE_NEW_CONSOLE | subprocess.STARTF_USESHOWWINDOW
        )
        startupinfo.wShowWindow = subprocess.SW_HIDE

        kwargs["startupinfo"] = startupinfo
        super().__init__(*args, **kwargs)


subprocess.Popen = NoWindowPopen
