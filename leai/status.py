"""Background status ticker for Rich console status during long-running tasks."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rich.status import Status


def fmt_duration(secs: float) -> str:
    """Format seconds into MM:SS string."""
    m = int(secs) // 60
    s = int(secs) % 60
    return f"{m:02d}:{s:02d}"


class LiveStatusTicker:
    """Periodically refreshes a Rich Status with real-time elapsed time.

    Prevents UI timer freeze during long blocking operations like database queries.
    """

    def __init__(
        self,
        status: Status | Any,
        prefix: str,
        t0: float | None = None,
        initial_msg: str = "",
        interval: float = 0.5,
    ) -> None:
        self.status = status
        self.prefix = prefix
        self.t0 = t0 if t0 is not None else time.perf_counter()
        self.msg = initial_msg
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def update(self, msg: str | None = None, prefix: str | None = None) -> None:
        """Update message and/or prefix and refresh status immediately."""
        with self._lock:
            if msg is not None:
                self.msg = msg
            if prefix is not None:
                self.prefix = prefix
        self._render()

    def _render(self) -> None:
        if self.status is None:
            return
        with self._lock:
            elapsed_str = fmt_duration(time.perf_counter() - self.t0)
            text = f"[cyan]{self.prefix} [{elapsed_str}] {self.msg}[/cyan]"
        try:
            self.status.update(text)
        except Exception:
            pass

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval):
            self._render()

    def start(self) -> LiveStatusTicker:
        self._render()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def __enter__(self) -> LiveStatusTicker:
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
