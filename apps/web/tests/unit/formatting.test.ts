import { describe, expect, it } from "vitest";

import { formatMoney, formatMoscowDateTime } from "@/shared/formatting";

describe("Russian formatting", () => {
  it("formats minor units as roubles", () => {
    const formatted = formatMoney(123_456);

    expect(formatted).toMatch(/1[\s\u00a0]234,56\s₽/u);
  });

  it("converts UTC instants to Moscow time", () => {
    const formatted = formatMoscowDateTime("2026-01-15T09:30:00Z");

    expect(formatted).toContain("12:30");
    expect(formatted).toContain("2026");
  });

  it("rejects fractional minor units", () => {
    expect(() => formatMoney(10.5)).toThrow(RangeError);
  });
});
