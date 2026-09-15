# Локальная разработка

Статус: проверено для P01–P03 2026-09-15. Здесь зафиксированы инструменты и команды;
backend-приложение появится в P04, web-shell — в P06. Статические проверки и текущие
backend/frontend тесты исполнимы, но команды запуска приложений пока только подготовлены.

## Проверенные инструменты

| Инструмент | Версия на проверенном стенде | Назначение |
| --- | --- | --- |
| macOS | Darwin 25.6.0 arm64 | Локальный стенд P01 |
| Python | 3.11.15 | Единственная поддерживаемая minor-ветка backend |
| uv | 0.11.7 | Разрешение и проверка `uv.lock` |
| Node.js | 26.4.0 | Frontend toolchain; удовлетворяет engines |
| npm | 11.17.0 | Создание `package-lock.json` и воспроизводимая установка |

Прямые Python- и Node-зависимости закреплены точными версиями в соответствующих
manifest-файлах. Транзитивные версии и целостность артефактов находятся в `uv.lock` и
`package-lock.json`; lock-файлы не редактируются вручную.

## Backend

Рабочий каталог всех команд этого раздела:

```bash
cd apps/backend
```

Проект использует общий venv из инструкции репозитория. `--inexact` обязателен: обычный
`uv sync` удаляет пакеты, не перечисленные в проекте, и потому небезопасен для общей среды.

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv sync --frozen --inexact
```

Проверки manifest/lock и уже существующего исходного дерева:

```bash
uv lock --check
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen ruff check src tests migrations
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen ruff format --check src tests migrations
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen mypy
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen lint-imports --config pyproject.toml
```

Запуск unit-, contract-, integration- и architecture-тестов backend:

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen pytest
```

### Локальная SQLite и миграции

Миграции не выполняются при импорте модулей. До появления bootstrap в P04 их нужно запускать
явно из `apps/backend`; конфигурация по умолчанию использует исключенный из Git файл
`../../var/alpha_defense.db`:

```bash
mkdir -p ../../var
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen alembic upgrade head
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen alembic current
```

Проверка upgrade/downgrade, отсутствия drift, сохранения audit/outbox после restart и
восстановления истекшего lease входит в интеграционный набор:

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen pytest tests/integration/test_sqlite_persistence.py
```

Outbox имеет семантику at-least-once: handler вызывается вне локальной транзакции, успешный
результат фиксируется отдельным commit, а истекший lease снова подбирается dispatcher. Это не
гарантия exactly-once и не замена provider idempotency для будущих денежных операций.

После реализации bootstrap в P04 сервер будет запускаться из того же каталога командой:

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen uvicorn alpha_defense.bootstrap.app:create_app --factory --reload
```

## Frontend

Рабочий каталог всех команд этого раздела:

```bash
cd apps/web
```

Воспроизводимая установка и доступные проверки конфигурации:

```bash
npm ci
npm run lint
npm run typecheck
npm run format:check
```

Vitest уже проверяет frontend import boundaries. Playwright-команда подготовлена для будущей
браузерной приемки:

```bash
npm test
npm run test:e2e
```

После реализации web-shell в P06 станут исполнимы команды приложения:

```bash
npm run dev
npm run build
npm run preview
```

Генерация клиентских типов требует существующего экспорта P04
`contracts/http/openapi.json`:

```bash
npm run generate:api
```

Playwright-браузеры не устанавливаются в P01. Их установка и первый фактический E2E-прогон
выполняются в карточке, которая добавляет браузерную приемку.

## Известное состояние общего Python venv

Проверка `/Users/Shared/github/MachineLearning/ml_venv/bin/python -m pip check` 2026-09-15
возвращает уже существующие конфликты `rectools==0.19.0` с установленными в общей среде
`attrs==26.1.0`, `numpy==2.4.6` и `pandas==3.0.5`. Эти пакеты не входят в `uv.lock` проекта и
не изменялись установкой P01. Исправлять их массовым downgrade в общей среде нельзя без
отдельной проверки проектов-потребителей. Проверки Alpha Defense из раздела Backend проходят
через этот venv; конфликт следует учитывать, если будущая задача начнет использовать
`rectools` (текущая архитектура этого не требует).

## Обновление зависимостей

Обновление — отдельное осознанное изменение: изменить точный direct pin, пересоздать
соответствующий lock-файл и повторить проверки затронутой части. Для Python использовать
`uv lock --upgrade-package name==version`, для Node — `npm install --save-exact name@version`
или `npm install --save-dev --save-exact name@version`. Не выполнять незакрепленный массовый
upgrade и не запускать `uv sync` без `--inexact` против общего venv.
