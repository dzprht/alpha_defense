import { ApiError } from "@/shared/api";

export function contactError(error: Error): string {
  if (!(error instanceof ApiError)) {
    return "Не удалось связаться с сервисом. Проверьте подключение и повторите попытку.";
  }
  switch (error.status) {
    case 401:
      return "Сессия закончилась. Войдите снова и повторите проверку.";
    case 403:
      return "Для проверки нужно разрешение. Проверьте его на стартовой странице.";
    case 404:
      return "Результат не найден или недоступен этому аккаунту.";
    case 409:
      return "Состояние изменилось. Обновите страницу и повторите проверку.";
    case 422:
      return "Проверьте введённый текст или адрес и повторите попытку.";
    case 503:
      return "Проверка временно недоступна. Сохраните ввод и попробуйте позже.";
    default:
      return error.message;
  }
}
