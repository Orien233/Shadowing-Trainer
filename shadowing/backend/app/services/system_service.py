import multiprocessing
import os
import signal
import threading
import time


def schedule_backend_shutdown(delay_seconds: float = 1.0) -> None:
    def shutdown() -> None:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        parent_process = multiprocessing.parent_process()
        if parent_process and parent_process.pid and parent_process.pid != os.getpid():
            try:
                os.kill(parent_process.pid, signal.SIGTERM)
            except OSError:
                pass
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except OSError:
            pass
        os._exit(0)

    thread = threading.Thread(target=shutdown, name="backend-shutdown", daemon=True)
    thread.start()
