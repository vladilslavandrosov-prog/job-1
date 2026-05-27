# АС СКЛ v2.0 — Полный стек

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-green)
![React](https://img.shields.io/badge/React-18-61DAFB)
![Leaflet](https://img.shields.io/badge/Leaflet-1.9-199900)
![Tests](https://img.shields.io/badge/tests-41%20passed-brightgreen)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED)

> **Заказчик:** ООО «Электромонтаж-110»

ИИ-система автоматизации согласования строительства кабельных линий.

## Быстрый запуск (Docker)

```bash
git clone https://github.com/vladilslavandrosov-prog/job-1.git
cd job-1
docker-compose up --build
# → http://localhost
```

## Запуск без Docker

```bash
cd backend
pip install -r requirements.txt
python run.py
# → http://localhost:5000
```

## Функциональность

### Что умеет система

| Шаг | Функция | Технология |
|-----|---------|-----------|
| 1 | Загрузка DXF/CSV/JSON с координатами трассы | Flask multipart / JSON API |
| 2 | Парсинг + конвертация МСК→WGS-84 | Гаусс-Крюгер (numpy/math) |
| 3 | Кадастровая сверка: 9 участков, форма собственности | PKK API Росреестра |
| 4 | Анализ пересечений с охранными зонами | Ray-casting + segment intersection |
| 5 | Реестр согласований: матрица → инстанции + сроки | Конфигурируемая матрица |
| 6 | Интерактивная карта трассы с кадастром | React + Leaflet.js |
| 7 | Генерация PDF-комплектов писем | ReportLab |
| 8 | Трекинг статусов согласований | REST PATCH API |

### Интерфейс

**Sidebar (3 вкладки):**
- **Загрузка** — drag-and-drop DXF/CSV или демо-данные
- **Анализ** — запуск кадастровой сверки (реальный PKK или демо)
- **Согласования** — реестр с выбором, статусами, генерацией PDF

**Карта (Leaflet):**
- Трасса КЛ с поворотными точками
- Кадастровые участки (цвет по форме собственности)
- Маркеры пересечений (! — красный критично, оранжевый — важно)
- Всплывающие карточки по клику

## Структура

```
job-1/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py          # Матрица согласований, охранные зоны
│   │   ├── routes.py          # REST API эндпоинты
│   │   ├── templates/
│   │   │   └── index.html     # React SPA (без сборки)
│   │   └── modules/
│   │       ├── dwg_parser.py  # DXF/CSV парсер, МСК→WGS-84
│   │       ├── cadastral.py   # PKK API, геоанализ, реестр
│   │       └── pdf_generator.py  # Генерация PDF-комплектов
│   ├── tests/
│   │   └── test_backend.py    # 41 unit-тест
│   ├── Dockerfile
│   └── requirements.txt
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
└── README.md
```

## API

```
GET  /api/v1/health                     — healthcheck
POST /api/v1/upload                     — загрузка файла или JSON точек
POST /api/v1/analyze/<pid>              — кадастровая сверка
POST /api/v1/generate/<pid>             — генерация PDF
GET  /api/v1/download/<pid>             — скачать PDF
GET  /api/v1/project/<pid>              — данные проекта
GET  /api/v1/projects                   — список проектов
PATCH /api/v1/project/<pid>/approval/<id> — обновить статус согласования
```

## Тесты

```bash
cd backend
python tests/test_backend.py
# Ran 41 tests — OK
```

## Дорожная карта

- [x] Backend: парсинг DWG/DXF/CSV
- [x] Backend: кадастровая сверка (PKK API + геоанализ)
- [x] Backend: матрица согласований, реестр
- [x] Backend: генерация PDF-комплектов (ReportLab)
- [x] Frontend: карта трассы (React + Leaflet)
- [x] Frontend: реестр согласований (выбор, статусы)
- [x] Docker-compose (backend + nginx)
- [ ] База данных (PostgreSQL + SQLAlchemy)
- [ ] Аутентификация пользователей (JWT)
- [ ] OCR PDF ОПС (Tesseract)
- [ ] Интеграция с ЕСИА / ЭЦП

---

MIT License · ООО «Электромонтаж-110» · 2025
