import { useId, useState } from "react";

import { errorMessage } from "@/features/onboarding/model/errorMessage";
import { useOnboarding } from "@/features/onboarding/model/useOnboarding";
import { AccountForm } from "@/features/onboarding/ui/AccountForm";
import type { ConsentScope, Session } from "@/shared/api/types";
import { formatMoscowDateTime } from "@/shared/formatting";
import strings from "@/shared/i18n/ru.json";
import { Button, InlineNotice } from "@/shared/ui";

const profileCodes = ["demo-user", "demo-senior"] as const;
const consentScopes: ConsentScope[] = [
  "analyze_communications",
  "analyze_resources",
  "use_transaction_history",
  "send_notifications",
  "participate_in_research",
];

type ProfileCode = (typeof profileCodes)[number];

export function Onboarding() {
  const { acceptSession, consentMutation, logoutMutation, sessionQuery, startSessionMutation } =
    useOnboarding();

  return (
    <section className="onboarding-layout" aria-labelledby="onboarding-title">
      <div className="hero-panel">
        <p className="eyebrow">{strings.onboarding.eyebrow}</p>
        <h1 id="onboarding-title">{strings.onboarding.title}</h1>
        <p className="hero-copy">{strings.onboarding.intro}</p>
      </div>

      {sessionQuery.isPending ? (
        <div className="onboarding-card loading-card" role="status">
          {strings.onboarding.loading}
        </div>
      ) : sessionQuery.isError ? (
        <LoadError
          error={sessionQuery.error}
          isRetrying={sessionQuery.isFetching}
          onRetry={() => void sessionQuery.refetch()}
        />
      ) : sessionQuery.data.status === "anonymous" ? (
        <div className="onboarding-stack">
          <AccountForm onAuthenticated={acceptSession} />
          <ProfileForm
            error={startSessionMutation.error}
            isPending={startSessionMutation.isPending}
            onSubmit={(profileCode) => {
              startSessionMutation.mutate(profileCode);
            }}
          />
        </div>
      ) : (
        <ConsentForm
          error={consentMutation.error}
          isPending={consentMutation.isPending}
          isLoggingOut={logoutMutation.isPending}
          logoutError={logoutMutation.error}
          onChange={(scope, granted) => {
            const currentSession = sessionQuery.data;
            if (currentSession.status !== "active") {
              return;
            }
            consentMutation.mutate({
              expectedRevision: currentSession.consent_revision,
              scope,
              status: granted ? "granted" : "revoked",
            });
          }}
          onLogout={() => {
            logoutMutation.mutate();
          }}
          session={sessionQuery.data}
          wasSaved={consentMutation.isSuccess}
        />
      )}
    </section>
  );
}

interface LoadErrorProps {
  error: Error;
  isRetrying: boolean;
  onRetry: () => void;
}

function LoadError({ error, isRetrying, onRetry }: LoadErrorProps) {
  return (
    <div className="onboarding-card">
      <h2>Сессию не удалось загрузить</h2>
      <InlineNotice tone="error">{errorMessage(error)}</InlineNotice>
      <div className="form-actions">
        <Button disabled={isRetrying} onClick={onRetry} type="button">
          {isRetrying ? strings.onboarding.loading : strings.onboarding.retry}
        </Button>
      </div>
    </div>
  );
}

interface ProfileFormProps {
  error: Error | null;
  isPending: boolean;
  onSubmit: (profileCode: ProfileCode) => void;
}

function ProfileForm({ error, isPending, onSubmit }: ProfileFormProps) {
  const [profileCode, setProfileCode] = useState<ProfileCode>("demo-user");
  const groupName = useId();

  return (
    <form
      className="onboarding-card"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(profileCode);
      }}
    >
      <h2>{strings.onboarding.profilesTitle}</h2>
      <p className="card-description">
        Профиль задаёт только синтетический контекст и не подтверждает личность пользователя.
      </p>
      <fieldset className="profile-list" disabled={isPending}>
        <legend className="visually-hidden">{strings.onboarding.profilesTitle}</legend>
        {profileCodes.map((code) => (
          <label className="profile-option" key={code}>
            <input
              checked={profileCode === code}
              name={groupName}
              onChange={() => {
                setProfileCode(code);
              }}
              type="radio"
              value={code}
            />
            <span>
              <span className="option-title">{strings.onboarding.profiles[code].title}</span>
              <span className="option-description">
                {strings.onboarding.profiles[code].description}
              </span>
            </span>
          </label>
        ))}
      </fieldset>
      {error === null ? null : <InlineNotice tone="error">{errorMessage(error)}</InlineNotice>}
      <div className="form-actions">
        <Button disabled={isPending} type="submit">
          {isPending ? strings.onboarding.starting : strings.onboarding.start}
        </Button>
      </div>
    </form>
  );
}

interface ConsentFormProps {
  error: Error | null;
  isPending: boolean;
  isLoggingOut: boolean;
  logoutError: Error | null;
  onChange: (scope: ConsentScope, granted: boolean) => void;
  onLogout: () => void;
  session: Session;
  wasSaved: boolean;
}

function ConsentForm({
  error,
  isPending,
  isLoggingOut,
  logoutError,
  onChange,
  onLogout,
  session,
  wasSaved,
}: ConsentFormProps) {
  const isAccount = session.auth_kind === "account";
  return (
    <div className="onboarding-card">
      <h2>{isAccount ? strings.account.activeTitle : strings.onboarding.activeTitle}</h2>
      <p className="card-description">
        {isAccount ? strings.account.activeDescription : strings.onboarding.activeDescription}
      </p>
      <p className="session-meta">
        {strings.onboarding.expires}:{" "}
        <strong>{formatMoscowDateTime(session.expires_at)} МСК</strong>
      </p>
      <h3 className="consent-heading">
        {isAccount ? strings.account.consentsTitle : strings.onboarding.consentsTitle}
      </h3>
      <div className="consent-list">
        {consentScopes.map((scope) => {
          const consent = session.consents.find((item) => item.scope === scope);
          const isGranted = consent?.status === "granted";
          return (
            <label className="consent-option" key={scope}>
              <input
                checked={isGranted}
                disabled={isPending || isLoggingOut}
                onChange={(event) => {
                  onChange(scope, event.target.checked);
                }}
                type="checkbox"
              />
              <span>
                <span className="option-title">{strings.onboarding.consents[scope].title}</span>
                <span className="option-description">
                  {strings.onboarding.consents[scope].description}
                </span>
              </span>
            </label>
          );
        })}
      </div>
      {isPending ? (
        <p className="notice" role="status">
          {strings.onboarding.saving}
        </p>
      ) : null}
      {error === null ? null : <InlineNotice tone="error">{errorMessage(error)}</InlineNotice>}
      {!isPending && error === null && wasSaved ? (
        <InlineNotice tone="success">{strings.onboarding.saved}</InlineNotice>
      ) : null}
      {logoutError === null ? null : (
        <InlineNotice tone="error">{errorMessage(logoutError)}</InlineNotice>
      )}
      <div className="form-actions">
        <Button
          disabled={isPending || isLoggingOut}
          onClick={onLogout}
          type="button"
          variant="secondary"
        >
          {isLoggingOut
            ? strings.account.loggingOut
            : isAccount
              ? strings.account.logoutAccount
              : strings.account.logoutDemo}
        </Button>
      </div>
    </div>
  );
}
