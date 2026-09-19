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
