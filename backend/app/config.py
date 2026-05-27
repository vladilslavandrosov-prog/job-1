"""Конфигурация АС СКЛ"""
import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "as-skl-dev-secret-2025")
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB upload limit
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
    ALLOWED_EXTENSIONS = {"dwg", "dxf", "pdf", "xlsx", "xls", "csv"}

    # Кадастровый API Росреестра (PKK)
    PKK_API_BASE = "https://pkk.rosreestr.ru/api"
    PKK_TIMEOUT = 15  # секунды
    CADASTRAL_BUFFER_M = 100  # буфер bbox вокруг трассы, метры

    # Охранные зоны (нормативные, метры) по видам сетей
    PROTECTIVE_ZONES = {
        "gas_high":   50,   # газопровод высокого давления
        "gas_medium": 15,   # среднего давления
        "gas_low":     4,   # низкого давления
        "heat":        5,   # теплотрасса
        "telecom":     2,   # кабели связи
        "water":      10,   # водопровод/канализация
        "power_6_10": 10,   # КЛ 6–10 кВ
        "power_110":  20,   # КЛ 110 кВ
    }

    # Матрица: тип объекта → инстанция (упрощённая, расширяется в БД)
    APPROVAL_MATRIX = {
        "federal_road":   [
            {"name": "Росавтодор / ФКУ", "basis": "ФЗ №257", "days": 30, "priority": "critical"},
            {"name": "УГИБДД МВД",       "basis": "Регламент МВД", "days": 10, "priority": "critical"},
        ],
        "regional_road":  [
            {"name": "Министерство транспорта субъекта", "basis": "ФЗ №257", "days": 30, "priority": "critical"},
        ],
        "railway":        [
            {"name": "РЖД (региональный филиал)", "basis": "Приказ МПС", "days": 45, "priority": "critical"},
        ],
        "gas":            [
            {"name": "ГРО (Газпром / региональный)", "basis": "СП 62.13330", "days": 45, "priority": "critical"},
        ],
        "heat":           [
            {"name": "Теплоснабжающая организация", "basis": "СП 124.13330", "days": 30, "priority": "important"},
        ],
        "telecom":        [
            {"name": "Оператор связи", "basis": "ФЗ №126", "days": 30, "priority": "critical"},
        ],
        "water":          [
            {"name": "Водоканал", "basis": "СанПиН", "days": 30, "priority": "important"},
        ],
        "private_land":   [
            {"name": "Частный собственник", "basis": "ГК РФ ст.274", "days": None, "priority": "important"},
        ],
        "municipal_land": [
            {"name": "Администрация района", "basis": "ЗК РФ ст.22", "days": 30, "priority": "important"},
        ],
        "federal_land":   [
            {"name": "Росимущество", "basis": "ФЗ №218", "days": 30, "priority": "important"},
        ],
        "forest":         [
            {"name": "Рослесхоз / лесничество", "basis": "ЛК РФ", "days": 30, "priority": "important"},
        ],
        "water_object":   [
            {"name": "Росрыболовство", "basis": "ВК РФ", "days": 30, "priority": "important"},
        ],
        "heritage":       [
            {"name": "Минкультуры / ГИОП", "basis": "ФЗ №73", "days": 45, "priority": "critical"},
        ],
    }
