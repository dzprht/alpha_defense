"""Money value object for the MVP transfer boundary."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

MAX_AMOUNT_MINOR: Final = 100_000_000


class Currency(StrEnum):
    """Currencies supported by the MVP."""

    RUB = "RUB"


@dataclass(frozen=True, slots=True)
class Money:
    """A positive amount represented only in integer minor units."""

    amount_minor: int
    currency: Currency

    def __post_init__(self) -> None:
        if type(self.amount_minor) is not int:
            raise TypeError("amount_minor must be an integer and must not be bool")
        if not 1 <= self.amount_minor <= MAX_AMOUNT_MINOR:
            raise ValueError(f"amount_minor must be between 1 and {MAX_AMOUNT_MINOR}")
        if not isinstance(self.currency, Currency):
            raise TypeError("currency must be a supported Currency")
