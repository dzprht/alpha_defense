import { AppErrorBoundary } from "@/app/ErrorBoundary";
import { AppProviders } from "@/app/providers";
import { AppRouter } from "@/app/router";

export function App() {
  return (
    <AppErrorBoundary>
      <AppProviders>
        <AppRouter />
      </AppProviders>
    </AppErrorBoundary>
  );
}
