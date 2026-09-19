# Порядок и протокол реализации «Альфа Защиты»

Версия 1.0 от 2026-09-14. Это рабочий чеклист будущей реализации по [ARCHITECTURE.md](ARCHITECTURE.md), а не отчет о готовом приложении. На момент создания документа все задачи реализации открыты. Текущий запрос создает только этот протокол; запуск разработки определяется отдельным запросом пользователя.

## Навигация

- [Как выбрать и выполнить следующий пункт](#execution-protocol)
- [Качество и определение завершения](#definition-of-done)
- [Этапы и зависимости](#roadmap)
- [P01–P06: фундамент](#stage-foundation)
- [P07–P16: первый полный сценарий S01](#stage-contact)
- [P17–P20: дополнительные источники свидетельств](#stage-context)
- [P21–P24: защищенный перевод](#stage-transfer)
- [P25–P27: полный каталог и интерфейс](#stage-scenarios)
- [P28–P31: инструменты исследования](#stage-research)
- [P32–P36: техническая приемка и демонстрация](#stage-technical)
- [P37–P40: реальные результаты и сдача](#stage-delivery)
- [Отметки по сценариям](#scenario-checklist)
- [Карта API и владельцев](#api-coverage)
- [E01–E10: условные расширения после MVP](#extensions)
- [Журнал выполнения и передача](#work-log)

<a id="execution-protocol"></a>

## 1. Как другому агенту работать с документом

Источники имеют разные обязанности: [TASK.md](../TASK.md) задает требуемый результат; [ARCHITECTURE.md](ARCHITECTURE.md) — устройство и бизнес-контракты; этот документ — порядок работ, границы задач и доказательства завершения. Новый запрос пользователя может менять объем работы; фиксировать его влияние в документах, не подменять архитектуру незаметно. При ссылке на архитектуру использовать якорь раздела: номера строк изменяются.

### 1.1. Выбор следующей задачи

1. Прочитать [AGENTS.md](../AGENTS.md), актуальные TASK/ARCHITECTURE, этот протокол и последнюю запись [журнала](#work-log). Проверить реальные файлы и изменения рабочей копии; прежняя галочка не заменяет проверку наличия результата.
2. Установить разрешенный текущим запросом объем. При запросе «реализуй по плану» последовательно выполнять P01–P40 в пределах доступных условий; не запрашивать новое разрешение на каждый обычный пункт. При запросе только одной фичи выполнять ее и необходимые технические предпосылки в согласованном объеме; не запускать независимые фичи автоматически.
3. Выбрать самый ранний незавершенный P-пункт, все зависимости которого завершены и сохраняют пригодность. Блокированный пункт можно обойти только ради независимой задачи с выполненными зависимостями. E-пункты в этот автоматический выбор не входят.
4. Указать в карточке исполнителя и статус `in_progress`, сохранив чекбокс пустым. Прочитать указанные разделы архитектуры полностью. Уточнять локальные детали реализации в их пределах самостоятельно.
5. Сделать ограниченный результат карточки, пройти ее проверки и общие условия готовности. Изменения соседней фичи допускаются только как необходимая часть контракта; крупный дополнительный объем оформить отдельной задачей.
6. Записать фактические файлы, команды и результаты в журнал, затем изменить чекбокс на `[x]` и статус на `done`. Если готова лишь часть — оставить `[ ]`, описать остаток и точное следующее действие.
7. Перейти к следующему доступному пункту. Не выдавать остановку сессии агента, исчерпание времени или черновик за завершение задачи.

Нельзя выполнять платежный happy path на заглушках «нет сигнала = безопасно». Если зависимость еще не реализована, она либо не используется в текущей законченной подзадаче, либо возвращает предусмотренный unavailable; задача, требующая полноценного поведения этой зависимости, остается открытой.

### 1.2. Статусы и чекбоксы

| Статус | Чекбокс | Значение |
| --- | --- | --- |
| `todo` | `[ ]` | Работа еще не начата; это не утверждение наличия блокера |
| `in_progress` | `[ ]` | Есть назначенный исполнитель и конкретное следующее действие |
| `blocked` | `[ ]` | Невозможно завершить без указанного внешнего условия; в журнале причина, сделанная часть и способ разблокировки |
| `done` | `[x]` | Весь объем и критерии карточки выполнены, есть актуальные доказательства |

В каждой P/E-карточке ровно одна итоговая отметка. Матрица сценариев хранит самостоятельные отметки приемки Sxx; P26 закрывается после всех ее строк, P32 затем проверяет их через окончательный UI. Проценты готовности «на глаз» не использовать.

Если последующее изменение нарушило завершенный контракт, вернуть затронутую карточку в `in_progress` или `blocked`, снять галочку, записать причину и проверить зависимые контрольные точки. Прежние записи журнала сохранять. Не оставлять `done` у сломанного результата.

### 1.3. Гранулярность и параллельная работа

P-пункт — одна законченная способность или ограниченный технический фундамент. Объем задан выходами и приемкой, а не количеством строк кода/часов. Нет требования создавать все перечисленные в архитектуре будущие файлы заранее.

Основной порядок линейный, зависимости позволяют безопасное распараллеливание. Один агент владеет одной изменяемой карточкой; совместные DTO, migrations и bootstrap согласуются до редактирования. Независимые задания можно делегировать с явными путями и выходами. Итоговую галочку ставит агент, проверивший объединенный результат.

Если карточка не помещается в разумный рабочий шаг, добавить подзадачи `Pxx.a`, `Pxx.b` с той же структурой полей, зависимостями и журналом. Исходный Pxx становится контрольной точкой и закрывается только после всех обязательных подзадач. Нумерацию существующих ID не менять; при удалении требования оставить объясненную запись и обновить зависимые пункты, не ставить фиктивную галочку.

<a id="definition-of-done"></a>

## 2. Качество и общий протокол реализации

**Общее условие DONE** применяется к каждой карточке вместе с ее собственной приемкой:

- Результат можно вызвать/использовать указанным способом; нет обязательных веток с `pass`, `NotImplementedError`, произвольным константным ответом или TODO вместо требуемого поведения. Полноценный детерминированный fake-адаптер допустим там, где предусмотрен архитектурой.
- Соблюдены [слои и импорты](ARCHITECTURE.md#dependency-rule), [форматы](ARCHITECTURE.md#contracts) и [правила файлов](ARCHITECTURE.md#naming). У domain нет I/O, фреймворков и глобальных часов; application не зависит от конкретного SDK; межфичевую координацию выполняют workflows.
- Для сохраняемых сущностей есть mapper, repository, миграция и проверка инвариантов хранения. Для команды — ownership/namespace, валидация, разрешенные переходы, идемпотентность и ошибки в применимой части. Внешний сайд-эффект не выполняется внутри SQL-транзакции.
- При появлении HTTP-контракта есть transport-схемы, корректные коды/Problem Details, актуальный экспорт OpenAPI, сгенерированные типы web и валидные примеры. Нереализованный endpoint не публикуется как работающий stub.
- В UI предусмотрены требуемые ready/loading/error/empty и бизнес-состояния, русский текст и доступные действия. Backend остается источником риска и финансового статуса.
- Проверки подтверждают важное поведение и отказ, а не повторяют строки реализации. Для чистого форматирования/простого обратимого текста отдельные тесты не добавлять без причины. Выполнять тесты карточки, необходимые общие проверки и затронутую регрессию; весь набор запускать на контрольных точках или при широком изменении.
- Отрицательная проверка подтверждает ожидаемый отказ, а не случайное падение. Незавершенный прогон, skipped обязательный тест, отсутствующий браузер и «должно работать» не считаются PASS.
- Проверены собственные изменения и `git diff --check`; сохранены пользовательские изменения. Обновлены затронутые документы и [журнал](#work-log). Commit hash указывать, если commit уже существует; создание commit/push не является условием галочки.
- После каждой завершенной P-карточки обновлен [конспект для защиты](presentation/defense-guide.md): добавленная способность объяснена на уровне устройства, гарантий и ограничений без низкоуровневого перечня функций. В конспект не переносятся планы как свершившиеся факты.
- Остатки, способные нарушить приемку карточки, отсутствуют. Необязательные улучшения можно вынести в отдельный backlog, с объяснением почему они не нужны для ее завершения.

**Среда:** Python по умолчанию — `/Users/Shared/github/MachineLearning/ml_venv/bin/python`. Не выполнять разрушительное синхронизирование общего venv. Node-зависимости устанавливать в `apps/web/`. В P01 зафиксировать точные совместимые версии и проверенные команды; этот документ не утверждает, что они уже установлены.

**Уровень продукта:** завершенный воспроизводимый локальный web-прототип с реальными внутренними правилами и сохранением состояния, synthetic данными и fake провайдерами. Реальные переводы, доступ к коммуникациям устройства, платные интеграции, обучение моделей и промышленная инфраструктура не входят в P01–P40.

**Уровни завершения:** P35 — технический прототип принят; P38 — получен фактический UX-отчет; P40 — выполнен весь результат TASK, включая презентацию. Ни одна из этих отметок не доказывает снижение реального мошенничества на 30–50%.

<a id="roadmap"></a>

## 3. Этапы и маршрут реализации

| Пакет | Пункты | Выход |
| --- | --- | --- |
| Фундамент | P01–P06 | Среда, слои, сохранение, HTTP, сессия, web-shell |
| Первый сценарий | P07–P16 | SMS → оценка → предупреждение/объяснение → действующее ограничение demo-ресурса |
| Контекст | P17–P20 | Подлинность звонка в демо, screenshot, история и сеть |
| Перевод | P21–P24 | Проверка → gate/решение → исполнение → фактический исход fake bank |
| Каталог | P25–P27 | 15 сценариев, обязательные варианты, все продуктовые ветки UI |
| Исследовательский инструмент | P28–P31 | Протокол, сбор событий, анкета, проверенный расчет и экспорт |
| Техническая готовность | P32–P36 | Полный прогон, эксплуатация, доступность, комплект демонстрации |
| Сдача TASK | P37–P40 | Реальные UX-сессии, выводы, презентация, итоговая приемка |

Это детализация [§18 архитектуры](ARCHITECTURE.md#implementation). Минимальный реестр, content, outbox и namespace нужны уже для первого S01; история/behavior/network нужны до законченного transfer check. Поэтому часть компонентов «всех сценариев» намеренно реализуется раньше их общей приемки. Структура слоев и контракты архитектуры не меняются.

Пути в карточках: `B = apps/backend/src/alpha_defense/`, `W = apps/web/src/`; префиксы относятся только к путям внутри кода в карточках. Документальные ссылки ведут к реальным разделам. Имена будущих файлов показаны как спецификация, без неработающих ссылок на еще несуществующие файлы.

<a id="stage-foundation"></a>

## 4. Фундамент

<a id="p01"></a>

### P01. Зафиксировать инструменты, зависимости и команды разработки

- [x] Выполнено и проверено. **Статус:** done. **Исполнитель:** Codex.

**Зависимости:** нет.

**Архитектура:** [§2.1: стек](ARCHITECTURE.md#stack); [§3.2: форматирование](ARCHITECTURE.md#naming); [§18.2: проверки](ARCHITECTURE.md#verification).

**Где и какой результат:** apps/backend/pyproject.toml, uv.lock; apps/web/package.json, package-lock.json; ops/runbooks/development.md.

**Реализовать:** Проверить существующие Python/Node инструменты; выбрать совместимые версии из архитектурного стека. Настроить packaging, lint/typecheck/test-команды и воспроизводимое разрешение зависимостей. Записать команды, рабочие каталоги и переменные для запуска проверок через принятый venv.

**Граница объема:** Только нужные MVP dev/runtime зависимости; без ML-весов, внешних credentials, нового venv по умолчанию и контейнерной инфраструктуры заранее.

**Приемка и качество:** Manifests/locks согласованы; команды доступны и их реальные версии записаны. Команда, которой пока не на чем работать, явно отмечена как подготовленная, без ложного «тесты прошли»; минимальный lint/typecheck конфигурации действительно выполнен.

**Запись выполнения:** [2026-09-15-P01-01](#log-2026-09-15-p01-01).

<a id="p02"></a>

### P02. Создать общие типы, ошибки и проверки границ слоев

- [x] Выполнено и проверено. **Статус:** done. **Исполнитель:** Codex.

**Зависимости:** [P01](#p01).

**Архитектура:** [§2.2: зависимости](ARCHITECTURE.md#dependency-rule); [§4.11: технические ветки](ARCHITECTURE.md#technical-branches); [§5: контракты](ARCHITECTURE.md#contracts).

**Где и какой результат:** B/domain/shared/, B/application/shared/, B/application/ports/; backend tests/unit/ и tests/architecture/.

**Реализовать:** Реализовать ID, Money, Severity, Provenance, ActorContext, Clock/IdGenerator, pagination и прикладные ошибки. Включить проверяемые запреты импортов для backend и правило app→pages→features→shared для будущего web-кода.

**Граница объема:** Только реально общие типы; без BaseService, общего CRUD и моделей всех будущих фичей. Domain-фичи не получают взаимных импортов.

**Приемка и качество:** Money отклоняет неверные/дробные значения; время/ID инъецируются. Временная запрещенная зависимость обнаруживается проверкой, затем удаляется; валидное дерево проходит. Зависимости Python не проникают из infrastructure в application/domain.

**Запись выполнения:** [2026-09-15-P02-01](#log-2026-09-15-p02-01).

<a id="p03"></a>

### P03. Реализовать хранилище, UnitOfWork и технические гарантии команд

- [x] Выполнено и проверено. **Статус:** done. **Исполнитель:** Codex.

**Зависимости:** [P02](#p02).

**Архитектура:** [§7.3: повторы и гонки](ARCHITECTURE.md#idempotency); [§7.4: события](ARCHITECTURE.md#internal-events); [§9: порты](ARCHITECTURE.md#ports); [§14: БД](ARCHITECTURE.md#persistence).

**Где и какой результат:** B/application/ports/{repositories,unit_of_work,events}.py; B/infrastructure/persistence/, runtime/, observability/; apps/backend/migrations/.

**Реализовать:** Сделать SQLite/SQLAlchemy и in-memory UoW, начальные миграции idempotency/audit/outbox, CAS и конкретные инфраструктурные операции. Сохранять состояние команды и hash; добавить durable dispatch/recovery механизм, в который фичи позже регистрируют обработчики.

**Граница объема:** Здесь только технические таблицы и порты; бизнес-таблицы добавляются их владельцами. Outbox не заменяет provider idempotency и не объявляется exactly-once.

**Приемка и качество:** Откат не оставляет частичной локальной записи; тот же ключ/тело воспроизводит ресурс, другое тело дает конфликт; CAS допускает одного победителя. Аудит/outbox записываются атомарно, переживают restart; in-memory и SQL проходят одинаковые смысловые contract cases.

**Запись выполнения:** [2026-09-15-P03-01](#log-2026-09-15-p03-01).

<a id="p04"></a>

### P04. Собрать bootstrap, базовый HTTP и генерацию контрактов

- [x] Выполнено и проверено. **Статус:** done. **Исполнитель:** Codex.

**Зависимости:** [P03](#p03).

**Архитектура:** [§4.11: сборка](ARCHITECTURE.md#technical-branches); [§8: API](ARCHITECTURE.md#api); [§8.1: ошибки](ARCHITECTURE.md#http-errors); [§11: конфигурация](ARCHITECTURE.md#configuration).

**Где и какой результат:** B/bootstrap/, B/transport/http/v1/; contracts/http/, contracts/examples/; ops/local/.env.example; scripts/ для экспорта контрактов.

**Реализовать:** Создать settings/container/ASGI app, общие request/response mapping, Problem Details, request_id, ограничения запросов и health/live. Подключить SQLite и подготовленные guards. Экспортировать OpenAPI детерминированно и запустить генерацию web-типов для уже доступных API.

**Граница объема:** Только реально реализованные endpoints. Readiness обязана отклонять отсутствие обязательного catalog; окончательный 200 для полного MVP проверяется после P07. Не делать ready всегда зеленым ради раннего запуска.

**Приемка и качество:** Приложение стартует с валидной конфигурацией; плохой режим/секрет/БД дает ожидаемый отказ. HTTP-ошибки валидны по схеме, внутренние исключения/секреты не выходят наружу. Повтор экспорта без изменения API не меняет контракт.

**Запись выполнения:** [2026-09-17-P04-01](#log-2026-09-17-p04-01).

<a id="p05"></a>

### P05. Реализовать demo-сессии, namespace, роли и согласия

- [x] Выполнено и проверено. **Статус:** done. **Исполнитель:** Codex.

**Зависимости:** [P04](#p04).

**Архитектура:** [§4.1: identity](ARCHITECTURE.md#feature-identity); [§5.2: ActorContext](ARCHITECTURE.md#data-models); [§7.3: namespace](ARCHITECTURE.md#idempotency); [§8: session API](ARCHITECTURE.md#api).

**Где и какой результат:** B/domain/identity/, application/identity/, infrastructure/identity/mock/; session/consent transport и repositories.

**Реализовать:** Сделать pre-session token, start_session, session view, manual namespace, серверную роль, consent revision и update_consent. Создать ownership/namespace/CSRF dependencies, общие для будущих routes.

**Граница объема:** Аутентификация synthetic; Alfa ID и доказательство звонка не подменяются этой сессией. Не просить доступ к реальным SMS ради демо.

**Приемка и качество:** POST /sessions/demo, GET /session, PATCH /consents/{scope} сохраняют/восстанавливают состояние. Повтор не создает лишнюю сессию; чужой resource/namespace не раскрывается; клиент не расширяет роль. Отзыв scope меняет revision; отказ от research не выключает основную защиту.

**Запись выполнения:** [2026-09-18-P05-01](#log-2026-09-18-p05-01).

<a id="p06"></a>

### P06. Подготовить web-shell, API-клиент и onboarding

- [x] Выполнено и проверено. **Статус:** done. **Исполнитель:** Codex.

**Зависимости:** [P05](#p05).

**Архитектура:** [§10: web-слои и фичи](ARCHITECTURE.md#frontend); [§10.3: UX](ARCHITECTURE.md#ux-contract); [§5: форматы](ARCHITECTURE.md#contracts).

**Где и какой результат:** W/app/, pages/, shared/api/, shared/formatting/, shared/i18n/, shared/styles/, shared/ui/; features/onboarding/.

**Реализовать:** Собрать router/providers/error boundary/query cache, fetch-клиент с CSRF/idempotency и generated types. Добавить русское форматирование денег/дат, tokens и onboarding c реальной backend-сессией/согласиями.

**Граница объема:** Страницы будущих фичей не выдавать за готовые. Общие компоненты делать по текущей необходимости; бизнес-политики в UI не появляются.

**Приемка и качество:** Сессия восстанавливается после refresh; согласия и отказ отражают backend. Видим режим «Демонстрация», ошибки не стирают ввод. Проверены формат денег/UTC→Moscow, базовая клавиатура и отсутствие импортов между frontend-фичами.

**Запись выполнения:** [2026-09-19-P06-01](#log-2026-09-19-p06-01).

<a id="stage-contact"></a>

## 5. Первый полный контактный сценарий S01

<a id="p07"></a>

### P07. Создать схемы и загрузку версионированных данных

- [x] Выполнено и проверено. **Статус:** done. **Исполнитель:** Codex.

**Зависимости:** [P04](#p04).

**Архитектура:** [§3.1: каталоги](ARCHITECTURE.md#supporting-directories); [§6.1: PolicySnapshot](ARCHITECTURE.md#risk-policy); [§12.1: fixtures](ARCHITECTURE.md#fixture-format).

**Где и какой результат:** contracts/fixtures/, fixtures/communications/, fixtures/threats/; content/policies/, trusted_entities/; B/infrastructure/content/.

**Реализовать:** Определить JSON Schema для policy/trusted entities и общих fixture-конвертов; сделать безопасные loaders и минимальный synthetic набор для S01. Версии/hash/refs валидируются; данные политики маппятся в plain snapshot. Подготовить validator CLI.

**Граница объема:** Схемы новых payload расширяются при появлении их фичей. В этом пункте не нужен полный scenario runner и весь каталог; нет фиктивного expected→assessment присваивания.

**Приемка и качество:** Поврежденный JSON, enum, ссылка за FIXTURE_ROOT, неизвестная версия и неверный hash отклоняются. Valid S01 data загружается, обязательный catalog участвует в readiness. Domain не читает файлы.

**Запись выполнения:** [2026-09-19-P07-01](#log-2026-09-19-p07-01).

<a id="p08"></a>

### P08. Реализовать реестр угроз и атомарное обновление снимков

- [ ] Выполнено и проверено. **Статус:** in_progress. **Исполнитель:** Codex.

**Зависимости:** [P07](#p07), [P05](#p05).

**Архитектура:** [§4.7: threats](ARCHITECTURE.md#feature-threats); [§9: ThreatFeedPort](ARCHITECTURE.md#ports); [§14: хранение](ARCHITECTURE.md#persistence).

**Где и какой результат:** B/domain/threats/, application/threats/, infrastructure/threat_intel/fixtures/, persistence/; fixtures/threats/; scripts/seed и refresh.

**Реализовать:** Сделать typed indicators, записи active/revoked/expired/unverified, RegistrySnapshot, lookup_indicators, refresh_registry, get_registry_status. Ввести source/expiry/normalization version и атомарную публикацию только валидного снимка.

**Граница объема:** Файловый feed; публичного административного blacklist API и реального МВД/РКН нет.

**Приемка и качество:** Active exact match найден; revoked/expired не считается актуальной угрозой. No match и unavailable различимы. Плохой пакет не заменяет последний валидный, повтор обновления не создает дубликаты; смена версии видна потребителям контекста.

**Запись выполнения:** [2026-09-19-P08-01](#log-2026-09-19-p08-01).

<a id="p09"></a>

### P09. Реализовать наблюдения и нормализацию коммуникаций

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P05](#p05), [P07](#p07).

**Архитектура:** [§4.2: communications](ARCHITECTURE.md#feature-communications); [§5.2: Observation](ARCHITECTURE.md#data-models); [§5.3: входные лимиты](ARCHITECTURE.md#input-limits).

**Где и какой результат:** B/domain/communications/, application/communications/, persistence/; transport schemas observations; contracts/fixtures/observation schema.

**Реализовать:** Сделать tagged union SMS/chat/call_transcript/web_resource, неизменяемое наблюдение, раздельный content storage и source event ID. Реализовать нормализацию phone/URL/domain, conversation/call/sequence и типизированные ошибки.

**Граница объема:** Готовая модель и прикладные операции приема; POST /observations публикуется только вместе с полным workflow P15. Screenshot хранится ссылкой до P18, speech-to-text не реализуется.

**Приемка и качество:** Варианты payload/размеры/времена проверяются; raw не перезаписывается нормализованным. Повтор одного source event в namespace узнается, другой run независим. Неверный телефон не маскируется валидным; URL сохраняет значимые path/query.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p10"></a>

### P10. Создать инциденты, корреляцию и немедленную инвалидизацию контекста

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P09](#p09).

**Архитектура:** [§4.4: incidents](ARCHITECTURE.md#feature-incidents); [§7.1: прием](ARCHITECTURE.md#flow-contact); [§7.3: freshness](ARCHITECTURE.md#idempotency).

**Где и какой результат:** B/domain/incidents/, application/incidents/, application/workflows/analyze_contact.py (часть атомарного приема); incident repositories.

**Реализовать:** Сделать Incident, context_version, timeline read model, preliminary correlation и resolution. Атомарно сохранять observation/preliminary incident, увеличивать namespace ingress_risk_epoch и analysis_pending. Workflow связывает feature-use cases через DTO.

**Граница объема:** Приемная часть workflow; финализация анализа и публичный intake endpoint — P15. Временная близость без дополнительной связи не склеивает контакты в одну атаку.

**Приемка и качество:** Принятый контакт виден как pending до оценки и делает прежний контекст непригодным; rollback не оставляет разорванную пару observation/incident. Чужие namespace не связываются; history оценок не теряется; false_positive_reported не меняет платежный gate.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p11"></a>

### P11. Реализовать оценку риска и детерминированный text/URL-анализ

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P08](#p08), [P09](#p09).

**Архитектура:** [§4.3: detection](ARCHITECTURE.md#feature-detection); [§5.2: AnalysisResult](ARCHITECTURE.md#data-models); [§6.1: политика](ARCHITECTURE.md#risk-policy).

**Где и какой результат:** B/domain/detection/, application/detection/, application/ports/analysis.py, infrastructure/analysis/mock/; content/policies/demo-risk-v1.json.

**Реализовать:** Сделать Signal/Assessment, analysis plan/applicability/completeness и domain risk policy. Реализовать TextAnalysisPort и URL-часть ResourceAnalysisPort: признаки текста, trusted/похожие домены, ссылки на threat evidence, объяснимые reason codes.

**Граница объема:** Полный каталог и алгоритм v1 из архитектуры, без обучаемой модели/LLM. CV, behavior и network подключаются отдельными P18–P20; неподключенный применимый анализ не считается безопасным.

**Приемка и качество:** Проверены границы severity, поглощение комбинаций/дубликатов, partial/unavailable/not_applicable и отсутствие пригодных анализаторов. На одинаковом входе/версиях результат одинаков; scenario_id/expected не используются. Изменение содержания меняет результат при тех же scenario metadata.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p12"></a>

### P12. Реализовать рекомендации, учебные карточки и structured assistant

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P07](#p07), [P11](#p11).

**Архитектура:** [§4.8: education](ARCHITECTURE.md#feature-education); [§3.1: content](ARCHITECTURE.md#supporting-directories); [§8: guidance API](ARCHITECTURE.md#api).

**Где и какой результат:** B/domain/education/, application/education/, infrastructure/content/; content/recommendations/, education/, trusted_entities/.

**Реализовать:** Сделать ContentCatalogPort, get_guidance/list_cards/get_card, русские версии объяснений и карточек для начальных схем; расширить content schema. Guidance связывает risk/reason codes с контентом и server allowed actions.

**Граница объема:** Ассистент — структурированное представление анализа; нет свободного чата, генерации команд и endpoint из текста.

**Приемка и качество:** Карточки валидируются и читаются через education API. Нет raw HTML/MDX; неподдерживаемый code/locale имеет предсказуемый fallback без выдуманной причины. Контакт помощи берется из trusted catalog, не из подозрительного сообщения.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p13"></a>

### P13. Реализовать предупреждения, доставку и подтверждение показа

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P10](#p10), [P11](#p11), [P12](#p12).

**Архитектура:** [§4.5: protection](ARCHITECTURE.md#feature-protection); [§6.2: warning states](ARCHITECTURE.md#lifecycle); [§7.4: события](ARCHITECTURE.md#internal-events).

**Где и какой результат:** B/domain/protection/warning.py, warning_policy.py; application/protection/; infrastructure/notifications/in_app/; warning repositories/routes.

**Реализовать:** Сделать issue_warning, delivery через durable outbox, presentation/response endpoints, immutable связь с assessment и server AllowedAction. Разделить dispatched, presented, response.

**Граница объема:** Внутриприложенческое предупреждение; внешние notification adapters пока не включаются. Работа не зависит от research consent.

**Приемка и качество:** HTTP 200 доставки не делает presented. На уровне backend тестовая presentation-команда создает ровно одну запись impression; проверены ownership и повтор. Ack/dismiss не исполняет перевод и не снимает gate. Сбой доставки отражается и восстанавливается с тем же warning_id. Фактический момент UI-render проверяется в P16 и не является преждевременным условием P13.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p14"></a>

### P14. Реализовать локальное ограничение ресурса и статус заявки

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P08](#p08), [P10](#p10), [P13](#p13).

**Архитектура:** [§4.5: ResourceGate](ARCHITECTURE.md#feature-protection); [§9: ResourceEnforcementPort](ARCHITECTURE.md#ports); [§8: resource API](ARCHITECTURE.md#api).

**Где и какой результат:** B/domain/protection/resource_gate.py, protection_action.py; application/protection/; infrastructure/resources/mock/; resource gates/actions persistence.

**Реализовать:** Сделать request_resource_action/get_action/check_resource_navigation, fake restrict/report и сохраненный gate на owner/namespace/нормализованную цель. Связать allowed actions с assessment и корректным scope/effect.

**Граница объема:** Навигация только на подготовленный безопасный demo-preview. Сетевой fetch или глобальное закрытие сайта не реализуются. Preview может быть статической безопасной заглушкой страницы; ограничение и результат работают на backend.

**Приемка и качество:** После confirmed restrict backend действительно запрещает demo-переход; frontend state/reset чужого run не снимает запрет. Report_received не отображается как resource_restricted. Повтор команды идемпотентен; неподдерживаемая мера имеет явный исход.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p15"></a>

### P15. Завершить сквозной analyze_contact и контактный API

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P08](#p08), [P10](#p10), [P11](#p11), [P12](#p12), [P13](#p13), [P14](#p14).

**Архитектура:** [§7.1: полный поток](ARCHITECTURE.md#flow-contact); [§7.3: consistency](ARCHITECTURE.md#idempotency); [§8: API](ARCHITECTURE.md#api); [§15: deadline/recovery](ARCHITECTURE.md#reliability).

**Где и какой результат:** B/application/workflows/analyze_contact.py; transport observation/assessment/incident/guidance routes; runtime recovery handlers.

**Реализовать:** Собрать атомарный прием, чтение snapshots, параллельные применимые анализаторы под одним deadline, сохранение immutable assessment/warning/outbox и разрешение pending. Подключить POST observations, reassessments, GET incidents/assessments/guidance и resolution.

**Граница объема:** Синхронный workflow с persisted degraded результатом; не вводить job API/брокер. Недостающие схемы/типизация дополняются по новым endpoints.

**Приемка и качество:** S01 от HTTP-входа дает receipt, объяснимую оценку и warning. Timeout возвращает degraded, не low; recheck создает новую оценку. Crash после приема восстанавливается без дублей; старый check/context не оживает после разрешения pending.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p16"></a>

### P16. Собрать первый полный пользовательский поток S01

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P06](#p06), [P15](#p15).

**Архитектура:** [§10: UI фичи](ARCHITECTURE.md#frontend); [§10.3: предупреждение](ARCHITECTURE.md#ux-contract); [§12: S01](ARCHITECTURE.md#scenarios).

**Где и какой результат:** W/features/communication-inbox/, incident-details/, risk-warning/, resource-check/, assistant/, education/; соответствующие pages.

**Реализовать:** Связать ввод SMS, реальный receipt, incident timeline, причины, warning, server actions, structured guidance и education. Сделать demo-переход через resource navigation API с наблюдаемым отказом после ограничения.

**Граница объема:** Один полностью законченный S01; остальные каналы/сценарии добавляются позже. Не выдавать отсутствие frontend runner за отсутствие работающего backend-потока.

**Приемка и качество:** Браузерный smoke/E2E вызывает backend и наблюдает ресурсный запрет. Warning presented возникает после render; Escape безопасен, опасный текст экранируется. Loading/error/degraded и режим demo видимы; screenshot/trace проверки сохранены как техническое evidence.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="stage-context"></a>

## 6. Дополнительные источники свидетельств

<a id="p17"></a>

### P17. Реализовать проверку конкретного звонка через mock proof

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P15](#p15).

**Архитектура:** [§4.1: CallVerification](ARCHITECTURE.md#feature-identity); [§6.2: состояния proof](ARCHITECTURE.md#lifecycle); [§9: CallAttestationPort](ARCHITECTURE.md#ports).

**Где и какой результат:** B/domain/identity/call_verification.py; application/identity/verify_call.py; infrastructure/identity/mock/; fixtures/identities/; call verification route.

**Реализовать:** Реализовать mock proof с привязкой call/user/session/nonce/issuer/expiry, verified/unverified/unavailable/expired и версионированное свидетельство в контексте анализа.

**Граница объема:** Никакого реального Alfa ID/оператора; подтвержденный login или caller number не является доказательством звонка. Случай отсутствия transcript остается явным отсутствием данных.

**Приемка и качество:** Подходящий proof проходит; чужой/повторно использованный/истекший отклоняется по назначению. Provider unavailable не превращается в verified или обвинение. Verified нейтрального звонка не обнуляет риск опасного содержания. Здесь воспроизводятся контактная часть S02 и проверки proof из S07/S13; полный S02 с переводом принимается после P23 в P26.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p18"></a>

### P18. Добавить безопасное хранение изображений и CV-мок

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P15](#p15), [P07](#p07).

**Архитектура:** [§5.3: media](ARCHITECTURE.md#input-limits); [§9: MediaStore/ResourceAnalysis](ARCHITECTURE.md#ports); [§11: изоляция](ARCHITECTURE.md#configuration).

**Где и какой результат:** B/infrastructure/media/local/, analysis/mock/; media port/transport; fixtures/screenshots/ и metadata; contracts/fixtures/.

**Реализовать:** Сделать put/get/delete owner-scoped media, MIME+decode/hash/размеры, screenshot reference и mock CV lookup по hash. Присоединить image evidence к ResourceAnalysisPort и assessment.

**Граница объема:** PNG/WebP подготовленных страниц; внешний сайт не открывается и не считается проанализированным по одному URL. Нет реальной CV-модели и remote renderer.

**Приемка и качество:** S06 возвращает ожидаемый сигнал с provenance mock. Неверный формат, oversize, поддельный MIME, чужой media_id и path traversal отклоняются. Незнакомое изображение дает явно определенный недостаточный результат, а не выдуманную уверенность.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p19"></a>

### P19. Построить синтетическую историю и поведенческие признаки

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P05](#p05), [P07](#p07), [P11](#p11).

**Архитектура:** [§4.3: behavior](ARCHITECTURE.md#feature-detection); [§5.2: BehaviorProfile](ARCHITECTURE.md#data-models); [§6.1: история/пороги](ARCHITECTURE.md#risk-policy); [§9: history port](ARCHITECTURE.md#ports).

**Где и какой результат:** B/application/detection/, ports/bank.py, infrastructure/bank/mock/, analysis/behavior/; fixtures/profiles/; history/profile repositories.

**Реализовать:** История через TransactionHistoryPort: синтетические прежние операции → immutable snapshot → profile с as_of/sample_size/feature_version. Вычислить новизну получателя и аномальную сумму по правилам v1.

**Граница объема:** Только завершенные прежние RUB-операции в окне архитектуры; текущий перевод не добавляется в признаки. Нет обучения или магических вручную заданных summary.

**Приемка и качество:** Порог/минимальная история проверены на границах; consent revoked и малая выборка дают явную недостаточность. Snapshot/profile воспроизводимы, меняют контекст при обновлении; S09/S11/S15 получают соответствующие признаки.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p20"></a>

### P20. Реализовать небольшой граф угроз и network-признаки

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P08](#p08), [P11](#p11).

**Архитектура:** [§4.7: сетевой контекст](ARCHITECTURE.md#feature-threats); [§9: NetworkAnalysisPort](ARCHITECTURE.md#ports); [§12.1: graph fixtures](ARCHITECTURE.md#fixture-format).

**Где и какой результат:** B/infrastructure/analysis/network/; network DTO/port; fixtures/network/; graph schema и snapshot repository.

**Реализовать:** Загружать валидный typed graph snapshot с provenance/expiry; возвращать ограниченные готовые связи индикаторов и evidence. Встроить применимость/недоступность в analysis plan.

**Граница объема:** Небольшой synthetic graph для MVP; никакого Kafka/Spark/графовой СУБД или прохода всей истории на запросе.

**Приемка и качество:** S10 находит заданную активную связь; общий IP без достаточного основания не доказывает сеть. Просроченный/невалидный snapshot не дает актуальный сигнал; unavailable отличим от no_match, версии попадают в evaluation context.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="stage-transfer"></a>

## 7. Защищенный перевод

<a id="p21"></a>

### P21. Создать модель перевода и сохраняемый симулятор банка

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P05](#p05), [P03](#p03).

**Архитектура:** [§4.6: transfers](ARCHITECTURE.md#feature-transfers); [§5.2: intent/execution/operation](ARCHITECTURE.md#data-models); [§6.2: состояния](ARCHITECTURE.md#lifecycle); [§9: bank port](ARCHITECTURE.md#ports).

**Где и какой результат:** B/domain/transfers/, application/transfers/create_transfer.py; infrastructure/bank/mock/; transfer/operation/gate repositories и migrations.

**Реализовать:** Сделать Intent revision/fingerprint/lifecycle, Execution и отдельный BankOperation, создать/редактировать/читать draft. Реализовать fake ledger, capabilities, provider key, get_request_status/get_operation_status и программируемые исходы accepted/settled/declined/unknown.

**Граница объема:** Модель/хранилище и draft API; подтверждение отправки не публиковать до P23. Demo hold — немонетарный gate; live reserve/release не эмулируется словом «удержание средств».

**Приемка и качество:** Изменение суммы/валюты/получателя меняет revision/fingerprint. Fake bank сохраняется после restart, повтор provider key не создает второй эффект. Accepted и settled независимы; outcome declined после accepted возможен. Клиент не меняет lifecycle напрямую.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p22"></a>

### P22. Реализовать TransferCheck и полный evaluation_context

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P15](#p15), [P17](#p17), [P19](#p19), [P20](#p20), [P21](#p21).

**Архитектура:** [§4.6: check](ARCHITECTURE.md#feature-transfers); [§5.2: evaluation_context](ARCHITECTURE.md#data-models); [§7.2: review_transfer](ARCHITECTURE.md#flow-transfer); [§7.3: stale checks](ARCHITECTURE.md#idempotency).

**Где и какой результат:** B/domain/transfers/decision_policy.py, transfer_check.py; application/transfers/check_transfer.py; application/workflows/review_transfer.py (решение); transport check schemas.

**Реализовать:** Создавать отдельную transfer assessment из согласованных snapshots и immutable check. Связать fingerprint/revision, ingress epoch, incident, history/registry/graph/consent/proof/policy и expiry; вычислять currentness. Сохранять allow/confirm/hold/deny и допустимые действия, актуализировать demo gate. При deny переводить intent в rejected без запроса submit.

**Граница объема:** Здесь завершены оценка, решение и модель перехода gate. Публичный check endpoint с подтверждаемым hold execution подключается в P23 вместе с исполнителем; не публиковать частично действующий маршрут. Все применимые context-порты функциональны или явно unavailable.

**Приемка и качество:** S09 high→hold, S11 low→allow, S15 medium→confirm; critical→deny дает intent rejected и ноль вызовов bank submit. Отзыв scope, новая registry/profile/policy/proof, expired check и принятый pending контакт делают старое разрешение непригодным. Gate cleared/blocked/superseded следует версии; жалоба об ошибке не снимает gate.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p23"></a>

### P23. Реализовать submit/cancel/hold, неопределенный исход и reconciliation

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P22](#p22), [P13](#p13).

**Архитектура:** [§6.2: три оси состояния](ARCHITECTURE.md#lifecycle); [§7.2: execute_protection](ARCHITECTURE.md#flow-transfer); [§7.3: гонки](ARCHITECTURE.md#idempotency); [§8.1: unknown](ARCHITECTURE.md#http-errors).

**Где и какой результат:** B/application/transfers/{confirm_transfer,cancel_transfer,reconcile_execution}.py; workflows/execute_protection.py и финализация review_transfer; runtime recovery; checks/executions/operations transport.

**Реализовать:** Для submit атомарно проверить актуальность и зарезервировать выполнение, вызвать fake bank вне UoW, сохранить подтверждение; при неизвестном исходе сверять прежний key/ref. Раздельно реализовать local draft cancel, provider cancel и hold с их условиями. Восстанавливать outbox/active/unknown после restart.

**Граница объема:** Один логический эффект при двойной отправке; это требует HTTP key, uniqueness/CAS и provider key одновременно. Cancel не требует свежего risk check для локального draft.

**Приемка и качество:** Обязательны разные keys из двух вкладок, concurrent submit/cancel, устаревшая revision, crash до/после bank call, timeout после accepted, S15.declined_after_accepted. Medium submit без acknowledgment текущего warning/check отклоняется; acknowledgment от старого check, другого warning или owner также не дает разрешение. Confirmed submit не означает completed; только settled завершает intent. При blocked gate/pending анализе локальная отмена разрешена.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p24"></a>

### P24. Собрать интерфейс защищенного перевода

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P16](#p16), [P23](#p23).

**Архитектура:** [§10: protected-transfer](ARCHITECTURE.md#frontend); [§8.1: polling](ARCHITECTURE.md#http-errors); [§10.3: честный статус](ARCHITECTURE.md#ux-contract).

**Где и какой результат:** W/features/protected-transfer/, risk-warning/ через pages; routes /transfers/new и /transfers/:id.

**Реализовать:** Сделать форму Money/получателя, draft editing, check, дополнительное подтверждение medium, безопасные действия hold/deny/cancel и отображение execution/BankOperation. Реализовать ограниченный polling и восстановление GET.

**Граница объема:** Антифрод-политика не копируется в TypeScript. Клиент блокирует двойной клик для UX, но серверная защита остается обязательной.

**Приемка и качество:** Контакт → попытка перевода → объясненная остановка проходит через backend. Refresh/reconnect не отправляет деньги повторно; unknown/pending не показывает успех, accepted не completed. При смене реквизитов нужен новый check; polling через 30 s переходит к ручному обновлению.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="stage-scenarios"></a>

## 8. Каталог сценариев и полный интерфейс

<a id="p25"></a>

### P25. Реализовать сценарный движок, reset и восстановление run

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P23](#p23), [P17](#p17), [P18](#p18), [P20](#p20).

**Архитектура:** [§4.10: scenarios](ARCHITECTURE.md#feature-scenarios); [§12.1: формат шагов](ARCHITECTURE.md#fixture-format); [§7.3: namespace](ARCHITECTURE.md#idempotency); [§8: scenario API](ARCHITECTURE.md#api).

**Где и какой результат:** B/application/scenarios/, ports/scenarios.py, infrastructure/content/; ScenarioRun persistence; scenario routes и fixture validators.

**Реализовать:** Сделать list/start/advance/reset, server run namespace, fixed clock/seed и controlled provider behavior. Выполнять только декларативные разрешенные steps через те же workflows, что ручные действия; отдавать read model для GET восстановления.

**Граница объема:** Expected остается только у test harness; input/outputs анализатора не получают scenario_id или ground truth. Fake provider behavior отделен от окончательного verdict. Здесь выполняются шаги защитного потока; handler submit_feedback подключается в P29–P30. До этого fixtures P26 не требуют исследовательского шага, а его неподключенный handler не возвращает фиктивный успех.

**Приемка и качество:** Недопустимый/повторный шаг не выполняется дважды; чужой run недоступен. Повтор seed воспроизводит правила без требования тех же UUID. Reset создает новый namespace, не склеивает source IDs и не удаляет study trials; GET не переисполняет команды.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p26"></a>

### P26. Наполнить и проверить S01–S15 и обязательные варианты

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P25](#p25), [P16](#p16), [P19](#p19).

**Архитектура:** [§12: каталог](ARCHITECTURE.md#scenarios); [§12.1: fixtures](ARCHITECTURE.md#fixture-format); [§18.2: scenario tests](ARCHITECTURE.md#verification).

**Где и какой результат:** fixtures/scenarios/, communications/, identities/, profiles/, threats/, network/, screenshots/; backend scenario harness и contracts/fixtures/.

**Реализовать:** Создать валидные synthetic входы/контекст/версии и declared expected для каждой строки матрицы ниже. Прогнать общий runner/workflows и проверить signals/decision/effect/execution count; заполнить отдельные отметки Sxx.

**Граница объема:** 15 основных сценариев плюс два обязательных именованных варианта. Все используемые зависимости загружаются из схем/портов, а не из hardcoded готовых assessments.

**Приемка и качество:** Все 17 строк сценарной матрицы отмечены по фактическому backend/harness прогону с evidence. Есть benign и failure controls, отрицательные варианты ownership/consent/expiry/duplicates. На этапе P32 эти же случаи подтверждаются окончательным UI.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p27"></a>

### P27. Завершить сценарный UI, проверку звонков и ресурсов

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P24](#p24), [P26](#p26).

**Архитектура:** [§10: все фичи и маршруты](ARCHITECTURE.md#frontend); [§10.3: состояния](ARCHITECTURE.md#ux-contract); [§12: демонстрация](ARCHITECTURE.md#scenarios).

**Где и какой результат:** W/features/scenario-player/, call-verification/, resource-check/, communication-inbox/; app/pages и существующие feature public APIs.

**Реализовать:** Добавить SMS/chat/transcript, список/шаги/reset scenarios, call proof status, загрузку/просмотр screenshot, resource gate и восстановление run. Довести все продуктовые маршруты §10.2, кроме study feedback из P30.

**Граница объема:** Все фичи общаются через страницы/props/query cache, не импортируют внутренности соседней фичи. Вердикты до проверки/исследовательские labels не раскрываются.

**Приемка и качество:** Пользователь проходит каждый основной канал; unavailable/expired verification отличимы от verified, CV помечен mock. Arbitrary URL не загружается, research data не уничтожается reset. Empty/loading/error/degraded доступны в UI, длинные причины читаемы.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="stage-research"></a>

## 9. Инструменты исследования

<a id="p28"></a>

### P28. Подготовить протокол UX-теста, анкету и шаблон отчета

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P26](#p26).

**Архитектура:** [§13: дизайн исследования](ARCHITECTURE.md#ux-research); [§13.2: метрики](ARCHITECTURE.md#ux-metrics); [§13.3: материалы](ARCHITECTURE.md#research-output).

**Где и какой результат:** research/protocols/, instruments/, report_templates/; docs/research/ для описания процедуры.

**Реализовать:** Определить protocol version, единицу анализа, primary trial до опыта, условия/порядок, безопасные действия, 120 s окно, включение/исключение/reload и единый вопрос 1–5. Задать поля для целевой аудитории, размера/продолжительности исследования и процедуры согласия.

**Граница объема:** Можно подготовить без участников. Неизвестные организационные параметры явно перечислить; P37 не начинается, пока они не заполнены и не зафиксированы. Не заполнять шаблон вымышленными результатами.

**Приемка и качество:** По документу другой человек может провести одинаковый trial и определить eligible/outcome без догадок. Технические исключения и влияние автоматического deny определены заранее. Анкета/согласие не смешаны с разрешением анализа коммуникаций.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p29"></a>

### P29. Реализовать study/trial, прием событий и обратную связь

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P28](#p28), [P25](#p25), [P05](#p05).

**Архитектура:** [§4.9: research](ARCHITECTURE.md#feature-research); [§13.1: события](ARCHITECTURE.md#ux-events); [§8: study API](ARCHITECTURE.md#api); [§14: research storage](ARCHITECTURE.md#persistence).

**Где и какой результат:** B/domain/research/, application/research/, persistence/; contracts/events/; study/trial/events/feedback/completion transport.

**Реализовать:** Сделать pseudonymous study/session/primary trial/condition, чтение текущего состояния, atomic event batches/allowlist/schema/dedup, feedback 1–5, completion/abort. Сохранить client_timebase_id/sequence и исключения тайминга. Подключить handler сценарного шага submit_feedback через исследовательский workflow с действующим trial; проверить его в сценарном режиме, не вызывая соседние application-фичи напрямую.

**Граница объема:** События исследования не меняют платежные решения и не подменяют audit; отсутствие research consent запрещает именно этот сбор.

**Приемка и качество:** Event retry/reorder не удваивает наблюдения, invalid batch отклоняется атомарно. Клиент не переназначает primary/condition/role, не читает чужое исследование. Feedback один актуальный; restart/reset сохраняет trials, completion технического сбоя отличим от добровольного выхода.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p30"></a>

### P30. Реализовать исследовательские события и feedback UI

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P29](#p29), [P27](#p27).

**Архитектура:** [§10: study-feedback](ARCHITECTURE.md#frontend); [§13.1: timebase](ARCHITECTURE.md#ux-events); [§13.2: измеримость](ARCHITECTURE.md#ux-metrics).

**Где и какой результат:** W/features/study-feedback/; instrumentation существующих feature boundaries через app/pages и shared event transport; /study/:id/feedback.

**Реализовать:** Добавить исследовательский вход через существующие onboarding и /demo: явное research consent → создание study → назначенный primary trial. Предусмотренный протоколом ввод/выбор участника до warning фиксирует prior risky intent; он не берется из expected или автоматической команды сценария. Собирать только allowlist событий, общий impression_id для operational/research warning, видимый render с доступными кнопками, монотонную базу document, feedback/completion и submit_feedback step. Восстанавливать study/trial через GET.

**Граница объема:** Не добавлять отдельное событие просмотра за каждый fetch/re-render; instrumentation не задерживает основное защитное действие.

**Приемка и качество:** Технический браузерный прогон проходит consent → study → primary trial → явно введенное намерение → warning → безопасное действие → feedback; P32 дополняет его проверкой экспорта P31. Проверены отказ/отзыв consent, retry без дубля, reload между warning/response, новый client_timebase_id без нового trial. Feedback валидируется 1–5, незавершенное измерение не превращается в reaction=0; raw content не отправляется в analytics. Этот технический прогон не считается участником P37.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p31"></a>

### P31. Реализовать вычисление UX-метрик и обезличенный экспорт

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P29](#p29), [P28](#p28).

**Архитектура:** [§13.2: точные формулы](ARCHITECTURE.md#ux-metrics); [§13.3: JSONL/CSV/Report](ARCHITECTURE.md#research-output); [§8: researcher export](ARCHITECTURE.md#api).

**Где и какой результат:** B/domain/research/metric_definition.py; application/research/export_study.py и metric use cases; export adapter; synthetic metric test fixtures.

**Реализовать:** Рассчитать participant-level primary metrics и отдельные trial slices; формировать JSONL events, CSV trial summaries и Report JSON по архитектуре. Обработать нулевые знаменатели, non-response, reload, skipped/aborted и повторные прохождения.

**Граница объема:** Синтетический проверочный набор служит проверке формул, не результатом UX-теста. Экспорт доступен researcher и не содержит raw сообщений/платежных IDs.

**Приемка и качество:** На вручную посчитанном небольшом наборе совпадают numerator/denominator, средние/median/p90 и exclusions. Auto deny/ack не считается изменением поведения; добровольный ранний выход учтен. Проверены CSV injection, пропуски полезности, одинаковые participant с несколькими trials и неопределенный тайминг.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="stage-technical"></a>

## 10. Техническая приемка и демонстрация

<a id="p32"></a>

### P32. Проверить всю систему через итоговый API и браузер

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P27](#p27), [P30](#p30), [P31](#p31).

**Архитектура:** [§18.2: уровни тестов](ARCHITECTURE.md#verification); [§12: сценарии](ARCHITECTURE.md#scenarios); [§7.3: инварианты](ARCHITECTURE.md#idempotency).

**Где и какой результат:** apps/backend/tests/{unit,application,contract,integration,architecture}/; apps/web/tests/{unit,component,e2e}/; contracts/examples/.

**Реализовать:** Провести сквозную приемку всех S01–S15 и двух обязательных вариантов на итоговом UI/backend; проверить все API строки матрицы, import boundaries, contract drift и критические гонки. Сопоставить UI-исход с серверной записью/эффектом.

**Граница объема:** Не заменять backend frontend interception-моком при сквозной приемке. Contract fixtures и изолированные component tests могут использовать doubles, но не доказывают end-to-end готовность.

**Приемка и качество:** Обязательные случаи реально выполнены и имеют результаты, без skipped маскировки. Пройдены типизация/lint/схемы/миграции и затронутая регрессия. Старые evidence при несовместимых изменениях обновлены; падения устранены до done.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p33"></a>

### P33. Довести эксплуатацию, восстановление и измерение задержек

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P32](#p32).

**Архитектура:** [§11: защита данных](ARCHITECTURE.md#configuration); [§14: retention](ARCHITECTURE.md#persistence); [§15: надежность](ARCHITECTURE.md#reliability).

**Где и какой результат:** B/infrastructure/runtime/, observability/; ops/local/, runbooks/; scripts/seed, backup/restore/cleanup; локальный var/ вне Git.

**Реализовать:** Проверить health/readiness, структурированные логи, окончательную конфигурацию mock-only, seed, restore/recovery, reset и cleanup по retention. Измерить целевые p95 на описанном стенде, отделив injected failures.

**Граница объема:** Локальная эксплуатация MVP; контейнеры только если нужны воспроизводимому выбранному запуску. Нет production SLA и миграции в PostgreSQL ради галочки.

**Приемка и качество:** Реально выполнены backup→restore и restart с pending/unknown; trials сохранены, duplicate effects отсутствуют. В логах/экспортах нет секретов/raw контента. Зафиксированы среда, n и результаты p95; цели архитектуры выполнены либо сначала явно пересмотрены в архитектуре с причиной, а не объявлены измеренными по конфигу.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p34"></a>

### P34. Проверить доступность и качество всех UI-состояний

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P32](#p32).

**Архитектура:** [§10.3: UX-контракт](ARCHITECTURE.md#ux-contract); [§18.2: web tests](ARCHITECTURE.md#verification).

**Где и какой результат:** W/features/, shared/ui/, formatting/, i18n/; browser checks и запись результатов в журнал.

**Реализовать:** Проверить 360/768/1280 px, 200% zoom, длинный русский текст, focus/keyboard/screen reader semantics. Пройти loading/error/degraded/unknown/hold/deny и безопасный выход из warning.

**Граница объема:** Это техническая UX-проверка; полезность/понятность людям измеряются в P37–P38.

**Приемка и качество:** Нет недоступной основной кнопки/обрезанного объяснения; severity не только цвет; mock/scope видны. Esc не подтверждает действие, URL обезврежены, банк accepted не показан completed. Исправления сопровождаются затронутыми проверками, а не повтором всей системы без причины.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p35"></a>

### P35. Зафиксировать техническую готовность прототипа

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P33](#p33), [P34](#p34).

**Архитектура:** [§18.3: готовый MVP](ARCHITECTURE.md#mvp-acceptance); [§1: границы](ARCHITECTURE.md#scope).

**Где и какой результат:** Этот документ, журнал; README.md и ops/runbooks/ с актуальным состоянием реализации.

**Реализовать:** Проверить, что P01–P34 завершены и доказательства относятся к текущему состоянию; воспроизвести основную цепочку и убедиться, что полный набор запускается по инструкции. Обновить текст «только каркас» там, где он больше не соответствует текущему коду.

**Граница объема:** Закрывает только техническую готовность. Не закрывает реальное UX-исследование, итоговые выводы, презентацию или интеграции.

**Приемка и качество:** Нет обязательной незавершенной/пропущенной проверки; матрицы функций/API/сценариев покрыты. README дает проверенный запуск, ограничения явно перечислены. В журнале зафиксирована контрольная точка «технический прототип», без заявления полной сдачи TASK.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p36"></a>

### P36. Подготовить комплект демонстрации и структуру презентации

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§3.1: документы/ops](ARCHITECTURE.md#supporting-directories); [§13.3: презентация](ARCHITECTURE.md#research-output); [§15: демонстрация](ARCHITECTURE.md#reliability).

**Где и какой результат:** docs/presentation/outline.md; ops/runbooks/demo.md; README.md; ссылки на данные/контракты/сценарии.

**Реализовать:** Описать маршрут показа основной цепочки, выбор контрольных случаев, проверенный запуск/reset/backup, известные ограничения и структуру слайдов. Сделать воспроизводимый пакет текущего локального результата.

**Граница объема:** Только outline/демо-комплект; места фактических UX-результатов остаются пустыми до P38. Публикация сайта не требуется для локального web-прототипа.

**Приемка и качество:** Другой агент/демонстратор запускает пакет по инструкции, воспроизводит эффект защиты и восстановление. На демонстрации видны mocks и scope. Подготовленный outline не назван готовой финальной презентацией.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="stage-delivery"></a>

## 11. Фактическое исследование и сдача TASK

<a id="p37"></a>

### P37. Провести реальные UX-сессии по протоколу

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P28](#p28), [P35](#p35), [P36](#p36).

**Архитектура:** [§13: проведение исследования](ARCHITECTURE.md#ux-research); [§17: организационные условия](ARCHITECTURE.md#open-questions); [§18.3: полная сдача](ARCHITECTURE.md#mvp-acceptance).

**Где и какой результат:** Research runtime records в var/ с доступом по роли; журнал проведения и обезличенная процедура в docs/research/.

**Реализовать:** До первого участника зафиксировать целевую аудиторию, n/продолжительность/условия в протоколе и manifest проверенного прототипа: build identifier (commit или hash сборки), policy/content/fixture/protocol versions. Связать manifest с study/trial в журнале проведения. С участниками, давшими consent, провести primary trials и анкету, сохранить реальные события, completion/exclusions и случаи отказа. Существенная смена кода/политики/контента требует новой версии условий и отдельного среза; данные до/после не объединяются молча.

**Граница объема:** Нужны реальные участники и доступная исследовательская сессия. Не выдавать агентские/S01–S15 автопрогоны за людей. Приглашения людям отправляются только при соответствующей авторизации; подготовка инструмента ее не подразумевает.

**Приемка и качество:** Протокол выполнен на фактических сессиях и записан объем выборки. Если участников/согласия нет — статус blocked с точным условием, чекбокс открыт; техническая часть P35 остается отдельно готовой.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p38"></a>

### P38. Проверить данные исследования и выпустить фактический UX-отчет

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P37](#p37), [P31](#p31).

**Архитектура:** [§13.2: расчет/ограничения](ARCHITECTURE.md#ux-metrics); [§13.3: отчет](ARCHITECTURE.md#research-output).

**Где и какой результат:** docs/research/ux-results.md и обезличенные агрегаты; приватные исходные экспорты остаются вне Git.

**Реализовать:** Проверить completeness/dedup/timebases/primary assignments/consent и сопоставимость build/policy/content/fixture/protocol versions по manifest исследования. Посчитать метрики на реальных данных с раздельными срезами при измененных условиях, раскрыть participants/trials/non-response/exclusions и типовые ошибки. Сформулировать подтвержденные выводы и ограничения, указать версию прототипа, к которой относятся результаты.

**Граница объема:** Нулевой знаменатель/малая выборка описываются честно. Не делать вывод о причинном снижении потерь/NPS/мошенничества из демонстрации.

**Приемка и качество:** Каждое число воспроизводимо из разрешенного экспорта; числители/знаменатели и версии присутствуют. Комментарии очищены; гипотезы отделены от измерений. Отчет не закрывается шаблоном или синтетической проверкой формул.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p39"></a>

### P39. Создать итоговую презентацию с реальными результатами

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P38](#p38), [P36](#p36).

**Архитектура:** [§13.3: содержание слайдов](ARCHITECTURE.md#research-output); [§1.1: ожидаемые результаты](ARCHITECTURE.md#scope).

**Где и какой результат:** docs/presentation/ — финальный deck и/или PDF, outline и разрешенные изображения.

**Реализовать:** Собрать проблему/исследование, основной flow, demo, каталог и benign controls, архитектуру/mocks, методику/результаты, ошибки и рекомендации по внедрению. Ссылаться на фактический отчет и проверенную демонстрацию.

**Граница объема:** Не создавать маркетинговые проценты без evidence. Конкретный формат презентации выбрать под способ сдачи; сохранить редактируемый источник, если выбранный инструмент его поддерживает.

**Приемка и качество:** Финальный артефакт существует, открывается и визуально проверен по всем слайдам; числа совпадают с P38. Outline, пустые slides и ссылка на несуществующий deck не закрывают пункт.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="p40"></a>

### P40. Провести итоговую приемку и передать результат проекта

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P39](#p39).

**Архитектура:** [§1.1: требования](ARCHITECTURE.md#scope); [§18.3: полная приемка](ARCHITECTURE.md#mvp-acceptance).

**Где и какой результат:** README.md, этот чеклист/журнал, ops/runbooks/, docs/research/, docs/presentation/.

**Реализовать:** Сверить TASK с реальными выходами: интерактивный прототип, 15 сценариев, мок-ассистент, UX-результаты и презентация. Записать проверенные команды, состояние зависимостей, известные ограничения и места артефактов для следующего исполнителя.

**Граница объема:** Окончание P01–P40 не означает разрешения автоматически начать E-пункты или включить реальные финансовые действия.

**Приемка и качество:** Все P-пункты и обязательные S-строки закрыты с актуальными доказательствами, готовность кода/исследования/слайдов подтверждена отдельно. Нет скрытого «не проверено» в обязательном результате TASK; остающиеся улучшения названы необязательными и не маскируют требования.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="scenario-checklist"></a>

## 12. Приемка каждого сценария

Источник ожидаемого поведения — [каталог архитектуры](ARCHITECTURE.md#scenarios). Здесь хранится отметка первого полного backend/harness прогона P26, с fixture_version/policy_version и записью результата в журнале. P32 добавляет к этим результатам evidence итогового E2E, а не считает успешный backend-прогон проверкой UI. После изменения сценария/политики затронутая отметка снимается до повторной проверки.

- [ ] **S01** — Фишинговое SMS из active реестра → critical → warning → фактический запрет demo-перехода. **Evidence:** —.
- [ ] **S02** — Звонок «службы безопасности» без proof: high; связанный перевод critical; номер не подтверждает источник. **Evidence:** —.
- [ ] **S03** — «Родственник в беде»: high 55; новый получатель/необычная сумма/связанный контакт: critical 80. **Evidence:** —.
- [ ] **S04** — Выигрыш с предварительной оплатой и известной ссылкой: critical, ограничение и нужная education card. **Evidence:** —.
- [ ] **S05** — Новый похожий домен вне реестра плюс давление: high 55; no_match не снимает признаки. **Evidence:** —.
- [ ] **S06** — URL + подготовленный screenshot: high и явный mock CV; нет скрытого fetch сайта. **Evidence:** —.
- [ ] **S07** — Чужой/истекший proof и запрос кода: high; проверены call/user/nonce/expiry. **Evidence:** —.
- [ ] **S08** — Active номер и связанный получатель в окне: critical 100/deny; submit не начинается. **Evidence:** —.
- [ ] **S09** — Новый получатель + ≥3 медиан + достаточная история: high/hold, gate сохранен. **Evidence:** —.
- [ ] **S10** — Связь с active network snapshot: critical/deny, evidence/версия/срок доступны. **Evidence:** —.
- [ ] **S11** — Известный получатель и обычная история: low/allow; отдельное подтверждение и достоверный банковский статус. **Evidence:** —.
- [ ] **S12** — Срочная обычная встреча: low; нет блокирующего предупреждения. **Evidence:** —.
- [ ] **S13** — Валидный proof нейтрального звонка: verified mock/low; login/номер не заменяют proof. **Evidence:** —.
- [ ] **S14** — Малая история + недоступные lookup/network: unknown/hold; восстановление дает partial и сохраняет hold, старый check негоден. **Evidence:** —.
- [ ] **S15** — Известный получатель/необычная сумма: medium 30; два подтверждения и timeout после принятия дают один submit, затем reconcile. **Evidence:** —.
- [ ] **S09.false_positive** — Законная операция ошибочно получила hold; жалоба сохраняется, gate автоматически не снимается; доступен допустимый выход. **Evidence:** —.
- [ ] **S15.declined_after_accepted** — Принятый submit позже declined: сервер сохраняет intent failed / BankOperation declined. Отображение без ложного completed отдельно проверяет P32. **Evidence:** —.

S11–S13 — контрольные случаи, S14–S15 — устойчивость. Именованные варианты не увеличивают количество основных сценариев. Дополнительно проверять общие отказы из [§12 архитектуры](ARCHITECTURE.md#scenarios): consent revoked, другой owner, expired registry, duplicate/reordered observation, измененные реквизиты, delivery failure и выход пользователя. Приемкой отрицательного случая считается ожидаемый результат, а не падение теста.

<a id="api-coverage"></a>

## 13. Карта API: кто обязан довести каждый контракт

Все пути ниже имеют префикс `/api/v1`. Полные входы/выходы/статусы определяет [§8 архитектуры](ARCHITECTURE.md#api); таблица не создает второй источник схем. P32 сверяет ее с итоговым OpenAPI, положительными и отрицательными проверками.

| API / способность | Основной владелец | Что дополнительно проверить |
| --- | --- | --- |
| POST /sessions/demo; GET /session; PATCH /consents/{scope} | P05 | Pre-session flow, ownership, CSRF, consent revision; web P06 |
| GET /health/live; GET /health/ready | P04, окончательно P33 | Наличие DB/content/fixtures, корректность mode; optional unavailable не скрывается |
| POST /media; GET /media/{id} | P18 | Decode/лимиты/ownership, контролируемая выдача изображения |
| POST /observations; POST /observations/{id}/reassessments | P15 | Atomic ingress, deadline, degraded, immutable recheck/recovery |
| GET /incidents; GET /incidents/{id}; POST /incidents/{id}/resolution | P10 → P15 | Pagination/timeline/owner; resolution не отменяет банк |
| GET /assessments/{id} | P11 → P15 | Нет утечки content/evidence чужого владельца |
| POST /calls/{call_id}/verifications | P17 | Binding/expiry/replay/нет доверия к caller number |
| POST /warnings/{id}/presentation; POST /warnings/{id}/responses | P13, UI P16 | Реальный render, повтор, acknowledgment не является submit |
| POST /transfers; PATCH /transfers/{id}; GET /transfers/{id} | P21, полный view P23 | Fingerprint/revision/lifecycle и отдельные check/execution/operation |
| POST /transfers/{id}/checks | P22 → P23 | Полный evaluation_context и подтверждаемое создание/возврат hold gate |
| POST /transfers/{id}/confirmations; POST /transfers/{id}/cancellations | P23 | Разные guards submit/cancel, разные keys/две вкладки, active/unknown |
| GET /executions/{id}; GET /bank-operations/{id} | P23 | Requested/confirmed отдельно от accepted/settled/declined |
| POST /incidents/{id}/resource-actions; GET /protection-actions/{id} | P14 | Scope/effect/idempotency, report_received не равен блокировке |
| POST /resource-navigation-checks | P14 | Сохраненный backend gate действительно запрещает demo-preview |
| GET /incidents/{id}/guidance | P12 → P15 | Reasons/content/allowed actions; без выдуманного контакта |
| GET /education/cards; GET /education/cards/{code} | P12 | Контент/version/locale, безопасный markdown, pagination |
| GET /scenarios; POST /scenario-runs; GET /scenario-runs/{id}; POST /scenario-runs/{id}/steps | P25 | Нет expected в UI, allowed steps, восстановление GET |
| POST /demo-resets | P25 | Новый namespace, сохранность исследования и исходов старых операций |
| POST /study-sessions; GET /study-sessions/{id} | P29 | Consent/pseudonym/primary/read ownership |
| POST /study-sessions/{id}/trials; GET /trials/{id} | P29 | Назначение condition, primary до опыта; reload не новый trial |
| POST /trials/{id}/events; POST /trials/{id}/feedback; POST /trials/{id}/completion | P29, UI P30 | Atomic validation/dedup/timebases/feedback 1–5/completion status |
| GET /study-sessions/{id}/export | P31 | Researcher-only, обезличивание, CSV injection, корректные знаменатели |
| Threat refresh/status через script, без публичного admin endpoint | P08 | Валидный atomic snapshot и fresh/revoked/expired |
| Применимые ошибки каждой команды/чтения | Владелец API + P32 | 401/403/404/409/413/415/422/429/503 по контракту; не все коды искусственно на каждом route |

Эта карта также определяет завершенность plumbing: наличие use case в domain/application не закрывает его HTTP/UI контракт. Добавление нового endpoint требует обновления архитектуры, владельца в этой таблице, OpenAPI и проверки соответствующего клиентского потребителя.

<a id="extensions"></a>

## 14. Условные расширения после прототипа

E-пункты — отдельный backlog по [§16–17 архитектуры](ARCHITECTURE.md#evolution). Их пустые чекбоксы не мешают закрыть P40. Они не стартуют автоматически после P40 и не являются скрытой обязанностью запроса «сделать прототип». Для старта нужен запрос на соответствующее расширение и проверка конкретных внешних условий из карточки; не надо повторно спрашивать разрешение, если оно уже содержится в текущем запросе.

`todo` здесь означает «еще не выполнялось», а не «доступ к провайдеру подтвержден». Когда работа началась и уперлась в недоступное условие, использовать `blocked` с evidence. При активации нескольких независимых capability разделять их на подзадачи и не считать готовность одного провайдера готовностью всей ветки.

<a id="e01"></a>

### E01. Подготовить данные и протокол независимой оценки моделей

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§16: ML-расширение](ARCHITECTURE.md#evolution); [§3.1: ml/](ARCHITECTURE.md#supporting-directories).

**Где и какой результат:** ml/datasets/, evaluation/, model_cards/.

**Реализовать:** Описать разрешенные источники/условия доступа, label policy, временные/групповые splits, leakage checks и per-class/slice/false-positive метрики.

**Граница объема:** Старт только при отдельном запросе на ML и доступных разрешенных данных. Не скачивать случайный датасет и не считать fixture-каталог независимой выборкой.

**Приемка и качество:** Есть проверенные манифесты/hash/разбиения и воспроизводимый протокол. Если данных нет, остается открытым соответствующий результат; доступность каталога не означает готовность датасета.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="e02"></a>

### E02. Подключить и оценить реальные NLP/CV/поведенческие модели

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [E01](#e01).

**Архитектура:** [§4.3: analysis ports](ARCHITECTURE.md#feature-detection); [§16: shadow-режим](ARCHITECTURE.md#evolution).

**Где и какой результат:** ml/experiments/, evaluation/, model_cards/; B/infrastructure/analysis/{nlp,vision,behavior}/.

**Реализовать:** По одной модели реализовать согласованный preprocessing/артефакт или endpoint, model version/hash, контракт адаптера и независимую оценку; сравнить с фиксированным baseline.

**Граница объема:** Обучение/расходы вычислений — только в разрешенном ML-объеме. Начать с shadow, без влияния на платежное исполнение; разные модели при необходимости оформить E02.a и далее.

**Приемка и качество:** Есть реальные результаты качества/ошибок/задержек и malformed/timeout tests, модельная карточка и воспроизводимость. Переход к влиянию на решения отдельно основан на критериях пилота; хороший средний score не закрывает критические классы.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="e03"></a>

### E03. Подключить реальный источник коммуникаций или speech-to-text

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§4.2: ObservationInput](ARCHITECTURE.md#feature-communications); [§16: каналы](ARCHITECTURE.md#evolution).

**Где и какой результат:** Новый входной adapter по ADR; B/application/ports/analysis.py для STT; источник приводит данные к ObservationInput.

**Реализовать:** Подтвердить API/permissions устройства, identity источника, согласия и качество транскрипта. Реализовать adapter→стандартный intake, timestamps/sequence, replay/dedup и unavailable.

**Граница объема:** Нужен явный запрос на конкретный канал и реальный доступ; native SDK не добавляется в domain или React web. Новый физический путь сначала фиксируется в архитектуре.

**Приемка и качество:** Контракт проверен на доступном провайдере/устройстве; отзыв разрешения/отсутствующий transcript и дубли обработаны. Имитация входящего SMS в браузере не закрывает интеграцию.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="e04"></a>

### E04. Реализовать реальную аутентификацию через Alfa ID

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§4.1: login](ARCHITECTURE.md#feature-identity); [§9: IdentityProviderPort](ARCHITECTURE.md#ports); [§17: доступ](ARCHITECTURE.md#open-questions).

**Где и какой результат:** B/infrastructure/identity/alfa_id/; согласованные login/callback routes и settings.

**Реализовать:** Получить актуальный контракт/доступ, реализовать auth flow с проверкой issuer/audience/state/nonce, безопасное хранение сессии и отзыв/ошибки.

**Граница объема:** Отдельная авторизованная интеграция; не придумывать provider endpoints и не включать credentials в repo. Это не проверка звонка.

**Приемка и качество:** Подтвержден фактический вызов разрешенной среды провайдера, а не только registration/config. Проверены mismatch/replay/expiry и session isolation; E05 остается независимым.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="e05"></a>

### E05. Подключить доверенную аттестацию конкретного звонка

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§4.1: call proof](ARCHITECTURE.md#feature-identity); [§9: CallAttestationPort](ARCHITECTURE.md#ports); [§16: независимые контракты](ARCHITECTURE.md#evolution).

**Где и какой результат:** B/infrastructure/identity/call_attestation/.

**Реализовать:** Подтвердить источник call-bound proof, его проверяемую подпись/срок/issuer, binding user/call/nonce; реализовать port и evidence provenance.

**Граница объема:** Нужен существующий документированный механизм банка/оператора; успешный Alfa ID login не удовлетворяет этому условию. E04 не является автоматическим обязательным доказательством.

**Приемка и качество:** Реальная разрешенная интеграционная проверка подтверждает конкретный вызов; неверная привязка/replay/expiry/unavailable различимы. Без механизма proof задача остается blocked, не заменяется сравнением номера.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="e06"></a>

### E06. Подключить банковскую историю по отдельному read-only контракту

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§9: TransactionHistoryPort](ARCHITECTURE.md#ports); [§16: банк](ARCHITECTURE.md#evolution); [§11: согласия](ARCHITECTURE.md#configuration).

**Где и какой результат:** B/infrastructure/bank/open_api/; history adapter и provider-specific configuration.

**Реализовать:** Проверить доступные поля/периоды/пагинацию и согласия; маппить данные в HistorySnapshot с as_of и feature version; обработать freshness, отозванный доступ и неполную историю.

**Граница объема:** Read-only возможности не включают submit/hold/cancel. Нужны разрешенный доступ и согласие на конкретные данные.

**Приемка и качество:** Contract/sandbox проверки на реальном протоколе, воспроизводимое отображение в профиль, отсутствие текущей/будущей операции в признаках. Отсутствующие данные остаются insufficient/unavailable.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="e07"></a>

### E07. Подключить банковское исполнение с подтверждаемым исходом

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§9: BankOperationsPort](ARCHITECTURE.md#ports); [§7.3: atomic authorization](ARCHITECTURE.md#idempotency); [§16: bank pilot](ARCHITECTURE.md#evolution).

**Где и какой результат:** B/infrastructure/bank/open_api/; конфигурация capabilities, execution/reconciliation integration tests и runbook.

**Реализовать:** Для каждой операции подтвердить submit/cancel/hold/status/idempotency semantics. Для настоящего hold отдельно описать release/expiry/резервирование в архитектуре. Проверить банковскую точку авторизации и неизвестные исходы.

**Граница объема:** Нужны отдельный запрос, контракт и права; readiness адаптера доказывается в разрешенном sandbox. Реальные денежные действия не выполняются ради приемки. Включение production не следует из закрытия карточки.

**Приемка и качество:** Sandbox реально проверил прием/окончательный исход/decline/reconcile, повторы и конфликтующие команды. Без необходимых гарантий capability unsupported. Production deployment запрещает mock evidence; fake bank tests не закрывают этот пункт.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="e08"></a>

### E08. Подключить реальные threat feeds и подготовку больших снимков

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§4.7: registry](ARCHITECTURE.md#feature-threats); [§16: Big Data](ARCHITECTURE.md#evolution).

**Где и какой результат:** B/infrastructure/threat_intel/providers/, analysis/network/; ingestion pipeline по согласованному ADR.

**Реализовать:** Проверить доступ/форматы источников, нормализацию/достоверность/снятие записей; реализовать атомарные версионированные snapshots и компактные online graph features.

**Граница объема:** Право доступа к МВД/РКН/API не подразумевается. Большие технологии вводятся по объему/нагрузке, а не как формальное выполнение слова Big Data.

**Приемка и качество:** Реальный разрешенный feed обновлен и проверен; плохой пакет сохраняет прежний snapshot, revoked/expired соблюдаются, актуальность измерима. Есть evidence источника и входного качества; нет полного графового расчета в HTTP запросе.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="e09"></a>

### E09. Подключить внешние уведомления и действия по ресурсу

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§9: Notification/ResourceEnforcement](ARCHITECTURE.md#ports); [§4.5: scope/effect](ARCHITECTURE.md#feature-protection); [§16: операторы/ресурсы](ARCHITECTURE.md#evolution).

**Где и какой результат:** B/infrastructure/notifications/operator/, resources/providers/.

**Реализовать:** Отдельно подключить доступный notification канал и report/restrict механизм с consent, delivery status, idempotency и проверяемым effect. При независимых провайдерах разделить на подзадачи.

**Граница объема:** Нужны документированные полномочия и конкретный авторизованный запрос; delivered не значит прочитано, report не значит takedown.

**Приемка и качество:** Проверен фактический вызов разрешенной среды, корректные scope/effect/ошибки и отзыв согласия. Отсутствующий механизм ограничения не изображается как блокировка; готовность одного адаптера не закрывает второй.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="e10"></a>

### E10. Масштабировать хранение и выполнение по результатам нагрузки

- [ ] Выполнено и проверено. **Статус:** todo. **Исполнитель:** —.

**Зависимости:** [P35](#p35).

**Архитектура:** [§14: БД](ARCHITECTURE.md#persistence); [§15: измерения](ARCHITECTURE.md#reliability); [§16: scaling](ARCHITECTURE.md#evolution).

**Где и какой результат:** B/infrastructure/persistence/sqlalchemy/, runtime/; ops/containers/, runbooks/; контрактные изменения по ADR.

**Реализовать:** При измеренной необходимости внедрить PostgreSQL/отдельный worker/очередь, проверенные миграции/backup/concurrency и эксплуатационные метрики. Если analysis станет async, явно изменить API/client contract на job-поток.

**Граница объема:** Отдельный запрос и обоснование нагрузкой. Не считать один выбор PostgreSQL переносом гарантий SQLite; не менять синхронный /observations незаметно.

**Приемка и качество:** Миграции/restore/конкуренция/provider idempotency проверены в новой топологии, результаты нагрузки записаны; domain/use cases не зависят от новой инфраструктуры. Развертывание вне локального стенда — отдельный разрешенный объем.

**Запись выполнения:** —. После начала работ заменить на ссылку на запись [журнала](#work-log).

<a id="work-log"></a>

## 15. Журнал выполнения и протокол передачи

Журнал дополняется, старые записи не заменяются. В карточке остается актуальная отметка и ссылка на последнюю запись. При перерыве записи должно хватить, чтобы новый агент продолжил без чтения полного чата. Полные чувствительные логи/данные в этот файл не копируются.

Формат записи (заполнить реальными значениями; это шаблон, не evidence):

```text
ID записи: YYYY-MM-DD-Pxx-NN
Задача/исполнитель:
Статус и дата:
Проверенная версия архитектуры / существенные решения:
Что сделано:
Файлы и артефакты: относительные пути и ссылки; commit, если он существует
Проверки:
  - команда, cwd, среда/версии, дата, exit code и наблюдаемый результат
  - ручная/браузерная проверка: сценарий, действия, фактический outcome, evidence
Что не проверено и почему:
Остаток / блокер:
Условие разблокировки:
Следующее конкретное действие:
Затронутые или повторно открытые зависимые задачи:
```

Для отдельной записи использовать заголовок с ID и стабильный HTML-якорь, например `log-YYYY-MM-DD-pxx-nn`. Ссылки на артефакты должны вести к существующим файлам; для приватного локального результата указать разрешенное место хранения без публикации данных. Если тест не запускался, писать «не запускался», без предполагаемого exit code.

### Правило завершения сессии агента

В последней записи явно указать: какие ID закрыты; какой ID активен; что сейчас блокирует работу; следующее допустимое действие; какие незавершенные проверки обязательны. Не оставлять `in_progress` без исполнителя и инструкции. Независимые задачи можно продолжать, пока внешний блокер P37/E-пункта сохраняется.

Если изменены бизнес-контракты, сначала обновить ARCHITECTURE и при необходимости ADR, затем приемку/зависимости здесь. После начала реальной реализации обновлять устаревающие описания текущего состояния в README/AGENTS; исторические записи архитектурной поставки сохранять как исторические.

### Записи

2026-09-14: создан протокол. Галочки P01–P40, S01–S15 с двумя обязательными вариантами и E01–E10 оставлены пустыми: создание плана не означает выполнение кода, тестов или исследования. Первый кандидат после запроса на реализацию — [P01](#p01).

<a id="log-2026-09-15-p01-01"></a>

#### 2026-09-15-P01-01

**Задача/исполнитель:** P01, Codex.

**Статус и дата:** done, 2026-09-15.

**Проверенная версия архитектуры / существенные решения:** ARCHITECTURE.md v1.0 от
2026-09-13, §2.1, §3.2 и §18.2. Архитектурные границы не менялись. Direct-зависимости
закреплены точными версиями; транзитивные зависимости фиксируют lock-файлы. TypeScript
закреплен на 5.9.3, потому что доступный TypeScript 7.0.2 не удовлетворяет peer-ограничениям
`typescript-eslint==8.70.0` и `openapi-typescript==7.13.0`.

**Что сделано:** Созданы Python package manifest и universal lock с runtime/dev группами,
настроены uv build backend, Ruff, mypy, pytest и import-linter. Созданы private npm manifest и
lock для React/Vite-стека, строгий TypeScript, ESLint flat config и Prettier. Добавлен проверенный
runbook с рабочими каталогами, общей Python-средой, воспроизводимой установкой и явными
границами еще не исполнимых команд. README обновлен до фактического состояния P01.

**Файлы и артефакты:** `apps/backend/pyproject.toml`, `apps/backend/uv.lock`,
`apps/backend/src/alpha_defense/__init__.py`, `apps/web/package.json`,
`apps/web/package-lock.json`, `apps/web/tsconfig.json`, `apps/web/eslint.config.js`,
`apps/web/.prettierrc.json`, `apps/web/.prettierignore`, `apps/web/src/vite-env.d.ts`,
`ops/runbooks/development.md`, `README.md`, этот чеклист. Commit `cd8a8d8` («Настроить
инструменты и зависимости проекта») отправлен в `origin/main` 2026-09-15.

**Проверки:**

- `uv lock` и `uv lock --check`, cwd `apps/backend`, uv 0.11.7 / CPython 3.11.15,
  2026-09-15: exit 0, разрешено 43 пакета.
- `UV_PROJECT_ENVIRONMENT=/Users/Shared/github/MachineLearning/ml_venv uv sync --frozen
  --inexact`, cwd `apps/backend`, 2026-09-15: exit 0; проект собран и установлен, посторонние
  пакеты общей среды не удалялись.
- `ruff check src tests`, `ruff format --check src tests`, `mypy` и
  `lint-imports --config pyproject.toml` через принятый venv, cwd `apps/backend`, 2026-09-15:
  все exit 0; проверен 1 Python-файл, import-linter подтвердил 0 нарушенных контрактов при
  пока еще не созданных контрактах P02.
- `uv build` во временный каталог, cwd `apps/backend`, 2026-09-15: exit 0; созданы и открыто
  перечислены sdist и `py3-none-any` wheel. `pytest --version`: exit 0, pytest 9.1.1.
- `npm ci`, cwd `apps/web`, Node 26.4.0 / npm 11.17.0, 2026-09-15: exit 0, установлено
  280 пакетов из lock; браузеры Playwright не устанавливались.
- `npm run lint`, `npm run typecheck`, `npm run format:check`, cwd `apps/web`, 2026-09-15:
  все exit 0. `npm ls --depth=0` подтвердил direct-версии; Vitest 5.0.0 и Playwright 1.63.0
  доступны.
- `npm audit --audit-level=high`, cwd `apps/web`, 2026-09-15: exit 0, найдено 0 известных
  уязвимостей. `git diff --check`, cwd корня репозитория: exit 0.

**Что не проверено и почему:** Backend pytest-suite, frontend Vitest/Playwright-suite и сборка
Vite-приложения не запускались: до P02/P06 нет тестовых модулей и web entrypoint; команды
помечены в runbook как подготовленные, а не прошедшие. Полный `pip check` общей среды имеет
exit 1 из-за ранее существующих конфликтов `rectools==0.19.0` с `attrs==26.1.0`,
`numpy==2.4.6`, `pandas==3.0.5`; эти пакеты отсутствуют в lock проекта и не изменялись P01.

**Остаток / блокер:** По P01 остатка и блокера нет. Исправление чужих конфликтов общего venv
не входит в P01 и не требуется стеком Alpha Defense.

**Условие разблокировки:** Не применимо.

**Следующее конкретное действие:** При отдельном разрешении начать [P02](#p02): общие типы,
ошибки и исполнимые import-boundary contracts.

**Затронутые или повторно открытые зависимые задачи:** Закрыт P01; активных задач нет; P02
стал доступен, но в рамках запроса только P01 не запускался.

<a id="log-2026-09-15-p02-01"></a>

#### 2026-09-15-P02-01

**Задача/исполнитель:** P02, Codex.

**Статус и дата:** done, 2026-09-15.

**Проверенная версия архитектуры / существенные решения:** ARCHITECTURE.md v1.0 от
2026-09-13, §2.2, §4.11 и §5. Архитектурные границы не менялись. Domain использует только
stdlib и `domain/shared`; application зависит от domain и собственных контрактов; runtime I/O
представлен Protocol-портами без конкретных адаптеров.

**Что сделано:** Реализованы `EntityId`, integer-minor-unit `Money` только для RUB в границах
MVP, `Severity`, `ExecutionMode` и `Provenance`. Добавлены серверный `ActorContext`/роли,
инъецируемые `Clock`/`IdGenerator`, cursor pagination и типизированная иерархия прикладных
ошибок без HTTP-зависимостей. Настроены четыре Import Linter контракта и дополнительная
AST-проверка stdlib/фичевых границ. Для web добавлено локальное ESLint-правило, проверяющее
направление `app → pages → features → shared` и запрет импорта между соседними features.

**Файлы и артефакты:** `apps/backend/src/alpha_defense/domain/shared/`,
`apps/backend/src/alpha_defense/application/shared/`,
`apps/backend/src/alpha_defense/application/ports/runtime.py`, package markers корней слоев,
`apps/backend/tests/unit/`, `apps/backend/tests/architecture/test_import_boundaries.py`,
`apps/backend/pyproject.toml`, `apps/web/eslint-rules/layer-boundaries.js`,
`apps/web/tests/unit/layer-boundaries.test.js`, `apps/web/eslint.config.js`,
`apps/web/tsconfig.json`, `.gitignore`, `ops/runbooks/development.md`, `README.md`, этот чеклист.
Commit `0e51cfc` («Реализовать общие типы и границы слоёв») отправлен в `origin/main`
2026-09-15.

**Проверки:**

- `ruff check src tests` и `ruff format --check src tests` через принятый venv, cwd
  `apps/backend`, 2026-09-15: обе команды exit 0, проверено 20 Python-файлов.
- `mypy`, cwd `apps/backend`, 2026-09-15: exit 0, строгая типизация прошла для 20 source/test
  файлов.
- `pytest`, cwd `apps/backend`, 2026-09-15: exit 0, 30 passed; проверены Money/ID/provenance,
  ActorContext/errors/pagination, инъекция frozen clock/fixed ID и позитивные/негативные
  направления импортов.
- `lint-imports --config pyproject.toml`, cwd `apps/backend`, 2026-09-15: exit 0,
  `4 kept, 0 broken`, 24 файла и 30 зависимостей. Временный импорт
  `domain.shared → infrastructure` дал ожидаемый exit 1 и `BROKEN`; после удаления probe
  повторный прогон снова дал `4 kept, 0 broken`.
- `uv lock --check` и `uv build` во временный каталог, cwd `apps/backend`, 2026-09-15:
  exit 0; lock остался согласован, sdist/wheel собраны, новые domain/application модули
  присутствуют в wheel.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run format:check`, cwd `apps/web`,
  2026-09-15: все exit 0; Vitest `3 passed`. Временный импорт `shared → features` дал
  ожидаемый ESLint exit 1 по `project/layer-boundaries`; после удаления probe lint проходит.
- `npm audit --audit-level=high`, cwd `apps/web`, 2026-09-15: exit 0, найдено 0 известных
  уязвимостей. `git diff --check`, cwd корня репозитория, 2026-09-15: exit 0.

**Что не проверено и почему:** HTTP, persistence, миграции, runtime-реализации Clock/ID и
интеграционные сценарии не создавались и не проверялись: это объем P03–P05. Playwright не
запускался, поскольку P02 не добавляет пользовательский интерфейс. Общий venv сохраняет
описанные в runbook посторонние конфликты `rectools`; стек P02 их не импортирует.

**Остаток / блокер:** По P02 остатка и блокера нет.

**Условие разблокировки:** Не применимо.

**Следующее конкретное действие:** При отдельном разрешении начать [P03](#p03): порты и
реализации UnitOfWork, idempotency/audit/outbox и начальные технические миграции.

**Затронутые или повторно открытые зависимые задачи:** Закрыты P01 и P02; активных задач нет;
P03 стал доступен, но не запускался.

<a id="log-2026-09-15-p03-01"></a>

#### 2026-09-15-P03-01

**Задача/исполнитель:** P03, Codex.

**Статус и дата:** done, 2026-09-15.

**Проверенная версия архитектуры / существенные решения:** ARCHITECTURE.md v1.0 от
2026-09-13, §7.3, §7.4, §9 и §14. Архитектурные границы не менялись. SQLite остается
единственным durable-хранилищем MVP, in-memory adapter воспроизводит те же смысловые
ограничения. Outbox имеет at-least-once семантику: handler вызывается вне UoW, а provider
idempotency/exactly-once не имитируются.

**Что сделано:** Добавлены plain application-контракты repository/UoW/events, versioned event
envelope, idempotency scope/record с canonical command hash, audit record и outbox lease/state.
Реализованы сериализуемый copy-on-write in-memory UoW и SQLite/SQLAlchemy UoW с явными
entity↔row mapper-функциями, optimistic CAS и прикладным преобразованием ошибок хранения.
Создана начальная Alembic-миграция только для `idempotency_records`, `audit_events`, `outbox`;
state/result, revision, uniqueness и outbox state/timestamp защищены ограничениями БД.
Добавлены системные Clock/UUID, SHA-256 fingerprints, transactional audit/event adapters и
dispatcher с retry, lease и восстановлением незавершенной доставки после restart.

**Файлы и артефакты:** `apps/backend/src/alpha_defense/application/ports/{events,
repositories,unit_of_work}.py`, `apps/backend/src/alpha_defense/infrastructure/persistence/`,
`apps/backend/src/alpha_defense/infrastructure/runtime/`,
`apps/backend/src/alpha_defense/infrastructure/observability/`, `apps/backend/alembic.ini`,
`apps/backend/migrations/`, `apps/backend/tests/{contract,integration}/`,
`apps/backend/tests/unit/test_runtime_infrastructure.py`, `apps/backend/pyproject.toml`,
`ops/runbooks/development.md`, `README.md`, этот чеклист. Commit `f103eb8` («Реализовать
хранилище и гарантии команд») отправлен в `origin/main` 2026-09-15.

**Проверки:**

- `uv lock --check`, cwd `apps/backend`, uv 0.11.7 / CPython 3.11.15, 2026-09-15:
  exit 0, разрешено 43 пакета.
- `ruff check src tests migrations` и `ruff format --check src tests migrations` через
  принятый venv, cwd `apps/backend`, 2026-09-15: обе команды exit 0, 48 файлов соответствуют
  правилам и форматированию.
- `mypy`, cwd `apps/backend`, 2026-09-15: exit 0, strict-проверка прошла для 48 source/test/
  migration файлов.
- `pytest`, cwd `apps/backend`, 2026-09-15: exit 0, `46 passed`. Десять общих contract cases
  выполнены для in-memory и SQL; проверены rollback без частичной записи, replay/conflict,
  CAS, атомарные audit/outbox, dispatch/retry. Три integration cases проверили реальную
  SQLite-конкурентность, restart recovery и Alembic upgrade/check/downgrade/upgrade без drift.
- `lint-imports --config pyproject.toml`, cwd `apps/backend`, 2026-09-15: exit 0,
  `4 kept, 0 broken`, проанализировано 54 файла и 124 зависимости.
- `uv build --out-dir <temporary-directory>`, cwd `apps/backend`, 2026-09-15: exit 0,
  созданы sdist и wheel; новые ports/persistence/runtime/observability модули присутствуют в
  wheel.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run format:check`, cwd `apps/web`,
  2026-09-15: все exit 0; frontend regression `3 passed`. `npm audit --audit-level=high`:
  exit 0, найдено 0 известных уязвимостей.
- `git diff --check`, cwd корня репозитория, 2026-09-15: exit 0.

**Что не проверено и почему:** HTTP/bootstrap и пользовательские сценарии не создавались —
это P04 и последующие карточки. Реальные provider handlers и денежные операции отсутствуют;
P03 проверяет только регистрацию/повтор технической доставки и не заявляет exactly-once.
PostgreSQL не проверялся, поскольку архитектура MVP требует SQLite. Общий venv сохраняет
описанные в runbook посторонние конфликты `rectools`; код P03 их не импортирует.

**Остаток / блокер:** По P03 остатка и блокера нет.

**Условие разблокировки:** Не применимо.

**Следующее конкретное действие:** Начать [P04](#p04): settings/container/ASGI bootstrap,
Problem Details, request_id, health и детерминированный OpenAPI с web-типами.

**Затронутые или повторно открытые зависимые задачи:** Закрыты P01–P03; активных задач нет;
P04 стал доступен, но не запускался.

<a id="log-2026-09-17-p04-01"></a>

#### 2026-09-17-P04-01

**Задача/исполнитель:** P04, Codex.

**Статус и дата:** done, 2026-09-17.

**Проверенная версия архитектуры / существенные решения:** ARCHITECTURE.md v1.0 от
2026-09-13, §4.11, §8, §8.1 и §11. Границы слоев не менялись. Transport импортирует только
application-контракты и разрешенные HTTP-библиотеки; bootstrap остается единственным местом
сборки. Import Linter для transport настроен проверять запрещенные прямые импорты, поскольку
разрешенный application сам транзитивно использует domain; отдельный AST-тест продолжает
проверять эту границу. Live-режим не имитируется и отклоняется до появления проверенных
capability/adapters.

**Что сделано:** Реализованы типизированные settings, fail-fast container и ASGI factory.
Старт проверяет режим, секрет, каталоги, file-backed SQLite и точную Alembic revision, но не
выполняет миграции автоматически. Добавлены transport-neutral readiness port и локальная
проверка БД/обязательного файла политики. HTTP v1 публикует только live/ready; ready возвращает
503 до P07. Введены UUID request ID, базовые security headers, явный CORS/trusted-host список,
лимит тела, единый безопасный Problem Details и подготовленные CSRF/Idempotency-Key guards.
OpenAPI экспортируется каноническим JSON, из него сгенерированы TypeScript-типы; добавлены
валидные примеры live и unavailable.

**Файлы и артефакты:** `apps/backend/src/alpha_defense/{bootstrap,transport/http/v1}/`,
`apps/backend/src/alpha_defense/application/ports/readiness.py`,
`apps/backend/src/alpha_defense/infrastructure/observability/readiness.py`,
`apps/backend/tests/{unit/test_settings.py,contract/test_http_contract.py,
integration/test_http_app.py}`, `contracts/http/openapi.json`, `contracts/examples/`,
`apps/web/src/shared/api/generated/openapi.ts`, `scripts/export_openapi.py`,
`ops/local/.env.example`, runbook, README, AGENTS, архитектура и конспект для защиты. Commit
`242e6be` («Реализовать bootstrap и базовый HTTP-контур») создан 2026-09-17 и отправляется в
`origin/main` вместе с этой записью.

**Проверки:**

- `uv lock --check`, cwd `apps/backend`, uv 0.11.7 / CPython 3.11.15, 2026-09-17:
  exit 0, разрешено 43 пакета.
- `ruff check` и `ruff format --check` для `src tests migrations` и export-script через
  принятый venv, cwd `apps/backend`, 2026-09-17: обе команды exit 0, 69 файлов.
- `mypy`, cwd `apps/backend`, 2026-09-17: exit 0, strict-проверка прошла для 68 source/test/
  migration файлов.
- `pytest`, cwd `apps/backend`, 2026-09-17: exit 0, `66 passed`. Проверены environment factory,
  неверные mode/secret/DB, миграция до старта, live/ready, request ID, body limit, guards,
  Problem Details без утечки пути/секрета, примеры и детерминированность OpenAPI. Два warning
  относятся к deprecation внутри закрепленной связки FastAPI/Starlette TestClient и не скрывают
  failed/skipped тесты.
- `lint-imports --config pyproject.toml`, cwd `apps/backend`, 2026-09-17: exit 0,
  `4 kept, 0 broken`, проанализировано 78 файлов и 200 зависимостей.
- Два экспорта во временный каталог и сравнение с committed `openapi.json` через `cmp`, cwd
  `apps/backend`, 2026-09-17: все exit 0; байты совпадают. `npm run generate:api` успешно
  пересоздал `openapi.ts` из этого контракта.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run format:check`, cwd `apps/web`,
  2026-09-17: все exit 0; Vitest `3 passed`. `npm audit --audit-level=high`: exit 0,
  найдено 0 известных уязвимостей.
- `uv build --out-dir <temporary-directory>`, cwd `apps/backend`, 2026-09-17: exit 0,
  созданы sdist и wheel с новыми bootstrap/transport-модулями.

**Что не проверено и почему:** Полный бизнес-readiness 200 не заявляется: P07 должен добавить
JSON Schema, loader, версию/hash и валидный каталог; P04 проверяет отсутствие файла как 503.
Session/ownership и использование подготовленных guards реальными командами относятся к P05.
Web UI и браузерный flow относятся к P06 и последующим задачам. Реальные providers и live-
режим отсутствуют. Ручной browser-тест не нужен двум machine health endpoints; HTTP поведение
проверено через ASGI integration.

**Остаток / блокер:** По P04 остатка и блокера нет. Красная readiness — предусмотренное
состояние неполной сборки, а не незавершенность P04.

**Условие разблокировки:** Не применимо.

**Следующее конкретное действие:** Начать [P05](#p05): synthetic demo-сессии,
owner/namespace, серверные роли, согласия и подключение CSRF/idempotency к реальным командам.

**Затронутые или повторно открытые зависимые задачи:** Закрыты P01–P04; активных задач нет.
Разблокированы P05 и P07; по порядку плана следующая P05.

<a id="log-2026-09-18-p05-01"></a>

#### 2026-09-18-P05-01

**Задача/исполнитель:** P05, Codex.

**Статус и дата:** done, 2026-09-19.

**Проверенная версия архитектуры / существенные решения:** ARCHITECTURE.md v1.0 от
2026-09-13, §4.1, §5.2, §7.3, §8 и §11. Границы слоев не менялись. Сессию, manual
namespace и роль назначает backend. В БД хранятся только SHA-256 отпечатки токенов;
сессионный токен воспроизводимо выводится из короткоживущей pre-session и server secret, что
позволяет безопасно повторить потерянный ответ без хранения raw token. Это только
synthetic identity, а не Alfa ID и не доказательство происхождения звонка.

**Что сделано:** Реализованы identity-сущности и use cases для короткоживущей pre-session,
создания/восстановления demo-сессии и изменения пяти независимых consent scopes. Все
согласия по умолчанию revoked; изменение использует ожидаемую версию всего снимка.
Добавлены allowlisted synthetic-профили без client-controlled role, HMAC/CSRF-токены, in-memory и
SQLite repositories, Alembic-миграция users/sessions/pre_sessions/consents и audit старта/изменения
согласий. HTTP публикует `GET /session`, `POST /sessions/demo`, `PATCH /consents/{scope}`;
команды требуют CSRF и Idempotency-Key. Общие owner, namespace и role dependencies готовы для
будущих routes. OpenAPI, TypeScript-типы, JSON-примеры, runbook, README, AGENTS,
архитектурный status и конспект для защиты обновлены по фактическому состоянию.

**Файлы и артефакты:** `apps/backend/src/alpha_defense/{domain,application}/identity/`,
`apps/backend/src/alpha_defense/infrastructure/identity/mock/`, identity repositories/mappers/UoW,
`apps/backend/src/alpha_defense/transport/http/v1/{dependencies.py,routes/identity.py,
schemas/identity.py}`, `apps/backend/migrations/versions/20260918_0002_identity_sessions.py`,
identity unit/contract/integration tests, `contracts/{http,examples}/`, generated web API types,
runbook, README, AGENTS, architecture, defense guide и этот чеклист. Commit `4bd2341`
(«Реализовать demo-сессии и согласия») создан 2026-09-19; эта документационная фиксация
добавляет его точный hash перед отправкой обоих commit в `origin/main`.

**Проверки:**

- `uv lock --check`, cwd `apps/backend`, uv 0.11.7 / CPython 3.11.15, 2026-09-19:
  exit 0, lock согласован, 43 пакета.
- `ruff check`, `ruff format --check`, `mypy`, cwd `apps/backend`, 2026-09-19: все exit 0;
  strict-типизация прошла для 84 source/test/migration файлов.
- `pytest`, cwd `apps/backend`, 2026-09-19: exit 0, `78 passed`; два warning относятся
  к deprecation в закрепленной связке FastAPI/Starlette TestClient. Проверены инварианты
  domain, общий contract in-memory/SQLite, rollback неуспешной аутентификации, replay/conflict,
  CAS согласий, CSRF/idempotency/role guards, отсутствие raw tokens в БД, отзыв research-
  согласия и восстановление сессии после restart.
- `lint-imports --config pyproject.toml`, cwd `apps/backend`, 2026-09-19: exit 0,
  `4 kept, 0 broken`, 87 файлов и 264 зависимости.
- Два экспорта OpenAPI во временные файлы и `cmp` с committed contract,
  2026-09-19: все exit 0; байты совпали. `npm run generate:api` пересоздал типы
  из нового контракта.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run format:check`, `npm audit
  --audit-level=high`, cwd `apps/web`, 2026-09-19: все exit 0; Vitest `3 passed`,
  известных уязвимостей нет.
- `uv build --out-dir <temporary-directory>`, cwd `apps/backend`, 2026-09-19: exit 0,
  созданы sdist и wheel с identity и transport-модулями. `git diff --check`:
  exit 0.

**Что не проверено и почему:** Браузерный UI-flow не проверялся, потому что web-shell и
onboarding принадлежат P06; HTTP поведение проверено через ASGI integration. Реальные Alfa ID,
call attestation, SMS и персональные данные не подключались и не заявляются. Readiness 200 не
заявляется до валидированного каталога P07. Реальных UX-сессий и измерений не было.

**Остаток / блокер:** По P05 остатка и блокера нет.

**Условие разблокировки:** Не применимо.

**Следующее конкретное действие:** Начать [P06](#p06): web-shell, типизированный API-клиент с
cookies/CSRF/idempotency и русский onboarding на реальном session/consent API.

**Затронутые или повторно открытые зависимые задачи:** Закрыты P01–P05; активных задач нет.
P06 и P07 разблокированы; по порядку плана следующая P06.

<a id="log-2026-09-19-p06-01"></a>

#### 2026-09-19-P06-01

**Задача/исполнитель:** P06, Codex.

**Статус и дата:** done, 2026-09-19.

**Проверенная версия архитектуры / существенные решения:** ARCHITECTURE.md v1.0 от
2026-09-13, §5, §10 и §10.3. Направление `app → pages → features → shared` сохранено;
onboarding не импортирует соседние фичи и не содержит антифрод-политики. Server state хранится
в query cache, ввод формы — локально. Контракт session/consent не переписан вручную, а выведен
из сгенерированного OpenAPI. Будущие маршруты не имитируются готовыми страницами.

**Что сделано:** Добавлены запускаемый Vite/React shell, router, providers, error boundary и
query cache. Реализован fetch-клиент с cookie credentials, CSRF, Idempotency-Key и безопасным
Problem Details. Созданы русские форматтеры денег/московского времени, словарь текстов,
дизайн-токены и mobile-first стили. Onboarding получает реальную pre-session, создает
synthetic demo-сессию и управляет пятью согласиями по серверной ревизии без optimistic success.
Ошибки сохраняют выбранный профиль; режим «Демонстрация» виден в header и footer.

**Файлы и артефакты:** `apps/web/{index.html,vite.config.ts}`, `apps/web/src/{app,pages}/`,
`apps/web/src/shared/{api,formatting,i18n,styles,ui}/`,
`apps/web/src/features/onboarding/`, frontend unit/component tests, `README.md`, `AGENTS.md`,
runbook, архитектурный status, defense guide и этот чеклист. Реализация зафиксирована commit
`0ab9615` («Реализовать web-shell и onboarding»); документационная фиксация отправляется
следующим commit в `origin/main`.

**Проверки:**

- `npm ci`, cwd `apps/web`, Node 26.4.0 / npm 11.17.0, 2026-09-19: exit 0, установлено
  280 пакетов из lock-файла.
- `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npm run format:check`,
  cwd `apps/web`, 2026-09-19: все exit 0; Vitest `9 passed` в трех файлах, production build
  преобразовал 88 модулей. Application source проверяется с `skipLibCheck=false`; для test/
  config-проекта пропущены только несовместимые внешние declaration-файлы Vitest 5/Vite 8/
  jest-dom, собственные тесты остаются под strict TypeScript.
- `npm audit --audit-level=high`, cwd `apps/web`, 2026-09-19: exit 0, известных уязвимостей
  нет. `git diff --check`, cwd корня репозитория: exit 0.
- `pytest`, cwd `apps/backend`, принятый venv, 2026-09-19: exit 0, `78 passed`; два warning
  относятся к уже зафиксированной deprecation связки FastAPI/Starlette TestClient.
  `lint-imports --config pyproject.toml`: exit 0, `4 kept, 0 broken`.
- Ручной локальный browser/backend flow, 2026-09-19: `GET /session` 200,
  `POST /sessions/demo` 201, grant/revoke через `PATCH /consents/participate_in_research` 200;
  после каждого refresh сессия и серверное состояние согласия восстановились. Визуально
  проверены 360, 768, 1280 px и reflow, эквивалентный 200% масштабу на 1280 px. Найденный на
  768 px ранний двухколоночный breakpoint исправлен и перепроверен.

**Что не проверено и почему:** Playwright-браузеры и автоматизированный e2e-набор не
устанавливались: текущая приемка покрыта component-тестами и ручным сквозным прогоном, а
полный e2e появляется вместе с пользовательскими сценариями. Реальных UX-сессий с людьми не
было. Onboarding не доказывает готовность анализа риска, будущих страниц, Alfa ID или внешних
интеграций. Readiness 200 по-прежнему не заявляется до P07.

**Остаток / блокер:** По P06 остатка и блокера нет.

**Условие разблокировки:** Не применимо.

**Следующее конкретное действие:** Начать [P07](#p07): JSON Schema, безопасный загрузчик и
версионированный каталог синтетических данных, после которого readiness сможет стать зеленой.

**Затронутые или повторно открытые зависимые задачи:** Закрыты P01–P06; активных задач нет.
P07 разблокирован и является следующим пунктом по порядку плана.

<a id="log-2026-09-19-p07-01"></a>

#### 2026-09-19-P07-01

**Задача/исполнитель:** P07, Codex.

**Статус и дата:** done, 2026-09-19.

**Проверенная версия архитектуры / существенные решения:** ARCHITECTURE.md v1.0 от
2026-09-13, §3.1, §6.1, §11 и §12.1. Чтение файлов оставлено в infrastructure, application
получает plain snapshots через порт, domain не импортирует файловые API. JSON Schema задает
общий конверт и каталоги P07; payload-схемы будущих фич намеренно не придуманы заранее.
Readiness требует целиком валидный каталог, а не одно наличие файла политики.

**Что сделано:** Добавлены схемы demo-политики, trusted entities и общего fixture-конверта,
версионированные синтетические данные S01 для SMS и связанного threat URL. Loader ограничивает
размер и UTF-8 JSON, запрещает повторяющиеся ключи и нечисловые константы, проверяет schema,
версии, enums, canonical content/payload hash и hash связанного файла. Относительные ссылки
разрешаются только внутри `FIXTURE_ROOT`, включая защиту от `..` и symlink escape. Политика и
trusted entities преобразуются в типизированные application snapshots. Добавлен отдельный
validator CLI, `SCHEMA_ROOT` и полная проверка каталога в readiness; с мигрированной БД и
валидным каталогом `/health/ready` теперь отвечает 200.

**Файлы и артефакты:** `contracts/fixtures/*.schema.json`,
`content/{policies,trusted_entities}/*.json`, `fixtures/{communications,threats}/*.json`,
`application/ports/content.py`, `infrastructure/content/`, `scripts/validate_catalog.py`,
настройка bootstrap/readiness, unit/contract/integration/architecture tests, пример успешной
readiness, README, AGENTS, runbook, архитектурный status, defense guide и этот чеклист.
Реализация зафиксирована commit `7ac52fd` («Реализовать валидируемый каталог P07»); эта
документационная фиксация добавляет evidence перед отправкой обоих commit в `origin/main`.

**Проверки:**

- `uv lock --check`, cwd `apps/backend`, uv 0.11.7 / CPython 3.11.15, 2026-09-19:
  exit 0, lock согласован, 49 пакетов.
- `ruff check`, `ruff format --check`, `mypy`, cwd `apps/backend`, 2026-09-19: все exit 0;
  strict-типизация прошла для 89 source/test/migration файлов.
- `pytest`, cwd `apps/backend`, 2026-09-19: exit 0, `87 passed`; два warning относятся к
  deprecation в закрепленной связке FastAPI/Starlette TestClient. Отдельно проверены valid S01,
  поврежденный JSON, неизвестный enum и fixture version, выход ссылки за fixture root, неверные
  content/reference hash, зеленая readiness и запрет file-system API в domain.
- `lint-imports --config pyproject.toml`, cwd `apps/backend`, 2026-09-19: exit 0,
  `4 kept, 0 broken`, 91 файл и 281 зависимость.
- `python ../../scripts/validate_catalog.py`, cwd `apps/backend`, 2026-09-19: exit 0,
  policy `demo-risk-v1`, 2 fixtures, итоговый catalog sha256
  `de94df4320aeb7f050a8163b5af9c21721843ff637aec886d6cc8ba66b5a73e6`.
- Два экспорта OpenAPI во временные файлы и `cmp` между ними и committed contract,
  2026-09-19: все exit 0; HTTP-схема не изменилась. `uv build` создал sdist и wheel.
- `npm run lint`, `npm run typecheck`, `npm test -- --run`, `npm run build`,
  `npm run format:check`, `npm audit --audit-level=high`, cwd `apps/web`, 2026-09-19:
  все exit 0; Vitest `9 passed`, production build преобразовал 88 модулей, известных
  уязвимостей нет. `git diff --check`: exit 0.

**Что не проверено и почему:** Fixture-конверты еще не исполняются scenario runner и не
передаются анализаторам: эти способности принадлежат следующим карточкам. S01-данные не
являются готовой оценкой и не содержат expected→assessment shortcut. Реальные сообщения,
threat feeds, персональные данные и live-интеграции не подключались. Зеленая readiness
подтверждает локальные обязательные зависимости, но не готовность антифрод-потока.

**Остаток / блокер:** По P07 остатка и блокера нет.

**Условие разблокировки:** Не применимо.

**Следующее конкретное действие:** Начать [P08](#p08): реестр угроз с атомарной публикацией
валидированных снимков, статусами записей и детерминированным match.

**Затронутые или повторно открытые зависимые задачи:** Закрыты P01–P07; активных задач нет.
P08 и P09 разблокированы; по порядку плана следующая P08.
