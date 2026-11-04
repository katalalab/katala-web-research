from __future__ import annotations

import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol, TypeVar


class Closable(Protocol):
    def close(self) -> None: ...


T = TypeVar("T", bound=Closable)


def close_after_error(resource: Closable, primary: BaseException) -> None:
    """Close after a failed operation without hiding either failure."""
    try:
        resource.close()
    except BaseException as close_error:
        detail = "".join(traceback.format_exception(close_error, chain=False)).rstrip()
        primary.add_note(f"Resource close also failed:\n{detail}")


@contextmanager
def closing_preserving_error(resource: T) -> Iterator[T]:
    try:
        yield resource
    except BaseException as primary:
        close_after_error(resource, primary)
        raise
    else:
        resource.close()
