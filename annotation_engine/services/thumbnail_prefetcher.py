"""
AnnotationEngine Desktop - Thumbnail Prefetcher

Fetches remote (SSH) images in the background so the grid never performs
network I/O inside ``paintEvent``. One worker thread owns its own SFTP
connection (paramiko's ``SFTPClient`` is not thread-safe, so it must not share
the main-thread client).

Requests are de-duplicated and processed in arrival order. Because they
originate from painting, visible tiles are enqueued first; the remainder of the
project follows, so scrolling stays smooth while everything eventually caches.
"""
import queue
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, QThread, Signal

from annotation_engine.services.ssh_client import SSHClient

# How long a blocking caller (opening an image) waits for its fetch.
BLOCKING_TIMEOUT = 60.0


class _PrefetchWorker(QObject):
    """Worker living on the prefetch thread."""

    ready = Signal(int, str, int, int)   # image_id, local_path, width, height
    failed = Signal(int, str)            # image_id, error

    def __init__(self, client_factory: Callable[[], Optional[SSHClient]]):
        super().__init__()
        self._client_factory = client_factory
        self._client: Optional[SSHClient] = None
        self._queue: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()
        self._pending: Dict[int, tuple] = {}
        self._pending_lock = threading.Lock()
        self._waiters: Dict[int, threading.Event] = {}

    # -- main-thread API (thread-safe) ---------------------------------
    def enqueue(self, image_id: int, remote_path: str, local_path: str):
        with self._pending_lock:
            if image_id in self._pending:
                return False
            self._pending[image_id] = (remote_path, local_path)
        self._queue.put((image_id, remote_path, local_path))
        return True

    def wait_for(self, image_id: int, timeout: float = BLOCKING_TIMEOUT) -> bool:
        """Block until ``image_id`` has been fetched (or failed)."""
        with self._pending_lock:
            if image_id not in self._pending:
                return True  # already done or never queued
            event = self._waiters.setdefault(image_id, threading.Event())
        return event.wait(timeout)

    def stop(self):
        self._stop.set()
        self._queue.put(None)

    # -- worker-thread loop --------------------------------------------
    def run(self):
        while not self._stop.is_set():
            item = self._queue.get()
            if item is None:
                break
            image_id, remote_path, local_path = item
            try:
                width, height = self._fetch(remote_path, local_path)
                self.ready.emit(image_id, local_path, width, height)
            except Exception as exc:
                self.failed.emit(image_id, str(exc))
            finally:
                with self._pending_lock:
                    self._pending.pop(image_id, None)
                    waiter = self._waiters.pop(image_id, None)
                if waiter is not None:
                    waiter.set()
        self._close_client()

    def _fetch(self, remote_path: str, local_path: str):
        if self._client is None:
            self._client = self._client_factory()
            if self._client is None:
                raise RuntimeError("No SSH connection available")
        if not self._client.fetch(remote_path, local_path):
            # A stale connection is the usual cause; reconnect once.
            self._close_client()
            self._client = self._client_factory()
            if self._client is None or not self._client.fetch(remote_path, local_path):
                raise RuntimeError(f"Could not fetch {remote_path}")
        return _image_size(local_path)

    def _close_client(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


def _image_size(local_path: str):
    """Return ``(width, height)`` for a downloaded image, or ``(0, 0)``."""
    try:
        from PIL import Image

        with Image.open(local_path) as img:
            return img.width, img.height
    except Exception:
        return 0, 0


class ThumbnailPrefetcher(QObject):
    """Owns the prefetch thread and exposes a simple enqueue/wait API."""

    ready = Signal(int, str, int, int)
    failed = Signal(int, str)

    def __init__(self, client_factory, parent=None):
        super().__init__(parent)
        self._thread = QThread()
        self._worker = _PrefetchWorker(client_factory)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.ready.connect(self.ready)
        self._worker.failed.connect(self.failed)
        self._thread.start()

    def enqueue(self, image_id: int, remote_path: str, local_path: str) -> bool:
        return self._worker.enqueue(image_id, remote_path, local_path)

    def wait_for(self, image_id: int, timeout: float = BLOCKING_TIMEOUT) -> bool:
        return self._worker.wait_for(image_id, timeout)

    def stop(self):
        if self._thread is None:
            return
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(5000)
        self._thread = None
