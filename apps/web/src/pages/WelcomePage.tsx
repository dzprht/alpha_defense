import { Onboarding } from "@/features/onboarding";
import strings from "@/shared/i18n/ru.json";

export function WelcomePage() {
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
        <span className="demo-badge">{strings.demoBadge}</span>
      </header>
      <main id="main-content" className="page-content">
        <Onboarding />
      </main>
      <footer className="site-footer">
        <strong>{strings.demoBadge}.</strong> Система работает только с синтетическими данными.
      </footer>
    </div>
  );
}
