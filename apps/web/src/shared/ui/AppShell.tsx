import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import strings from "@/shared/i18n/ru.json";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Перейти к основному содержимому
      </a>
      <header className="site-header">
        <div className="brand-mark" aria-hidden="true">
          А
        </div>
        <div>
          <p className="brand-name">{strings.appName}</p>
          <p className="brand-caption">Раннее предупреждение о мошенничестве</p>
        </div>
        <nav aria-label="Основная навигация" className="site-nav">
          <NavLink to="/welcome">Аккаунт</NavLink>
          <NavLink to="/check">Проверка</NavLink>
        </nav>
        <span className="demo-badge">{strings.demoBadge}</span>
      </header>
      <main id="main-content" className="page-content">
        {children}
      </main>
      <footer className="site-footer">
        <strong>{strings.demoBadge}.</strong> Используйте только вымышленные данные. Проверка не
        подтверждает факт мошенничества.
      </footer>
    </div>
  );
}
