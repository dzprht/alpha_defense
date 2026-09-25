import { describe, expect, it } from "vitest";

import {
  buildContactInput,
  resultPath,
  validateContactInput,
} from "@/features/contact-check/model/contactInput";

const eventId = "00000000-0000-4000-8000-000000000001";
const occurredAt = "2026-09-25T10:00:00.000Z";

describe("ручной контакт", () => {
  it("rejects blank, overlong and non-web URL input before sending", () => {
    expect(validateContactInput("sms", "  ")).toBe("Введите текст сообщения.");
    expect(validateContactInput("sms", "а".repeat(10_001))).toMatch(/10 000/u);
    expect(validateContactInput("web_resource", "javascript:alert(1)")).toMatch(/http/u);
    expect(validateContactInput("web_resource", "wrong-address")).toMatch(/http/u);
    expect(validateContactInput("web_resource", "https://example.test/path")).toBeNull();
  });

  it("maps SMS, messenger and transcript to distinct tagged contracts", () => {
    const sms = buildContactInput("sms", "  Учебный текст  ", eventId, occurredAt);
    const messenger = buildContactInput("messenger", "Учебный текст", eventId, occurredAt);
    const transcript = buildContactInput("call_transcript", "Учебный текст", eventId, occurredAt);
    expect(sms).toMatchObject({ kind: "sms", payload: { text: "Учебный текст" } });
    expect(messenger).toMatchObject({ kind: "messenger", payload: { text: "Учебный текст" } });
    expect(transcript).toMatchObject({
      kind: "call_transcript",
      payload: { transcript: "Учебный текст", segments: [], sequence: 0 },
    });
  });

  it("keeps URL as plain input and builds a restorable result path", () => {
    const url = buildContactInput(
      "web_resource",
      " https://example.test/card ",
      eventId,
      occurredAt,
    );
    expect(url).toMatchObject({
      kind: "web_resource",
      payload: { url: "https://example.test/card" },
    });
    expect(resultPath("observation", "incident", "assessment")).toBe(
      "/checks/observation/incident/assessment",
    );
  });
});
