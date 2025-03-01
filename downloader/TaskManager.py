from .my_logger import get_mp_child_logger
import os
import multiprocessing
from multiprocessing import Pool


class TaskManager:
    def __init__(self, log_queue=None, max_workers=None):
        self.max_workers = max_workers or os.cpu_count()
        self.stop_event = multiprocessing.Manager().Event()
        self.mutex = multiprocessing.Manager().Lock()
        self.pool = None

        # 初始化 logger
        self.logger = get_mp_child_logger(log_queue=log_queue, name=__name__)
        self.logger.info(f"TaskManager 初始化完成，最大執行緒數: {self.max_workers}")

    def start(self, tasks, worker_function):
        self.logger.info("啟動執行緒池，分配任務...")
        self.pool = Pool(self.max_workers)
        try:
            results = self.pool.map(worker_function, tasks)
            self.logger.info(
                f"所有任務執行完成。成功數量: {sum(results)}, 失敗數量: {len(results) - sum(results)}"
            )
            return results
        except Exception as e:
            self.logger.exception(f"執行任務時發生錯誤: {e}")
            return []
        finally:
            self.close_pool()

    def stop(self):
        self.logger.warning("收到停止指令，正在停止所有執行序...")
        self.stop_event.set()
        if self.pool:
            # self.pool.terminate()
            self.pool.close()
            self.pool.join()
            self.logger.warning("所有執行緒已停止。")
        else:
            self.logger.warning("執行緒池尚未啟動。")

    def close_pool(self):
        if self.pool:
            self.logger.info("正在關閉執行緒池...")
            self.pool.close()
            self.pool.join()
            self.logger.info("執行緒池已關閉。")
