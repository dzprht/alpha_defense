import type { components, operations } from "@/shared/api/generated/openapi";

export type AnonymousSession = components["schemas"]["AnonymousSessionResponse"];
export type Consent = components["schemas"]["ConsentResponse"];
export type ConsentScope = components["schemas"]["ConsentScope"];
export type ConsentStatus = components["schemas"]["ConsentStatus"];
export type ProblemDetails = components["schemas"]["ProblemDetails"];
export type Session = components["schemas"]["SessionResponse"];
export type SessionState =
  operations["get_session"]["responses"][200]["content"]["application/json"];
export type StartDemoSessionBody =
  operations["start_demo_session"]["requestBody"]["content"]["application/json"];
export type AccountCredentialsBody =
  operations["register_account"]["requestBody"]["content"]["application/json"];
export type UpdateConsentBody =
  operations["update_consent"]["requestBody"]["content"]["application/json"];
