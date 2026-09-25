import { apiRequest } from "@/shared/api";
import type {
  Assessment,
  ContactReceipt,
  ContactSubmitBody,
  EducationCard,
  EducationCardPage,
  Guidance,
  Incident,
  Observation,
  Warning,
  WarningLookup,
} from "@/shared/api/types";

export interface ContactResult {
  assessment: Assessment;
  guidance: Guidance;
  incident: Incident;
  observation: Observation;
  warning: Warning | null;
}

export function submitContact(body: ContactSubmitBody, key: string): Promise<ContactReceipt> {
  return apiRequest<ContactReceipt>("/observations", {
    body,
    command: true,
    idempotencyKey: key,
    method: "POST",
  });
}

export function reassessContact(observationId: string, key: string): Promise<ContactReceipt> {
  return apiRequest<ContactReceipt>(`/observations/${observationId}/reassess`, {
    command: true,
    idempotencyKey: key,
    method: "POST",
  });
}

export async function getContactResult(
  observationId: string,
  incidentId: string,
  assessmentId: string,
): Promise<ContactResult> {
  const [observation, incident, assessment, guidance, warningLookup] = await Promise.all([
    apiRequest<Observation>(`/observations/${observationId}`),
    apiRequest<Incident>(`/incidents/${incidentId}`),
    apiRequest<Assessment>(`/assessments/${assessmentId}`),
    apiRequest<Guidance>(`/assessments/${assessmentId}/guidance`),
    apiRequest<WarningLookup>(`/assessments/${assessmentId}/warning`),
  ]);
  if (
    assessment.target_id !== observation.observation_id ||
    !incident.observation_ids.includes(observation.observation_id) ||
    !incident.assessment_ids.includes(assessment.assessment_id) ||
    (warningLookup.warning !== null &&
      warningLookup.warning.assessment_id !== assessment.assessment_id)
  ) {
    throw new Error("Сохранённые части проверки не совпадают. Откройте результат заново.");
  }
  return { assessment, guidance, incident, observation, warning: warningLookup.warning };
}

export function presentWarning(warningId: string): Promise<Warning> {
  return apiRequest<Warning>(`/warnings/${warningId}/present`, {
    command: true,
    method: "POST",
  });
}

export function getEducationCard(code: string, version: string): Promise<EducationCard> {
  const query = new URLSearchParams({ locale: "ru-RU", version });
  return apiRequest<EducationCard>(`/education/cards/${encodeURIComponent(code)}?${query}`);
}

export function listEducationCards(): Promise<EducationCardPage> {
  return apiRequest<EducationCardPage>("/education/cards?locale=ru-RU&limit=20");
}
