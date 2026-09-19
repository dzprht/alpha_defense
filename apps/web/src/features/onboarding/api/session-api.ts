import { apiRequest } from "@/shared/api";
import type {
  Consent,
  ConsentScope,
  Session,
  SessionState,
  StartDemoSessionBody,
  UpdateConsentBody,
} from "@/shared/api/types";

export function getSession(): Promise<SessionState> {
  return apiRequest<SessionState>("/session");
}

export function startDemoSession(profileCode: string): Promise<Session> {
  const body: StartDemoSessionBody = { profile_code: profileCode };
  return apiRequest<Session>("/sessions/demo", {
    body,
    command: true,
    method: "POST",
  });
}

export function updateConsent(
  scope: ConsentScope,
  status: UpdateConsentBody["status"],
  expectedRevision: number,
): Promise<Consent> {
  const body: UpdateConsentBody = {
    expected_revision: expectedRevision,
    status,
  };
  return apiRequest<Consent>(`/consents/${scope}`, {
    body,
    command: true,
    method: "PATCH",
  });
}
