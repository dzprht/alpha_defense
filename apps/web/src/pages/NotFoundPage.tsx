import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main className="fatal-error" id="main-content">
      <p className="eyebrow">404</p>
      <h1>Такой страницы пока нет</h1>
      <p>В текущей версии реализован только безопасный вход в демонстрацию.</p>
      <Link className="button button--primary" to="/welcome">
        Вернуться к началу
      </Link>
    </main>
  );
}
