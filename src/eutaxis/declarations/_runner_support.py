"""Shared invariants for reviewed in-process runner boundaries."""

from __future__ import annotations

import inspect
from typing import Callable


def validate_synchronous_runner(
    runner: object,
    make_error: Callable[[str], Exception],
) -> None:
    """Require a synchronous callable invocable with one positional payload."""
    if not callable(runner):
        raise make_error("runner must be an in-process callable")
    call_method = getattr(runner, "__call__", None)
    if (
        inspect.iscoroutinefunction(runner)
        or inspect.iscoroutinefunction(call_method)
        or inspect.isasyncgenfunction(runner)
        or inspect.isasyncgenfunction(call_method)
    ):
        raise make_error("runner must be synchronous")
    try:
        inspect.signature(runner).bind(object())
    except (TypeError, ValueError) as exc:
        raise make_error(
            "runner must accept one positional input payload without other required arguments"
        ) from exc


def exception_detail(error: Exception) -> str:
    """Describe an exception without trusting its string conversion."""
    try:
        message = str(error)
    except Exception as formatting_error:
        return (
            f"{type(error).__name__}; message formatting raised "
            f"{type(formatting_error).__name__}"
        )
    return f"{type(error).__name__}: {message}"
