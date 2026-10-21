"""Shared utilities: logging, safe arithmetic, platform open, retry backoff."""

from __future__ import annotations

import ast
import functools
import logging
import operator
import os
import random
import re
import subprocess
import sys
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, TypeVar

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_PATH = _PROJECT_ROOT / "jarvis.log"
_LOGGER: logging.Logger | None = None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str = "jarvis", debug: bool = False) -> logging.Logger:
    """Return a rotating-file + console logger configured once per process."""
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

        file_handler = RotatingFileHandler(
            _LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

    _LOGGER = logger
    return logger


# ---------------------------------------------------------------------------
# Safe arithmetic (used by the `calculate` tool - never bare eval)
# ---------------------------------------------------------------------------

_ALLOWED_BINOPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS: dict[type, Any] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_ALLOWED_FUNCS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": lambda x: x ** 0.5,
}


def _safe_node(node: ast.expr) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left, right = _safe_node(node.left), _safe_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _ALLOWED_BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_safe_node(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fname = node.func.id
        if fname not in _ALLOWED_FUNCS:
            raise ValueError(f"function {fname!r} not allowed")
        args = [_safe_node(a) for a in node.args]
        return _ALLOWED_FUNCS[fname](*args)
    raise ValueError(f"unsupported expression element: {ast.dump(node)[:80]}")


def safe_eval(expression: str) -> Any:
    """Evaluate a numeric expression using a whitelisted AST walker."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid expression: {expression!r}") from exc
    return _safe_node(tree.body)


# ---------------------------------------------------------------------------
# Platform open
# ---------------------------------------------------------------------------

def platform_open(target: str) -> str:
    """Open a file, folder, or URL with the OS default handler."""
    try:
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
            return f"opened {target!r}"
        elif sys.platform == "darwin":
            subprocess.run(["open", target], timeout=10, check=True)
            return f"opened {target!r}"
        else:
            subprocess.run(["xdg-open", target], timeout=10, check=True)
            return f"opened {target!r}"
    except (OSError, subprocess.SubprocessError):
        webbrowser.open(target)
        return f"opened {target!r} in browser"


# ---------------------------------------------------------------------------
# Exponential backoff with jitter (for 429 / 5xx)
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])


def _retryable(exc: BaseException) -> bool:
    """Return True for HTTP 429 or 5xx errors."""
    status: int | None = None
    if hasattr(exc, "status_code"):
        status = getattr(exc, "status_code", None)
    elif hasattr(exc, "response") and exc.response is not None:
        status = getattr(exc.response, "status_code", None)
    if status is None:
        return False
    return status == 429 or 500 <= status < 600


def backoff(func: F | None = None, *, attempts: int = 4, base_delay: float = 1.0) -> Callable:
    """Decorator: retry on 429/5xx with exponential backoff + jitter, max 4 tries."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - deliberate catch for retry
                    if not _retryable(exc) or attempt == attempts:
                        raise
                    last_exc = exc
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    logging.getLogger("jarvis.backoff").warning(
                        "retryable error (attempt %d/%d): %s - sleeping %.1fs",
                        attempt, attempts, exc, delay,
                    )
                    time.sleep(delay)
            raise last_exc  # pragma: no cover

        return wrapper  # type: ignore[return-value]

    if func is not None:
        return decorator(func)
    return decorator


def http_status(exc: BaseException) -> int | None:
    """Best-effort HTTP status extraction from SDK / requests exceptions."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    return None


# ---------------------------------------------------------------------------
# Live sentence streaming
# ---------------------------------------------------------------------------

class SentenceEmitter:
    """Accumulates streamed tokens and fires on_sentence per complete sentence."""

    _SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

    def __init__(self, on_sentence: Callable[[str], None]) -> None:
        self._on_sentence = on_sentence
        self._buffer = ""

    def feed(self, token: str) -> None:
        self._buffer += token
        parts = self._SENTENCE_SPLIT.split(self._buffer)
        if len(parts) > 1:
            for complete in parts[:-1]:
                if complete.strip():
                    self._on_sentence(complete.strip())
            self._buffer = parts[-1]

    def flush(self) -> str:
        remainder = self._buffer.strip()
        if remainder:
            self._on_sentence(remainder)
        self._buffer = ""
        return remainder
