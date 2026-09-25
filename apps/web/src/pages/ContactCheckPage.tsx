import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ContactForm } from "@/features/contact-check/ui/ContactForm";
import { apiRequest } from "@/shared/api";
import type { SessionState } from "@/shared/api/types";
import { AppShell } from "@/shared/ui/AppShell";
import { Button, InlineNotice } from "@/shared/ui";

export function ContactCheckPage() {
  const session = useQuery({
    queryFn: () => apiRequest<SessionState>("/session"),
    queryKey: ["session"],
  });
  return (
    <AppShell>
      <div className="check-layout">
        <div className="hero-panel">
          <p className="eyebrow">Ручная проверка</p>
          <h1>Проверьте обращение до действия</h1>
          <p className="hero-copy">
            Прототип сравнит учебный текст с правилами и моделью или проверит признаки URL и
            локальный реестр. Он не устанавливает факт мошенничества.
          </p>
        </div>
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
            <h2>Сначала войдите</h2>
            <p>Для сохранения результата требуется учебный аккаунт или демо-сессия.</p>
            <Link to="/welcome">Перейти к входу</Link>
          </div>
        ) : (
          <ContactForm session={session.data} />
        )}
      </div>
    </AppShell>
  );
}
