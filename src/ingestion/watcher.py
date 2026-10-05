from __future__ import annotations

import threading
import time
from pathlib import Path

from ..config import PRIVATE_DIR, PUBLIC_DIR
from .loader import is_supported

class _IngestHandler:
    def __init__(self, process_file, delay: float = 1.0, retries: int = 5):
        self._process = process_file
        self._delay = delay
        self._retries = retries

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if not is_supported(path):
            return
        threading.Thread(target=self._safe_process, args=(path,), daemon=True).start()

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
    processed = []
    for base in (PRIVATE_DIR, PUBLIC_DIR):
        for path in sorted(base.rglob("*")):
            if path.is_file() and is_supported(path):
                try:
                    process_file(path)
                    processed.append(str(path))
                except Exception:
                    continue
    return processed
