# АС СКЛ v2.0 — Система согласования кабельных линий

Система автоматизации согласования строительства кабельных линий: геоаналитика пересечений трассы с кадастром, автоматический подбор согласующих инстанций по нормативной матрице и генерация пакета писем на согласование.

## Run & Operate

- `python artifacts/as-skl/run.py` — запуск Flask-сервера (порт из `$PORT`, по умолчанию 5000)
- Healthcheck: `GET /api/v1/health`

## Stack

- Python 3.12, Flask 3.1
- NumPy, Pandas, ReportLab
- Frontend: React 18 + Leaflet (CDN, без сборки, JSX через Babel-standalone)
- In-memory хранилище проектов (→ PostgreSQL в roadmap)

## Where things live

- `artifacts/as-skl/` — Flask backend + frontend
  - `app/__init__.py` — фабрика приложения
  - `app/config.py` — конфиг: матрица согласований, охранные зоны
  - `app/routes.py` — REST API endpoints
  - `app/modules/dwg_parser.py` — парсер DXF/CSV, конвертация МСК→WGS-84
  - `app/modules/cadastral.py` — PKK API Росреестра, геоанализ пересечений
  - `app/modules/pdf_generator.py` — генерация PDF-пакетов (ReportLab)
  - `app/templates/index.html` — React SPA (фронтенд)

## API

```
GET  /api/v1/health                      — healthcheck
POST /api/v1/upload                      — загрузка DXF/CSV/JSON с координатами
POST /api/v1/analyze/<pid>               — кадастровая сверка (demo_mode: true/false)
POST /api/v1/generate/<pid>              — генерация PDF-пакета
GET  /api/v1/download/<pid>              — скачать PDF
GET  /api/v1/project/<pid>               — данные проекта
GET  /api/v1/projects                    — список проектов
PATCH /api/v1/project/<pid>/approval/<id> — обновить статус согласования
```

## Architecture decisions

- Flask-приложение с единым Python-процессом: и фронтенд, и API
- React SPA компилируется Babel прямо в браузере — не требует сборки
- Геоанализ без shapely/pyproj — только numpy/math (Гаусс-Крюгер)
- PKK API Росреестра с автоматическим откатом на демо-данные при недоступности

## Product

- Загрузка трасс: DXF/DWG (AutoCAD), CSV с координатами, JSON API
- Кадастровая сверка: 9+ типов участков, форма собственности через PKK Росреестра
- Анализ пересечений: охранные зоны, Ray-casting + intersection алгоритм
- Матрица согласований: автоматическое определение инстанций и сроков
- Интерактивная карта: трасса КЛ, кадастр, маркеры пересечений (Leaflet)
- Генерация PDF-комплектов писем (ReportLab)

## User preferences

- Язык общения: русский

## Авторизация

Весь сайт (кроме `/api/v1/health`) закрыт HTTP Basic Auth на одного тестового
пользователя — это демо-заглушка, а не полноценная многопользовательская
система. Логин/пароль задаются переменными окружения `AUTH_USERNAME` /
`AUTH_PASSWORD`; без них используются дефолты для локальной разработки
(`demo` / `demo2026`) — **обязательно переопределите их на реальном деплое**.

## Gotchas

- Babel транспилирует JSX в браузере — при первой загрузке интерфейс появляется через 2-3 сек.
- Данные хранятся в памяти (in-memory) — перезапуск сервера сбрасывает все проекты
- DejaVu-шрифты для PDF ищутся в `/usr/share/fonts/truetype/dejavu/` — при отсутствии автоматически используется Helvetica
- Матрица согласований запрашивает у ПКК Росреестра только слой земельных участков — пересечения с газопроводом/ж-д/связью/охраняемыми объектами (ОКС) в реальном режиме не определяются, несмотря на упоминание в разделе Product
