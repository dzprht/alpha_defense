import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";

import { submitContact } from "@/features/contact-check/api/contact-api";
import { contactError } from "@/features/contact-check/model/contactError";
import {
  buildContactInput,
  resultPath,
  validateContactInput,
} from "@/features/contact-check/model/contactInput";
import type { ContactKind } from "@/features/contact-check/model/contactInput";
import type { ContactSubmitBody, Session } from "@/shared/api/types";
import { Button, InlineNotice } from "@/shared/ui";

const textKinds = [
  { code: "sms", label: "SMS" },
  { code: "messenger", label: "Мессенджер" },
  { code: "call_transcript", label: "Расшифровка звонка" },
] as const;

interface ContactCommand {
  body: ContactSubmitBody;
  key: string;
  kind: ContactKind;
  value: string;
}

export function ContactForm({ session }: { session: Session }) {
  const navigate = useNavigate();
  const [kind, setKind] = useState<ContactKind>("sms");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const commandRef = useRef<ContactCommand | null>(null);
  const mutation = useMutation({
    mutationFn: (command: ContactCommand) => submitContact(command.body, command.key),
    onSuccess: (receipt) => {
      void navigate(
        resultPath(receipt.observation_id, receipt.incident_id, receipt.assessment.assessment_id),
      );
    },
  });
  const isUrl = kind === "web_resource";
  const consentScope = isUrl ? "analyze_resources" : "analyze_communications";
  const hasConsent = session.consents.some(
    (item) => item.scope === consentScope && item.status === "granted",
  );

  const updateKind = (next: ContactKind) => {
    setKind(next);
    setValidationError(null);
    commandRef.current = null;
    mutation.reset();
  };
  const updateValue = (next: string) => {
    if (isUrl) {
      setUrl(next);
    } else {
      setText(next);
    }
    setValidationError(null);
    commandRef.current = null;
    mutation.reset();
  };

  return (
    <form
      className="check-card"
      onSubmit={(event) => {
        event.preventDefault();
        const value = isUrl ? url : text;
        const error = validateContactInput(kind, value);
        setValidationError(error);
        if (error !== null || !hasConsent) {
          return;
        }
        const normalized = value.trim();
        let command = commandRef.current;
        if (command === null || command.kind !== kind || command.value !== normalized) {
          const key = globalThis.crypto.randomUUID();
          command = {
            body: buildContactInput(kind, normalized, key, new Date().toISOString()),
            key,
            kind,
            value: normalized,
          };
          commandRef.current = command;
        }
        mutation.mutate(command);
      }}
    >
      <h2>Что проверить?</h2>
      <p className="card-description">
        Введите только вымышленный пример. Приложение не читает ваши SMS и не открывает ссылку.
      </p>
      <fieldset className="check-kind-list" disabled={mutation.isPending}>
        <legend>Источник обращения</legend>
        {textKinds.map((item) => (
          <label className="check-kind" key={item.code}>
            <input
              checked={kind === item.code}
              name="contact-kind"
              onChange={() => {
                updateKind(item.code);
              }}
              type="radio"
            />
            {item.label}
          </label>
        ))}
        <label className="check-kind">
          <input
            checked={isUrl}
            name="contact-kind"
            onChange={() => {
              updateKind("web_resource");
            }}
            type="radio"
          />
          Ссылка
        </label>
      </fieldset>
      <div className="check-field">
        {isUrl ? (
          <>
            <label htmlFor="contact-url">Адрес ссылки</label>
            <input
              autoComplete="off"
              disabled={mutation.isPending}
              id="contact-url"
              inputMode="url"
              maxLength={2048}
              onChange={(event) => {
                updateValue(event.target.value);
              }}
              placeholder="https://example.test/"
              type="text"
              value={url}
            />
            <p className="field-hint">Адрес будет показан как текст, без перехода на сайт.</p>
          </>
        ) : (
          <>
            <label htmlFor="contact-text">Текст сообщения или расшифровки</label>
            <textarea
              disabled={mutation.isPending}
              id="contact-text"
              maxLength={10_000}
              onChange={(event) => {
                updateValue(event.target.value);
              }}
              placeholder="Вставьте вымышленный текст для проверки"
              rows={7}
              value={text}
            />
            <p className="field-hint">Максимум 10 000 символов. Личные данные не вводите.</p>
          </>
        )}
      </div>
      {!hasConsent ? (
        <InlineNotice tone="error">
          Сначала разрешите {isUrl ? "анализ ссылок" : "анализ сообщений"} на странице{" "}
          <Link to="/welcome">аккаунта</Link>.
        </InlineNotice>
      ) : null}
      {validationError === null ? null : (
        <InlineNotice tone="error">{validationError}</InlineNotice>
      )}
      {mutation.error === null ? null : (
        <InlineNotice tone="error">{contactError(mutation.error)}</InlineNotice>
      )}
      {mutation.isPending ? <p role="status">Проверяем и сохраняем результат…</p> : null}
      <div className="form-actions">
        <Button disabled={!hasConsent || mutation.isPending} type="submit">
          {mutation.isPending ? "Проверяем…" : "Проверить"}
        </Button>
      </div>
    </form>
  );
}
