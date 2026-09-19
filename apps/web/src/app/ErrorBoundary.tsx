import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/shared/ui";

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  failed: boolean;
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  public state: AppErrorBoundaryState = { failed: false };

  public static getDerivedStateFromError(): AppErrorBoundaryState {
    return { failed: true };
  }

  public componentDidCatch(error: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error("Unexpected UI failure", error.name, info.componentStack);
    }
  }

  public render(): ReactNode {
    if (this.state.failed) {
      return (
        <main className="fatal-error" id="main-content">
          <p className="eyebrow">Демонстрация</p>
          <h1>Экран не удалось открыть</h1>
          <p>Обновите страницу. Введённые на сервере согласия сохранятся.</p>
          <Button
            onClick={() => {
              window.location.reload();
            }}
          >
            Обновить страницу
          </Button>
        </main>
      );
    }
    return this.props.children;
  }
}
