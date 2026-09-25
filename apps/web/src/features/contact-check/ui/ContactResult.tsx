import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import {
  getEducationCard,
  listEducationCards,
  presentWarning,
  reassessContact,
} from "@/features/contact-check/api/contact-api";
import type { ContactResult as ContactResultData } from "@/features/contact-check/api/contact-api";
import { contactError } from "@/features/contact-check/model/contactError";
import { resultPath } from "@/features/contact-check/model/contactInput";
import type { Warning } from "@/shared/api/types";
import { formatMoscowDateTime } from "@/shared/formatting";
import { Button, InlineNotice } from "@/shared/ui";

interface ContactResultProps {
  data: ContactResultData;
  queryKey: readonly unknown[];
}

export function ContactResult({ data, queryKey }: ContactResultProps) {
  const navigate = useNavigate();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const reassessmentKey = useRef<string | null>(null);
  const mutation = useMutation({
    mutationFn: (key: string) => reassessContact(data.observation.observation_id, key),
    onSuccess: (receipt) => {
      void navigate(
        resultPath(receipt.observation_id, receipt.incident_id, receipt.assessment.assessment_id),
      );
    },
  });
  useEffect(() => {
    titleRef.current?.focus();
  }, [data.assessment.assessment_id]);

  const rawUrl =
    data.observation.kind === "web_resource" && "url" in data.observation.payload
      ? data.observation.payload.url
      : null;
  const isIncomplete = data.assessment.completeness !== "complete";

  return (
    <div className="result-layout">
      <div className="result-topline">
        <Link to="/check">← Новая проверка</Link>
        <span className="demo-badge">Демонстрационный анализ</span>
      </div>
      <header className="result-header">
        <p className="eyebrow">Результат сохранён</p>
        <h1 ref={titleRef} tabIndex={-1}>
          {data.guidance.risk_label}
        </h1>
        <p>{data.guidance.explanation}</p>
        <p className="result-meta">
          Проверено {formatMoscowDateTime(data.assessment.assessed_at)} МСК · версия контекста{" "}
          {data.assessment.context_version}
        </p>
      </header>
      {isIncomplete ? (
        <InlineNotice tone="error">
          Проверка неполная или недоступна. Это не означает, что сообщение или ссылка безопасны.
        </InlineNotice>
      ) : null}
      {data.assessment.severity === "low" ? (
        <InlineNotice tone="success">
          Явных признаков не обнаружено, но отсутствие сигнала не гарантирует безопасность.
        </InlineNotice>
      ) : null}
      {data.warning === null ? null : <WarningPanel queryKey={queryKey} warning={data.warning} />}
      <section className="result-card" aria-labelledby="result-evidence-heading">
        <h2 id="result-evidence-heading">Что проверялось</h2>
        {rawUrl === null ? (
          <p>Введённый текст обработан по правилам и доступными анализаторами.</p>
        ) : (
          <p>
            Адрес: <code className="unsafe-url">{rawUrl}</code>
          </p>
        )}
        <p className="field-hint">
          {data.assessment.score === null
            ? "Численный балл не рассчитан."
            : `Эвристический балл: ${String(data.assessment.score)} из 100. Это не вероятность мошенничества.`}
        </p>
        <details>
          <summary>Технические основания и ограничения</summary>
          <p>Полнота: {data.assessment.completeness}.</p>
          <ul>
            {data.assessment.analyzer_results.map((item) => (
              <li key={item.analyzer}>
                {item.analyzer}: {item.status}
              </li>
            ))}
          </ul>
          <p>Коды причин: {data.assessment.reason_codes.join(", ") || "не указаны"}.</p>
          <p>Версия правил: {data.assessment.policy_version}.</p>
        </details>
      </section>
      <section className="result-card" aria-labelledby="result-guidance-heading">
        <h2 id="result-guidance-heading">Что делать дальше</h2>
        <ul className="recommendation-list">
          {data.guidance.recommendations.map((item) => (
            <li key={item.code}>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </li>
          ))}
        </ul>
        {data.guidance.support_message === null ? null : <p>{data.guidance.support_message}</p>}
        {data.guidance.support_contact === null ? null : (
          <p>Доверенный контакт: {data.guidance.support_contact.value}</p>
        )}
      </section>
      {data.guidance.education_cards.length === 0 ? null : (
        <EducationCards references={data.guidance.education_cards} />
      )}
      <section className="result-card" aria-labelledby="recheck-heading">
        <h2 id="recheck-heading">Повторная проверка</h2>
        <p>
          Новая оценка сохранится отдельно, прежний результат останется доступен по этой ссылке.
        </p>
        {mutation.error === null ? null : (
          <InlineNotice tone="error">{contactError(mutation.error)}</InlineNotice>
        )}
        <div className="form-actions">
          <Button
            disabled={mutation.isPending}
            onClick={() => {
              reassessmentKey.current ??= globalThis.crypto.randomUUID();
              mutation.mutate(reassessmentKey.current);
            }}
            type="button"
            variant="secondary"
          >
            {mutation.isPending ? "Проверяем…" : "Проверить ещё раз"}
          </Button>
        </div>
      </section>
    </div>
  );
}

