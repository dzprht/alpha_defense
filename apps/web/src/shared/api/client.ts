import type { ProblemDetails } from "@/shared/api/types";

const API_PREFIX = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const CSRF_COOKIE_NAME = "alpha_defense_csrf";

interface ApiRequestOptions {
  body?: unknown;
  command?: boolean;
  idempotencyKey?: string;
  method?: "GET" | "PATCH" | "POST";
}

export class ApiError extends Error {
  public readonly code: string;
  public readonly fieldErrors: ProblemDetails["field_errors"];
  public readonly retryable: boolean;
  public readonly status: number;

  public constructor(problem: ProblemDetails) {
    super(problem.detail);
    this.name = "ApiError";
    this.code = problem.code;
    this.fieldErrors = problem.field_errors;
    this.retryable = problem.retryable;
    this.status = problem.status;
  }
}

export async function apiRequest<ResponseBody>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<ResponseBody> {
  const method = options.method ?? "GET";
  const headers = new Headers({ Accept: "application/json" });
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (options.command === true) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME);
    if (csrfToken === null) {
      throw new Error("CSRF cookie is missing");
    }
    headers.set("X-CSRF-Token", csrfToken);
    headers.set("Idempotency-Key", options.idempotencyKey ?? globalThis.crypto.randomUUID());
  }

  const request: RequestInit = {
    credentials: "include",
    headers,
    method,
  };
  if (options.body !== undefined) {
    request.body = JSON.stringify(options.body);
  }

  const response = await fetch(`${API_PREFIX}${path}`, request);
  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    return undefined as ResponseBody;
  }
  return (await response.json()) as ResponseBody;
}

function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return match === undefined ? null : decodeURIComponent(match.slice(prefix.length));
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const candidate: unknown = await response.json();
    if (isProblemDetails(candidate)) {
      return new ApiError(candidate);
    }
  } catch {
    // A non-JSON upstream failure is represented by one safe client-side message.
  }
  return new ApiError({
    code: "unexpected_response",
    detail: "Сервис вернул неожиданный ответ. Повторите попытку.",
    instance: "",
    request_id: "",
    retryable: response.status >= 500,
    status: response.status,
    title: "Неожиданный ответ",
    type: "urn:alpha-defense:problem:unexpected_response",
  });
}

function isProblemDetails(value: unknown): value is ProblemDetails {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<ProblemDetails>;
  return (
    typeof candidate.code === "string" &&
    typeof candidate.detail === "string" &&
    typeof candidate.instance === "string" &&
    typeof candidate.request_id === "string" &&
    typeof candidate.retryable === "boolean" &&
    typeof candidate.status === "number" &&
    typeof candidate.title === "string" &&
    typeof candidate.type === "string"
  );
}
