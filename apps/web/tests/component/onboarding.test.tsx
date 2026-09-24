import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createAppQueryClient } from "@/app/queryClient";
import { Onboarding } from "@/features/onboarding";
import type { Session } from "@/shared/api/types";

const anonymousSession = {
  capabilities: ["start_demo_session"],
  execution_mode: "mock",
  pre_session_expires_at: "2026-09-19T12:00:00Z",
  status: "anonymous",
} as const;

const activeSession: Session = {
  capabilities: ["update_consents"],
  consent_revision: 0,
  consents: [],
  execution_mode: "mock",
  expires_at: "2026-09-19T14:30:00Z",
  namespace_id: "00000000-0000-0000-0000-000000000003",
  roles: ["demo_user"],
  session_id: "00000000-0000-0000-0000-000000000002",
  status: "active",
  auth_kind: "demo",
  user_id: "00000000-0000-0000-0000-000000000001",
};

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  document.cookie = "alpha_defense_csrf=csrf-token; path=/";
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("onboarding", () => {
  it("restores an active session after a new mount", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(activeSession)));

    const firstRender = renderOnboarding();
    expect(
      await screen.findByRole("heading", { name: "Демонстрационная сессия активна" }),
    ).toBeVisible();
    firstRender.unmount();

    renderOnboarding();
    expect(
      await screen.findByRole("heading", { name: "Демонстрационная сессия активна" }),
    ).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps the keyboard-selected profile after a backend error", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse(anonymousSession)).mockResolvedValueOnce(
      jsonResponse(
        {
          code: "dependency_unavailable",
          detail: "Сервис сессий временно недоступен.",
          instance: "/api/v1/sessions/demo",
          request_id: "request-1",
          retryable: true,
          status: 503,
          title: "Сервис недоступен",
          type: "urn:alpha-defense:problem:dependency_unavailable",
        },
        503,
      ),
    );
    renderOnboarding();

    const seniorProfile = await screen.findByRole("radio", { name: /Повышенное внимание/u });
    seniorProfile.focus();
    await user.keyboard(" ");
    expect(seniorProfile).toBeChecked();
    const submit = screen.getByRole("button", { name: "Начать демонстрацию" });
    submit.focus();
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Сервис сессий временно недоступен.",
    );
    expect(seniorProfile).toBeChecked();

    const [, request] = fetchMock.mock.calls[1] ?? [];
    expect(request?.credentials).toBe("include");
    expect(request?.method).toBe("POST");
    expect(request?.body).toBe(JSON.stringify({ profile_code: "demo-senior" }));
    expect(new Headers(request?.headers).get("X-CSRF-Token")).toBe("csrf-token");
    expect(new Headers(request?.headers).get("Idempotency-Key")).not.toBeNull();
  });

  it("sends grants and revocations with the latest backend revision", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(activeSession))
      .mockResolvedValueOnce(
        jsonResponse({
          changed_at: "2026-09-19T12:01:00Z",
          revision: 1,
          scope: "participate_in_research",
          status: "granted",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          changed_at: "2026-09-19T12:02:00Z",
          revision: 2,
          scope: "participate_in_research",
          status: "revoked",
        }),
      );
    renderOnboarding();

    const researchConsent = await screen.findByRole("checkbox", {
      name: /Участвовать в исследовании/u,
    });
    expect(researchConsent).not.toBeChecked();
    await user.click(researchConsent);

    expect(await screen.findByText("Изменение сохранено.")).toBeVisible();
    expect(researchConsent).toBeChecked();
    const [, request] = fetchMock.mock.calls[1] ?? [];
    expect(request?.method).toBe("PATCH");
    expect(request?.body).toBe(JSON.stringify({ expected_revision: 0, status: "granted" }));
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/consents/participate_in_research");

    await user.click(researchConsent);
    await waitFor(() => {
      expect(researchConsent).not.toBeChecked();
    });
    const [, revokeRequest] = fetchMock.mock.calls[2] ?? [];
    expect(revokeRequest?.body).toBe(JSON.stringify({ expected_revision: 1, status: "revoked" }));
  });

  it("checks registration confirmation without sending a request", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse(anonymousSession));
    renderOnboarding();

    await user.click(await screen.findByRole("button", { name: "Регистрация" }));
    await user.type(screen.getByRole("textbox", { name: "Логин" }), "student_one");
    await user.type(screen.getByLabelText("Пароль"), "safe-test-pass-123");
    await user.type(screen.getByLabelText("Повторите пароль"), "different-pass-123");
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Пароли не совпадают");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps registration fields after a server error and sends only credentials", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(anonymousSession))
      .mockResolvedValueOnce(problemResponse("login_taken", "Такой логин уже занят.", 409));
    renderOnboarding();

    await user.click(await screen.findByRole("button", { name: "Регистрация" }));
    const login = screen.getByRole("textbox", { name: "Логин" });
    await user.type(login, "student_one");
    await user.type(screen.getByLabelText("Пароль"), "safe-test-pass-123");
    await user.type(screen.getByLabelText("Повторите пароль"), "safe-test-pass-123");
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Такой логин уже занят.");
    expect(login).toHaveValue("student_one");
    const [, request] = fetchMock.mock.calls[1] ?? [];
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/accounts");
    expect(request?.body).toBe(
      JSON.stringify({ login: "student_one", password: "safe-test-pass-123" }),
    );
    expect(new Headers(request?.headers).get("X-CSRF-Token")).toBe("csrf-token");
    expect(new Headers(request?.headers).get("Idempotency-Key")).not.toBeNull();
  });

  it("logs in, logs out on a 204 response, and restores anonymous state", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(anonymousSession))
      .mockResolvedValueOnce(jsonResponse({ ...activeSession, auth_kind: "account" }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse(anonymousSession));
    renderOnboarding();

    await user.type(await screen.findByRole("textbox", { name: "Логин" }), "student_one");
    await user.type(screen.getByLabelText("Пароль"), "safe-test-pass-123");
    await user.click(screen.getByRole("button", { name: "Войти в аккаунт" }));
    expect(await screen.findByRole("heading", { name: "Учебный аккаунт активен" })).toBeVisible();
    const [, loginRequest] = fetchMock.mock.calls[1] ?? [];
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/sessions");
    expect(loginRequest?.body).toBe(
      JSON.stringify({ login: "student_one", password: "safe-test-pass-123" }),
    );

    await user.click(screen.getByRole("button", { name: "Выйти из аккаунта" }));
    expect(await screen.findByRole("heading", { name: "Войти в учебный аккаунт" })).toBeVisible();
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/v1/sessions/logout");
    expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/v1/session");
  });
});

function renderOnboarding() {
  return render(
    <QueryClientProvider client={createAppQueryClient()}>
      <Onboarding />
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });
}

function problemResponse(code: string, detail: string, status: number): Response {
  return jsonResponse(
    {
      code,
      detail,
      instance: "/api/v1/accounts",
      request_id: "test-request",
      retryable: false,
      status,
      title: "Ошибка",
      type: `urn:alpha-defense:problem:${code}`,
    },
    status,
  );
}
