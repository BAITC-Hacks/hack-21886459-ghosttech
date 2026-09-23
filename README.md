# GhostTech

Python + FastAPI + SQLite. HTML, CSS и JavaScript без сборки; FastAPI отдаёт страницу и API с одного адреса.

## Структура

```text
backend/
  app/main.py       # API, подключение SQLite, раздача фронтенда
  data/             # База app.sqlite3 (создаётся при запуске, исключена из Git)
  tests/            # Проверка API и сохранения данных
  pyproject.toml    # Зависимости и инструменты разработки
  uv.lock           # Точные версии зависимостей
frontend/
  index.html
  styles.css
  app.js
```

## Запуск

Нужны Python 3.11+ и [uv](https://docs.astral.sh/uv/getting-started/installation/).
Из корня репозитория:

```sh
make setup
make dev
```

`make setup` создаёт `backend/.venv` и устанавливает зависимости по lock-файлу.
Откройте http://127.0.0.1:8000 — страница с демонстрацией сохранения заметок в SQLite.
Документация API: http://127.0.0.1:8000/docs. Остановка сервера: Ctrl+C.
Python автоматически перезагружается при изменениях; после изменения HTML/CSS/JS обновите страницу браузера.
Node.js, npm, сборка фронтенда и отдельный сервер базы данных не нужны.

Без `make` (например, в Windows):

```sh
uv sync --project backend --locked
uv run --project backend --locked uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

## Проверки

```sh
make test
make check
```

В редакторе выберите интерпретатор `backend/.venv/bin/python` (Windows: `backend/.venv/Scripts/python.exe`).
Тесты используют временную базу и не меняют рабочие данные.

## Настройки и API

По умолчанию база находится в `backend/data/app.sqlite3`. Для другого пути задайте переменную окружения `DATABASE_PATH` перед запуском. Относительный путь считается от текущего рабочего каталога. Файл `.env` автоматически не загружается.

- `GET /api/health` — проверка API и соединения с SQLite.
- `GET /api/notes` — список заметок.
- `POST /api/notes` — создание заметки: `{"text": "Первая идея"}`.
- `DELETE /api/notes/{id}` — удаление заметки.

Это локальный стартовый проект без авторизации. Команда разработки слушает только `127.0.0.1`.
