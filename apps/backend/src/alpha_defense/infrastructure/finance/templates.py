"""Versioned, code-owned fixtures; no real account or payment data is loaded."""

from __future__ import annotations

from alpha_defense.application.transfers import ProfileTemplate, TemplateOperation

_VERSION = "demo-finance-v1"
_REGULAR_AMOUNTS = (
    120_000,
    95_000,
    135_000,
    110_000,
    105_000,
    140_000,
    100_000,
    125_000,
    115_000,
    130_000,
    90_000,
    145_000,
)
_REGULAR_RECIPIENTS = (
    "utilities",
    "family",
    "market",
    "utilities",
    "family",
    "market",
    "utilities",
    "family",
    "market",
    "utilities",
    "family",
    "market",
)


class StaticProfileTemplates:
    """Three deliberately different examples for normal, sparse, and empty history."""

    def __init__(self) -> None:
        self._templates = (
            ProfileTemplate(
                code="regular",
                version=_VERSION,
                title="Регулярные платежи",
                description="12 вымышленных завершённых операций за последние 84 дня.",
                operations=tuple(
                    TemplateOperation(
                        days_before_creation=7 * (index + 1),
                        amount_minor=amount,
                        recipient_code=_REGULAR_RECIPIENTS[index],
                    )
                    for index, amount in enumerate(_REGULAR_AMOUNTS)
                ),
            ),
            ProfileTemplate(
                code="sparse",
                version=_VERSION,
                title="Редкие переводы",
                description="5 вымышленных завершённых операций: данных для сравнения мало.",
                operations=tuple(
                    TemplateOperation(
                        days_before_creation=10 * (index + 1),
                        amount_minor=amount,
                        recipient_code="family" if index % 2 else "utilities",
                    )
                    for index, amount in enumerate((80_000, 150_000, 90_000, 200_000, 75_000))
                ),
            ),
            ProfileTemplate(
                code="empty",
                version=_VERSION,
                title="Без истории",
                description="Новый вымышленный профиль без завершённых операций.",
                operations=(),
            ),
        )

    def list_templates(self) -> tuple[ProfileTemplate, ...]:
        return self._templates

    def get_template(self, code: str) -> ProfileTemplate | None:
        return next((item for item in self._templates if item.code == code), None)
