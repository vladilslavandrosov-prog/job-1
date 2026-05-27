#!/bin/bash
# АС СКЛ v2.0 — Деплой на GitHub
set -e

TOKEN="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"
REPO="https://${TOKEN}@github.com/vladilslavandrosov-prog/job-1.git"

echo "=== АС СКЛ v2.0 → GitHub ==="
echo "Репозиторий: https://github.com/vladilslavandrosov-prog/job-1"

git init
git config user.email "as-skl@elektromontazh110.ru"
git config user.name "Электромонтаж-110"

# Удаляем старый remote если есть
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO"

git add .
git commit -m "feat: АС СКЛ v2.0 — полный стек (Flask + React + Leaflet + Docker)

Backend:
- Парсер DXF/CSV с конвертацией МСК→WGS-84 (Гаусс-Крюгер)
- Кадастровая сверка через PKK API Росреестра
- Геоанализ пересечений (ray-casting, без shapely)
- Матрица согласований: 14 типов → инстанции + сроки
- Генерация PDF-комплектов писем (ReportLab)
- REST API: /upload /analyze /generate /download
- 41 unit-тест (все пройдены)

Frontend (React + Leaflet, без сборки):
- Интерактивная карта трассы с кадастровой подложкой
- Кадастровые участки (цвет по форме собственности)
- Маркеры пересечений с popups
- Реестр согласований: выбор, статусы, генерация PDF
- Sidebar: Загрузка → Анализ → Согласования

Docker:
- docker-compose (backend + nginx)
- Один командой: docker-compose up --build

Заказчик: ООО «Электромонтаж-110»"

git branch -M main
git push -u origin main --force

echo ""
echo "✅ Готово!"
echo "🔗 https://github.com/vladilslavandrosov-prog/job-1"
