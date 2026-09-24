# Локальная разработка

Статус: проверено для P01–P13 и A01–A02 2026-09-24. Здесь зафиксированы инструменты и команды;
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
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen python -m pytest
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
observations, incidents, pending-контекста и warning после restart, а также восстановления истекшего
lease входит в интеграционный набор:

```bash
UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv run --frozen python -m pytest tests/integration/test_sqlite_persistence.py
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

### Рекомендации и учебные карточки

P12 добавляет обязательные русскоязычные каталоги рекомендаций и опубликованных учебных
карточек. При запуске loader проверяет JSON Schema, canonical hash, уникальность и взаимные
ссылки, а Markdown принимает только с ограниченным front matter и без raw HTML/MDX. Поэтому
изменение текста требует пересчитать его `content_sha256`; поврежденный контент делает
readiness красной, а не попадает в ответ частично.

После старта demo-сессии опубликованный каталог можно читать с пагинацией:

```bash
curl -sS -c "$cookie_jar" -b "$cookie_jar" \
  'http://127.0.0.1:8000/api/v1/education/cards?locale=ru-RU&limit=20'
curl -sS -c "$cookie_jar" -b "$cookie_jar" \
  'http://127.0.0.1:8000/api/v1/education/cards/general_safety?locale=ru-RU'
```

Неподдерживаемая локаль явно возвращает русский fallback. Неизвестный code или version
возвращает общую карточку безопасности с `fallback_reason`, а не 404 с потерей безопасного
совета. Внутренняя guidance-операция связывает результат P11 с проверенным текстом и передает
`allowed_actions` без изменения; номер поддержки берется только из trusted catalog. Публичный
incident guidance route и UI карточек появятся после сборки соответствующих workflow.

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

Это synthetic-вход локального MVP, а не полноценный вход зарегистрированного пользователя и не проверка происхождения
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
preview. Для обычной работы backend запускается по инструкции выше. Playwright-тест A02
сам запускает отдельный backend с временной SQLite после явных миграций и Vite dev server
на портах 8000/5173. Пользовательская `.env` и рабочая база не используются. Первый
запуск требует браузер той же версии, что и закреплённый Playwright:

```bash
npx playwright install chromium-headless-shell
npm run test:e2e
```

Генерация клиентских типов использует экспорт P04 `contracts/http/openapi.json`:

```bash
npm run generate:api
```

При необходимости Python задаётся через `ALPHA_DEFENSE_PYTHON`; по умолчанию используется
venv из `AGENTS.md`. Тест проходит регистрацию, ошибочный вход, два независимых контекста
одного аккаунта, изоляцию другого, refresh и выход одной сессии. Это не проверка второго
физического устройства или истории, которой пока нет.

## Синтетический текстовый набор M01

Из корня репозитория проверить неизменность 400 JSONL-записей, manifest и группового
разделения, затем выполнить отдельные offline-тесты:

```bash
/Users/Shared/github/MachineLearning/ml_venv/bin/python scripts/ml/build_text_dataset.py
/Users/Shared/github/MachineLearning/ml_venv/bin/python -m pytest -q scripts/ml/tests
/Users/Shared/github/MachineLearning/ml_venv/bin/python -m mypy --strict --explicit-package-bases scripts/ml
```

Источник, критерии разметки, классы, ограничения и SHA-256 находятся в
`datasets/text/`. Сборка без `--write` ничего не переписывает; после осознанной правки
источника `--write` пересоздаёт `messages.v1.jsonl` и `splits.v1.json`, но требует
повторной проверки и обновления документации/hash. Этот набор не импортирует сообщения
из runtime; его train/validation использует M02, test остаётся для M03.

## Офлайн-модель M02

ML-зависимости закреплены отдельно от backend в `scripts/ml/pyproject.toml` и
`scripts/ml/uv.lock`. Только для обучения создаётся изолированное `scripts/ml/.venv` на
Python 3.11 из принятой среды. Это не обновляет общий venv:

```bash
uv lock --project scripts/ml --check
uv sync --project scripts/ml --python /Users/Shared/github/MachineLearning/ml_venv/bin/python --frozen --no-install-project
scripts/ml/.venv/bin/python scripts/ml/train_text_classifier.py
/Users/Shared/github/MachineLearning/ml_venv/bin/python -m pytest -q scripts/ml/tests
/Users/Shared/github/MachineLearning/ml_venv/bin/python -m mypy --config-file scripts/ml/pyproject.toml --explicit-package-bases scripts/ml
```

Обычный запуск обучения сверяет повторно построенные модель, manifest и отчёт побайтово
с `artifacts/text/` и ничего не меняет. `--write` перевыпускает их только намеренно:
после изменения набора, кода или зависимостей потребуется новая версия артефакта и
повторная приемка. Текущий отчёт относится только к validation; test закрыт до M03.
Сериализованный joblib-файл загружается только из доверенного локального checkout;
путь к модели никогда не берётся из HTTP-запроса. Установка ML-пакетов в общий venv
и обучение в пользовательском запросе не требуются.

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
