import { ApiError } from "@/shared/api";

export function errorMessage(error: Error): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Не удалось связаться с сервисом. Проверьте подключение и повторите попытку.";
}
