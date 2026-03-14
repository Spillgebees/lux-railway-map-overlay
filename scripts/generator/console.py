from __future__ import annotations

import sys
import time
from dataclasses import dataclass


def format_elapsed(start_time: float) -> str:
    elapsed = int(time.time() - start_time)
    minutes, seconds = divmod(elapsed, 60)
    return f"{minutes}m {seconds}s"


def format_bytes(size_in_bytes: int) -> str:
    size = float(size_in_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024.0
    return f"{size_in_bytes}B"


@dataclass
class Console:
    use_color: bool

    @classmethod
    def create(cls) -> "Console":
        return cls(use_color=sys.stdout.isatty())

    def _style(self, code: str, text: str) -> str:
        if not self.use_color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def info(self, message: str) -> None:
        print(f"{self._style('0;32', '[INFO]')}  {message}")

    def warn(self, message: str) -> None:
        print(f"{self._style('1;33', '[WARN]')}  {message}")

    def error(self, message: str) -> None:
        print(f"{self._style('0;31', '[ERROR]')} {message}", file=sys.stderr)

    def step(self, message: str) -> None:
        bold_blue = (
            self._style("1;34", f"==> {message}")
            if self.use_color
            else f"==> {message}"
        )
        print(f"\n{bold_blue}")