function WarningPanel({ queryKey, warning }: { queryKey: readonly unknown[]; warning: Warning }) {
  const queryClient = useQueryClient();
  const nodeRef = useRef<HTMLElement>(null);
  const attemptedRef = useRef(false);
  const mutation = useMutation({
    mutationFn: () => presentWarning(warning.warning_id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  });
  const { mutate } = mutation;
  useEffect(() => {
    if (warning.presented_at !== null || attemptedRef.current) {
      return;
    }
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => {
        if (nodeRef.current?.isConnected && nodeRef.current.getClientRects().length > 0) {
          attemptedRef.current = true;
          mutate();
        }
      });
    });
    return () => {
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
    };
  }, [mutate, warning.presented_at]);

  return (
    <aside aria-labelledby="contact-warning-heading" className="warning-panel" ref={nodeRef}>
      <p className="eyebrow">Предупреждение</p>
      <h2 id="contact-warning-heading">{warning.risk_label}</h2>
      <p>{warning.explanation}</p>
      <p className="warning-limit">
        Это предупреждение не блокирует реальный платёж и не подтверждает источник обращения.
      </p>
      {mutation.error === null ? null : (
        <>
          <InlineNotice tone="error">
            Не удалось сохранить отметку о показе предупреждения.
          </InlineNotice>
          <Button
            disabled={mutation.isPending}
            onClick={() => {
              mutate();
            }}
            type="button"
          >
            Повторить подтверждение показа
          </Button>
        </>
      )}
    </aside>
  );
}

function EducationCards({ references }: { references: { code: string; version: string }[] }) {
  const [selected, setSelected] = useState<{ code: string; version: string } | null>(null);
  const catalog = useQuery({ queryFn: listEducationCards, queryKey: ["education-cards", "ru-RU"] });
  const query = useQuery({
    enabled: selected !== null,
    queryFn: () => {
      if (selected === null) {
        throw new Error("Учебная карточка не выбрана.");
      }
      return getEducationCard(selected.code, selected.version);
    },
    queryKey: ["education-card", selected?.code, selected?.version],
  });
  return (
    <section className="result-card" aria-labelledby="education-heading">
      <h2 id="education-heading">Учебные материалы</h2>
      <p>Откройте связанную карточку, чтобы подробнее узнать о схеме и безопасных действиях.</p>
      <div className="education-actions">
        {references.map((item, index) => (
          <Button
            key={`${item.code}:${item.version}`}
            onClick={() => {
              setSelected(item);
            }}
            type="button"
            variant="secondary"
          >
            {catalog.data?.items.find((card) => card.code === item.code)?.title ??
              `Учебный материал ${String(index + 1)}`}
          </Button>
        ))}
      </div>
      {query.isPending && selected !== null ? <p role="status">Загружаем карточку…</p> : null}
      {query.isError ? <InlineNotice tone="error">{contactError(query.error)}</InlineNotice> : null}
      {query.data === undefined ? null : (
        <article className="education-detail">
          <h3>{query.data.title}</h3>
          <p>{query.data.summary}</p>
          <EducationBody body={query.data.body} />
        </article>
      )}
    </section>
  );
}

function EducationBody({ body }: { body: string }) {
  return (
    <div className="education-body">
      {body
        .trim()
        .split(/\n\s*\n/u)
        .map((block, index) => {
          const key = `${String(index)}:${block.slice(0, 20)}`;
          if (block.startsWith("## ")) {
            return <h5 key={key}>{block.slice(3)}</h5>;
          }
          if (block.startsWith("# ")) {
            return <h4 key={key}>{block.slice(2)}</h4>;
          }
          return <p key={key}>{block}</p>;
        })}
    </div>
  );
}
