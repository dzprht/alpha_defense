# Локальная разработка

Статус: проверено для P01–P11 2026-09-21. Здесь зафиксированы инструменты и команды;
backend HTTP-контур, synthetic demo-сессии, onboarding web-shell и валидатор обязательного
каталога исполнимы. Синтетический threat registry можно идемпотентно заполнить и обновить
отдельной операторской командой.

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
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen ruff check src tests migrations ../../scripts/*.py
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen ruff format --check src tests migrations ../../scripts/*.py
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen mypy
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen lint-imports --config pyproject.toml
```

Запуск unit-, contract-, integration- и architecture-тестов backend:

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen pytest
```

### Локальная SQLite и миграции

Миграции не выполняются при импорте модулей или старте приложения. Их нужно запускать явно из
`apps/backend`; конфигурация примера использует исключенный из Git файл
`../../var/alpha_defense.db`:

```bash
mkdir -p ../../var
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen alembic upgrade head
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen alembic current
```

Проверка upgrade/downgrade, отсутствия drift, сохранения audit/outbox, threat snapshot,
observations, incidents и pending-контекста после restart, а также восстановления истекшего
lease входит в интеграционный набор:

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen pytest tests/integration/test_sqlite_persistence.py
```

Outbox имеет семантику at-least-once: handler вызывается вне локальной транзакции, успешный
результат фиксируется отдельным commit, а истекший lease снова подбирается dispatcher. Это не
гарантия exactly-once и не замена provider idempotency для будущих денежных операций.

### Запуск HTTP-контура

Подготовить локальную конфигурацию, заменить placeholder-секрет и создать runtime-каталог:

```bash
cp ../../ops/local/.env.example .env
mkdir -p ../../var/media
# Отредактировать SESSION_SECRET в .env: не менее 32 случайных символов.
```

После применения миграций загрузить переменные только в текущую shell-сессию и запустить
сервер:

```bash
set -a
source .env
set +a
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen uvicorn alpha_defense.bootstrap.app:create_app --factory --reload
```

Перед запуском каталог можно проверить отдельно от HTTP:

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen python ../../scripts/validate_catalog.py
```

Команда проверяет JSON Schema, поддерживаемые версии, hash содержимого и ссылки только внутри
`FIXTURE_ROOT`. Проверка живости отвечает 200, если процесс способен обработать HTTP.
Проверка готовности дополнительно проверяет SQLite на текущей миграции и весь обязательный
каталог:

```bash
curl -i http://127.0.0.1:8000/api/v1/health/live
curl -i http://127.0.0.1:8000/api/v1/health/ready
```

С конфигурацией из примера, примененными миграциями и неизмененным валидным каталогом второй
запрос отвечает 200. Поврежденный JSON, неизвестная версия, неверный hash или небезопасная
ссылка дают 503 в формате `application/problem+json`; внутренний путь и причина наружу не
выводятся.

### Синтетический реестр угроз

После применения миграций и загрузки `.env` первая команда создает текущий снимок из
валидированных fixtures. Повтор с той же версией не создает дубликат; `published=false`
показывает идемпотентный повтор:

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen python ../../scripts/refresh_threat_registry.py refresh
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen python ../../scripts/refresh_threat_registry.py status
```

Плохой пакет не переключает текущую версию. Статус `unavailable` или `expired` нельзя
трактовать как отсутствие угрозы. Команда использует только локальный synthetic feed; она не
вызывает МВД/РКН, банковские или коммерческие API и не публикует административный HTTP-route.

### Наблюдения коммуникаций

P09 добавляет внутреннюю application-операцию приема и отдельную схему хранения
raw-content, метаданных и нормализованных индикаторов. После `alembic upgrade head` новые таблицы
готовы, но отдельного операторского или публичного HTTP-входа для них нет: `POST /observations` будет открыт
только в полном workflow. Текущая приемка выполняется через unit/contract/integration-тесты, которые
запускаются общей backend-командой `pytest`.

### Предварительные инциденты и свежесть контекста

P10 добавляет внутреннюю приемную часть analyze-contact. Она одной транзакцией сохраняет
наблюдение, создает или дополняет предварительный инцидент, повышает `ingress_risk_epoch` и
оставляет принятое наблюдение в `analysis_pending`. Повтор того же source event не повышает
epoch повторно. Корреляция использует явный conversation/call либо одинаковый нормализованный
индикатор внутри namespace; одна близость времени контакты не объединяет.

Публичного HTTP-route пока нет: финализация анализа и разрешение pending-состояния относятся к
P15. Поведение, rollback и восстановление SQLite после restart проверяются общей backend-
командой `pytest`; отдельный интеграционный сценарий находится в
`tests/integration/test_incidents.py`.

### Детерминированная оценка риска

P11 добавляет внутреннюю assessment-операцию. Она получает owner-scoped данные наблюдения и
уже проверенный исход threat lookup, строит явный план применимости text, URL, lookup и visual-
анализа и возвращает неизменяемый результат с версиями правил, причинами, evidence refs и
provenance. Неприменимые ветви не снижают полноту; применимая, но недоступная ветвь дает
partial либо unavailable, а не ложный низкий риск.

В mock-режиме текст проверяется только фиксированными русскоязычными маркерами, а URL —
сравнением нормализованного домена с доверенным каталогом. Сетевых запросов, ML/LLM и скрытого
использования expected label нет. S01 вместе с активным threat evidence дает `critical` и 95
баллов. Публичного route пока нет: запись результата в incident и атомарное снятие pending
относятся к P15. Приемка выполняется общей backend-командой `pytest`; сквозная внутренняя
проверка находится в `tests/integration/test_detection.py`.

### Проверка demo-сессии и согласий

Клиент сначала получает короткоживущую pre-session и CSRF-cookie. Cookie jar нужно
сохранять между запросами; роль и namespace в теле команды не передаются:

```bash
cookie_jar=$(mktemp)
curl -sS -c "$cookie_jar" -b "$cookie_jar" http://127.0.0.1:8000/api/v1/session
csrf_token=$(awk '$6 == "alpha_defense_csrf" {print $7}' "$cookie_jar" | tail -n 1)
curl -sS -c "$cookie_jar" -b "$cookie_jar" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $csrf_token" \
  -H "Idempotency-Key: local-session-1" \
  -d '{"profile_code":"demo-user"}' \
  http://127.0.0.1:8000/api/v1/sessions/demo
```

После старта сессии CSRF-cookie меняется. При изменении согласия клиент передает
версию всего снимка и новый ключ команды:

```bash
csrf_token=$(awk '$6 == "alpha_defense_csrf" {print $7}' "$cookie_jar" | tail -n 1)
curl -sS -c "$cookie_jar" -b "$cookie_jar" -X PATCH \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $csrf_token" \
  -H "Idempotency-Key: grant-analysis-1" \
  -d '{"status":"granted","expected_revision":0}' \
  http://127.0.0.1:8000/api/v1/consents/analyze_communications
```

Это synthetic-вход локального MVP, а не интеграция Alfa ID и не проверка происхождения
звонка. Доступны только allowlisted-профили `demo-user` и `demo-senior`; оба получают
серверную роль `demo_user`.

### Контракт HTTP и web-типы

Из `apps/backend` экспортировать детерминированный контракт только реализованных endpoints:

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen python ../../scripts/export_openapi.py
```

Затем из `apps/web` обновить типы клиента:

```bash
npm run generate:api
```

Повторный экспорт без изменения роутов должен дать те же байты. Файлы OpenAPI и TypeScript
коммитятся вместе с изменением HTTP-контракта.

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
npm test
npm run build
npm run format:check
```

Vitest проверяет форматирование денег/дат, session/consent-состояния onboarding, клавиатурное
управление и frontend import boundaries. Vite проксирует `/api` на локальный backend по адресу
`http://127.0.0.1:8000` в dev/preview-режимах. Запуск приложения:

```bash
npm run dev
# либо после npm run build
npm run preview
```

Открыть `http://127.0.0.1:5173/welcome` для dev или `http://127.0.0.1:4173/welcome` для
preview. Backend должен быть запущен по инструкции выше. Отдельная Playwright-команда
подготовлена для будущей автоматизированной браузерной приемки:

```bash
npm run test:e2e
```

Генерация клиентских типов использует экспорт P04 `contracts/http/openapi.json`:

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
