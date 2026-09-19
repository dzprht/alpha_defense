const rubles = new Intl.NumberFormat("ru-RU", {
  currency: "RUB",
  currencyDisplay: "symbol",
  minimumFractionDigits: 2,
  style: "currency",
});

export function formatMoney(amountMinor: number, currency = "RUB"): string {
  if (!Number.isSafeInteger(amountMinor)) {
    throw new RangeError("Amount must be a safe integer in minor units");
  }
  if (currency !== "RUB") {
    throw new RangeError("Only RUB is supported by the MVP formatter");
  }
  return rubles.format(amountMinor / 100);
}
