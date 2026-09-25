import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getContactResult } from "@/features/contact-check/api/contact-api";
import { contactError } from "@/features/contact-check/model/contactError";
import { ContactResult } from "@/features/contact-check/ui/ContactResult";
import { apiRequest } from "@/shared/api";
import type { SessionState } from "@/shared/api/types";
import { Button, InlineNotice } from "@/shared/ui";
import { AppShell } from "@/shared/ui/AppShell";

export function ContactResultPage() {
  const { assessmentId, incidentId, observationId } = useParams();
  const session = useQuery({
    queryFn: () => apiRequest<SessionState>("/session"),
    queryKey: ["session"],
  });
  const resultKey = [
    "contact-result",
    session.data?.status === "active" ? session.data.user_id : null,
    session.data?.status === "active" ? session.data.namespace_id : null,
    observationId,
    incidentId,
    assessmentId,
  ] as const;
  const result = useQuery({
    enabled:
      session.data?.status === "active" &&
      observationId !== undefined &&
      incidentId !== undefined &&
      assessmentId !== undefined,
    queryFn: () => {
      if (observationId === undefined || incidentId === undefined || assessmentId === undefined) {
        throw new Error("Неполный адрес сохранённого результата.");
      }
      return getContactResult(observationId, incidentId, assessmentId);
    },
    queryKey: resultKey,
  });

  return (
    <AppShell>
      {session.isPending ? (
        <div className="check-card" role="status">
          Восстанавливаем сессию…
        </div>
      ) : session.isError ? (
        <div className="check-card">
          <InlineNotice tone="error">Не удалось загрузить сессию.</InlineNotice>
          <Button onClick={() => void session.refetch()} type="button">
            Повторить
          </Button>
        </div>
      ) : session.data.status === "anonymous" ? (
        <div className="check-card">
          <h1>Нужен вход</h1>
          <p>Сохранённые проверки доступны только владельцу.</p>
          <Link to="/welcome">Перейти к входу</Link>
        </div>
      ) : result.isPending ? (
        <div className="check-card" role="status">
          Загружаем сохранённый результат…
        </div>
      ) : result.isError ? (
        <div className="check-card">
          <h1>Результат не открылся</h1>
          <InlineNotice tone="error">{contactError(result.error)}</InlineNotice>
          <Button onClick={() => void result.refetch()} type="button">
            Повторить загрузку
          </Button>
        </div>
      ) : (
        <ContactResult data={result.data} queryKey={resultKey} />
      )}
    </AppShell>
  );
}
