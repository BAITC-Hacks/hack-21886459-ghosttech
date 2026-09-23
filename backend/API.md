# Контракт API

Базовый URL: `http://127.0.0.1:8000/api`. Авторизации, токенов и cookies нет.
Тело POST/PATCH — JSON с `Content-Type: application/json`. Все ID — строки.
Ошибки: `{"detail":"сообщение"}`; ошибки Pydantic (`422`) содержат массив `detail` с `loc`, `msg`, `type`.

## Карточка и рейтинг

Поля `card`: `title`, `topic`, `context`, `need`, `users`, `data`, `constraints`, `expected_result`, `success_criteria`, `contact`, `interaction_format`. Все — строки, отсутствующие поля становятся пустыми. Название ограничено 200 символами, тема — 100, контакт — 500, прочие поля — 5000.

`POST /tasks/analyze`:

```json
{"draft_text":"Нужен учёт посещаемости кружков","topic":"образование"}
```

Ответ: `questions: [{id, field, question}]`, `filled_fields`, `missing_fields`, `mode: "demo" | "openai"`. Вопросов от 3 до 5, идентификаторы и поля уникальны.

`POST /tasks/build-card`:

```json
{"draft_text":"Нужен учёт посещаемости","topic":"образование","answers":[{"question_id":"q1","field":"data","answer":"Есть журнал посещений"}]}
```

Ответ: `card`, массив строк `warnings` и `mode: "demo" | "openai"`. Поле `field` ограничено ключами карточки, повторные ответы для одного поля запрещены.

`POST /tasks/score`: `{"card": {...}}`. Ответ: `score`, `level`, `breakdown: [{field,label,max,earned,reason}]`, `missing: [{field,hint,potential_points}]`.

В режиме OpenAI помощник возвращает `429` при лимите, `503` при отсутствии ключа или доступа, `504` при тайм-ауте и `502` при сбое провайдера или некорректном ответе. Поле `detail` содержит сообщение на русском; ключи, исходный ответ провайдера и внутренние исключения не возвращаются. Ошибки не переключают запрос в деморежим.

`GET /health`: `{status, database, mode, ai_configured}`. Режим отражает конфигурацию, а `ai_configured` — наличие непустого ключа; это не проверка связи с OpenAI.

## Задачи

`POST /tasks`:

```json
{"card":{"title":"Учёт посещаемости","topic":"образование","need":"Быстро видеть пропуски занятий"},"confirmed":true}
```

Возвращает `201`: `{id, card, confirmed, score, level, breakdown, missing, created_at, updated_at, proposals}`.
Для публикации обязательны непустые `title` и `topic`. При `confirmed: false` можно сохранять незаполненную карточку.

`GET /tasks?topic=образование&level=ready&offset=0&limit=50` возвращает **массив** сводок:
`{id, title, topic, need, confirmed, score, level, proposals_count, created_at}`.
`limit` от 1 до 100. Пустые фильтры следует опускать. Сортировка: рейтинг по убыванию, дата по убыванию, ID. Для управления неопубликованными карточками используйте `include_drafts=true`.

`GET /tasks/{id}` возвращает полную карточку с откликами.

`PATCH /tasks/{id}` принимает `card` и/или `confirmed`. Переданное `card` **заменяет все поля карточки**, а не выполняет вложенный частичный merge. Не передавайте вычисляемые `score` и `level`. Изменение карточки снимает подтверждение, если в том же запросе не передано `confirmed: true`.

## Команды

`GET /teams?offset=0&limit=50` — массив `{id, name, interests, skills, tech, points}`.

`POST /teams` и `PATCH /teams/{id}`:

```json
{"name":"GhostTech","interests":["образование"],"skills":["аналитика"],"tech":["Python"]}
```

При PATCH передайте полную редактируемую форму команды. `points` вычисляется сервером и не принимается в запросе.

## Отклики и прогресс

`POST /tasks/{id}/proposals`:

```json
{"team_id":"team1","idea":"Сделать журнал посещений","plan":"Прототип, проверка, запуск","deadline":"2027-01-10","prototype_url":"https://example.com/prototype"}
```

Ссылка необязательна; допускается только HTTP/HTTPS. Ответ `201`:
`{id, task_id, team_id, idea, plan, deadline, prototype_url, status, stages_done, created_at}`.
`GET /tasks/{id}/proposals` возвращает массив таких объектов.

`GET /proposals?team_id={id}&offset=0&limit=100` возвращает отклики выбранной команды
для вкладки «Команда». Без `team_id` возвращает все отклики. `limit` от 1 до 100;
неизвестная команда — `404`. Статус и подтверждённые этапы берутся из базы данных.

`PATCH /proposals/{id}/decision`: `{"decision":"accepted"}` или `{"decision":"rejected"}`. Повторное решение — `409`.

`POST /proposals/{id}/progress`: `{"stage":"prototype"}` / `testing` / `final`.
Ответ `201`: `{proposal_id, team_id, stages_done, points_total, team_points_total}`.
`points_total` — баллы этого отклика, `team_points_total` — вся сумма команды. Подтвердить этап можно только у принятого отклика. Порядок подтверждения этапов не ограничен; каждый учитывается единожды.

## Подключение фронтенда

Готовый клиент — `frontend/api.js`: методы возвращают Promise, вызывайте их с `await` и обрабатывайте исключения. HTTP-статус доступен как `error.status`. Работающий интерфейс использует API; `mock.js` больше не подключён.

При запуске на `8080` используется API на `8000` с тем же хостом. Для другого адреса задайте `window.API_BASE_URL` до подключения клиента и добавьте origin страницы в `FRONTEND_ORIGINS`. При раздаче через FastAPI все запросы идут на относительный `/api`.


## Демонстрационные участники и темы

- `GET /api/participants?role=business|student&team_id=…&offset=0&limit=50` — публичные
  профили; роль и команда необязательны, максимальный размер страницы 100.
- `GET /api/topics` — темы опубликованных задач с `tasks_count`.
- `GET /api/tasks` дополнительно принимает `owner_id` и `search` (название и потребность).
- Ответы задач дополнены `owner`, `is_demo` и `work_tags`; команды — `members` и `is_demo`.
- `POST /api/tasks` принимает необязательный `owner_id` предпринимателя. При отсутствии
  автора прежний контракт сохраняется; студент автором бизнес-задачи быть не может.
- Редактирование карточки не меняет автора. Профили не являются учётными записями.


### Фильтрация и порядок каталога

`GET /api/tasks` поддерживает дополнительные параметры:

- `work_type` — точное совпадение с тегом типа работы (например, `аналитика`).
- `proposals=any|none|has` — любые задачи, без откликов или с откликами.
- `sort=score_desc|score_asc|newest|oldest|proposals_desc` — рейтинг по убыванию
  (по умолчанию), рейтинг по возрастанию, новые, старые или больше откликов.

Эти параметры сочетаются с темой, уровнем, заказчиком и поиском. Фильтрация и
сортировка выполняются до `offset`/`limit`; ID обеспечивает стабильный порядок
при равных значениях. Формат ответа остаётся списком задач.
