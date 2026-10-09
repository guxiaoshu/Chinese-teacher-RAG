from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from ..config import PRIVATE_DIR, PUBLIC_DIR
from .loader import is_supported
from watchdog.events import FileSystemEventHandler

class _IngestHandler(FileSystemEventHandler):
    def __init__(self, process_file, delay: float = 1.0, retries: int = 5):
        super().__init__()
        self._process = process_file
        self._delay = delay
        self._retries = retries
        self._queue: queue.Queue = queue.Queue()
        # 单线程串行处理：并发调用 embedding / ChromaDB 会触发 Rust 侧「Already borrowed」等竞态
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _enqueue(self, path: Path):
        if not is_supported(path):
            return
        self._queue.put(path)

    def on_created(self, event):
        if event.is_directory:
            return
        self._enqueue(Path(event.src_path))

    def on_moved(self, event):
        # 文件「剪切/移动」进目录时触发的是 moved 而非 created，这里补上目标路径
        if event.is_directory:
            return
        self._enqueue(Path(event.dest_path))

    def _run(self):
        while True:
            path = self._queue.get()
            try:
                self._safe_process(path)
            except Exception:
                pass
            finally:
                self._queue.task_done()

    def _safe_process(self, path: Path):
        for attempt in range(self._retries):
            try:
                if path.exists() and path.stat().st_size > 0:
                    self._process(path)
                    return
            except Exception:
                pass
            time.sleep(self._delay)
        try:
            self._process(path)
        except Exception:
            pass

class IngestWatcher:
    def __init__(self, process_file):
        self._process = process_file
        self._observer = None

    def start(self):
        if self._observer is not None:
            return
        from watchdog.observers import Observer

        handler = _IngestHandler(self._process)
        self._observer = Observer()
        self._observer.schedule(handler, str(PRIVATE_DIR), recursive=True)
        self._observer.schedule(handler, str(PUBLIC_DIR), recursive=True)
        self._observer.start()

    def stop(self):
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

def scan_existing(process_file) -> list[str]:
    """批量补扫 ingest 下的存量文件：单个文件跳过建索引，扫完按库统一重建一次。

    逐个文件重建 BM25 索引是 O(n²) 的重活，文件多时扫库极慢；改为只对「确实有新入库」的库重建一次。
    """
    from ..retrieval.retriever import rebuild_index

    processed = []
    touched = set()
    for base in (PRIVATE_DIR, PUBLIC_DIR):
        library = "private" if base == PRIVATE_DIR else "public"
        for path in sorted(base.rglob("*")):
            if path.is_file() and is_supported(path):
                try:
                    r = process_file(path, rebuild=False)
                except Exception:
                    continue
                processed.append(str(path))
                if isinstance(r, dict) and r.get("status") == "processed":
                    touched.add(library)
    for library in touched:
        rebuild_index(library)
    return processed
