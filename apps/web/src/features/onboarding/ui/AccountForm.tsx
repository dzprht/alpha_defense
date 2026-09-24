import { useId, useRef, useState } from "react";

import { loginAccount, registerAccount } from "@/features/onboarding/api/session-api";
import { errorMessage } from "@/features/onboarding/model/errorMessage";
import type { Session } from "@/shared/api/types";
import strings from "@/shared/i18n/ru.json";
import { Button, InlineNotice } from "@/shared/ui";

type AccountMode = "login" | "register";

interface AccountFormProps {
  onAuthenticated: (session: Session) => void;
}

export function AccountForm({ onAuthenticated }: AccountFormProps) {
  const [mode, setMode] = useState<AccountMode>("login");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const retryKey = useRef<string | null>(null);
  const formId = useId();

  const clearError = () => {
    retryKey.current = null;
    setError(null);
  };

  const switchMode = (nextMode: AccountMode) => {
    if (mode === nextMode) {
      return;
    }
    setMode(nextMode);
    setPassword("");
    setConfirmation("");
    clearError();
  };

  const submit = async () => {
    if (mode === "register" && password !== confirmation) {
      setError(strings.account.passwordMismatch);
      return;
    }
    const key = retryKey.current ?? globalThis.crypto.randomUUID();
    retryKey.current = key;
    setIsPending(true);
    setError(null);
    try {
      const body = { login: login.trim(), password };
      const session =
        mode === "register" ? await registerAccount(body, key) : await loginAccount(body, key);
      onAuthenticated(session);
    } catch (cause) {
      setError(errorMessage(cause instanceof Error ? cause : new Error("Unexpected error")));
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="onboarding-card account-card">
      <div className="account-mode-switch" aria-label={strings.account.modeLabel}>
        <Button
          aria-pressed={mode === "login"}
          disabled={isPending}
          onClick={() => {
            switchMode("login");
          }}
          type="button"
          variant={mode === "login" ? "primary" : "secondary"}
        >
          {strings.account.loginTab}
        </Button>
        <Button
          aria-pressed={mode === "register"}
          disabled={isPending}
          onClick={() => {
            switchMode("register");
          }}
          type="button"
          variant={mode === "register" ? "primary" : "secondary"}
        >
          {strings.account.registerTab}
        </Button>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <h2>{mode === "login" ? strings.account.loginTitle : strings.account.registerTitle}</h2>
        <p className="card-description">
          {mode === "login"
            ? strings.account.loginDescription
            : strings.account.registerDescription}
        </p>
        <div className="account-fields">
          <label htmlFor={`${formId}-login`}>{strings.account.loginLabel}</label>
          <input
            autoComplete="username"
            disabled={isPending}
            id={`${formId}-login`}
            maxLength={64}
            minLength={3}
            onChange={(event) => {
              setLogin(event.target.value);
              clearError();
            }}
            pattern="[A-Za-z][A-Za-z0-9._-]{2,63}"
            required
            spellCheck={false}
            type="text"
            value={login}
          />
          <p className="field-hint">{strings.account.loginHint}</p>
          <label htmlFor={`${formId}-password`}>{strings.account.passwordLabel}</label>
          <input
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            disabled={isPending}
            id={`${formId}-password`}
            maxLength={128}
            minLength={12}
            onChange={(event) => {
              setPassword(event.target.value);
              clearError();
            }}
            required
            type="password"
            value={password}
          />
          <p className="field-hint">{strings.account.passwordHint}</p>
          {mode === "register" ? (
            <>
              <label htmlFor={`${formId}-confirmation`}>{strings.account.confirmLabel}</label>
              <input
                autoComplete="new-password"
                disabled={isPending}
                id={`${formId}-confirmation`}
                maxLength={128}
                minLength={12}
                onChange={(event) => {
                  setConfirmation(event.target.value);
                  clearError();
                }}
                required
                type="password"
                value={confirmation}
              />
            </>
          ) : null}
        </div>
        {error === null ? null : <InlineNotice tone="error">{error}</InlineNotice>}
        <div className="form-actions">
          <Button disabled={isPending} type="submit">
            {isPending
              ? strings.account.submitting
              : mode === "login"
                ? strings.account.loginSubmit
                : strings.account.registerSubmit}
          </Button>
        </div>
      </form>
    </div>
  );
}
