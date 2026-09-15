"""Transport-neutral cursor pagination values."""

from dataclasses import dataclass
from typing import Generic, TypeVar

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

ItemT = TypeVar("ItemT")


def _validate_cursor(cursor: str | None) -> None:
    if cursor is None:
        return
    if not isinstance(cursor, str):
        raise TypeError("cursor must be a string or None")
    if not cursor or cursor != cursor.strip():
        raise ValueError("cursor must be non-empty and trimmed")


@dataclass(frozen=True, slots=True)
class PageRequest:
    """A validated opaque cursor and bounded page size."""

    cursor: str | None = None
    limit: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        _validate_cursor(self.cursor)
        if type(self.limit) is not int:
            raise TypeError("limit must be an integer and must not be bool")
        if not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")


@dataclass(frozen=True, slots=True)
class Page(Generic[ItemT]):
    """A page result with immutable items and an opaque continuation cursor."""

    items: tuple[ItemT, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        _validate_cursor(self.next_cursor)
