import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getSession, startDemoSession, updateConsent } from "@/features/onboarding/api/session-api";
import type { ConsentScope, ConsentStatus, SessionState } from "@/shared/api/types";

const sessionQueryKey = ["session"] as const;

interface ConsentChange {
  expectedRevision: number;
  scope: ConsentScope;
  status: ConsentStatus;
}

export function useOnboarding() {
  const queryClient = useQueryClient();
  const sessionQuery = useQuery({
    queryFn: getSession,
    queryKey: sessionQueryKey,
  });

  const startSessionMutation = useMutation({
    mutationFn: startDemoSession,
    onSuccess: (session) => {
      queryClient.setQueryData<SessionState>(sessionQueryKey, session);
    },
  });

  const consentMutation = useMutation({
    mutationFn: ({ expectedRevision, scope, status }: ConsentChange) =>
      updateConsent(scope, status, expectedRevision),
    onSuccess: (changedConsent) => {
      queryClient.setQueryData<SessionState>(sessionQueryKey, (current) => {
        if (current?.status !== "active") {
          return current;
        }
        const hasConsent = current.consents.some(
          (consent) => consent.scope === changedConsent.scope,
        );
        return {
          ...current,
          consent_revision: changedConsent.revision,
          consents: hasConsent
            ? current.consents.map((consent) =>
                consent.scope === changedConsent.scope ? changedConsent : consent,
              )
            : [...current.consents, changedConsent],
        };
      });
    },
  });

  return {
    consentMutation,
    sessionQuery,
    startSessionMutation,
  };
}
