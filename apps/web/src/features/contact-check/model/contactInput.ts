import type { ContactSubmitBody } from "@/shared/api/types";

export type ContactKind = "sms" | "messenger" | "call_transcript" | "web_resource";

export function validateContactInput(kind: ContactKind, value: string): string | null {
  const normalized = value.trim();
  if (normalized.length === 0) {
    return kind === "web_resource" ? "Введите адрес ссылки." : "Введите текст сообщения.";
  }
  if (kind === "web_resource") {
    if (normalized.length > 2048) {
      return "Адрес слишком длинный: максимум 2048 символов.";
    }
    try {
      const parsed = new URL(normalized);
      if (!(["http:", "https:"].includes(parsed.protocol) && parsed.hostname)) {
        return "Введите полный адрес с http:// или https://.";
      }
    } catch {
      return "Введите полный адрес с http:// или https://.";
    }
  } else if (normalized.length > 10_000) {
    return "Текст слишком длинный: максимум 10 000 символов.";
  }
  return null;
}

export function buildContactInput(
  kind: ContactKind,
  value: string,
  eventId: string,
  occurredAt: string,
): ContactSubmitBody {
  const normalized = value.trim();
  switch (kind) {
    case "sms":
    case "messenger":
      return {
        kind,
        source_event_id: eventId,
        occurred_at: occurredAt,
        payload: { text: normalized, sender: "manual-entry", conversation_id: eventId },
      };
    case "call_transcript":
      return {
        kind,
        source_event_id: eventId,
        occurred_at: occurredAt,
        payload: {
          transcript: normalized,
          phone: "manual-entry",
          call_id: eventId,
          sequence: 0,
          segments: [],
        },
      };
    case "web_resource":
      return {
        kind,
        source_event_id: eventId,
        occurred_at: occurredAt,
        payload: { url: normalized },
      };
  }
}

export function resultPath(observationId: string, incidentId: string, assessmentId: string) {
  return `/checks/${observationId}/${incidentId}/${assessmentId}`;
}
