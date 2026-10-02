"""Tiny job functions used by the job-runner tests (importable in a child process)."""

from __future__ import annotations

import time

from pdf_editor.core.errors import InvalidInput, OperationCancelled


def count_to(n: int, progress) -> int:
    for i in range(n):
        if progress(i, n, f"step {i}") is False:
            raise OperationCancelled()
    return n


def fail_invalid(progress) -> None:
    raise InvalidInput("bad input from job")


def crash(progress) -> None:
    raise RuntimeError("unexpected")


def slow(seconds: float, progress) -> None:
    end = time.time() + seconds
    while time.time() < end:
        if progress(0, 1, "waiting") is False:
            raise OperationCancelled()
        time.sleep(0.05)
