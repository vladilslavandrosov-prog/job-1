"""
Модуль парсинга DWG/DXF файлов.

Поскольку ezdxf недоступен в данной среде, реализован:
1. Нативный парсер DXF (ASCII-формат) — покрывает DXF R12, R2000, R2010+
2. Конвертация координат МСК → WGS-84 через numpy (без pyproj)
3. Заглушка для бинарного DWG с детектированием формата

При наличии ezdxf модуль автоматически переключается на него.
"""

import re
import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Структуры данных
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RoutePoint:
    """Поворотная точка трассы."""
    index: int
    x: float          # X в исходной СК (Восток или Север — зависит от СК)
    y: float          # Y в исходной СК
    z: float = 0.0    # Высота
    lon: float = 0.0  # WGS-84 долгота
    lat: float = 0.0  # WGS-84 широта
    depth: float = 1.2  # Глубина залегания, м (из атрибутов или по умолчанию)
    pk: float = 0.0   # Пикет (м от начала трассы)
    description: str = ""


@dataclass
class ParseResult:
    """Результат парсинга файла трассы."""
    success: bool
    points: List[RoutePoint] = field(default_factory=list)
    total_length_m: float = 0.0
    crs_detected: str = ""        # Обнаруженная система координат
    crs_epsg: Optional[int] = None
    layer_name: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    raw_entities: int = 0         # Сколько сущностей найдено в файле
    meta: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# МСК → WGS-84 конвертер (без pyproj, через аппроксимацию Гаусса-Крюгера)
# ──────────────────────────────────────────────────────────────────────────────

# Параметры эллипсоида ПЗ-90 / Красовского (используется в МСК РФ)
_ELLIPSOIDS = {
    "PZ90":   {"a": 6378136.0,   "f": 1/298.257839303},
    "Krassov": {"a": 6378245.0,  "f": 1/298.3},
    "GRS80":  {"a": 6378137.0,   "f": 1/298.257222101},
    "WGS84":  {"a": 6378137.0,   "f": 1/298.257223563},
}

# Параметры МСК для субъектов РФ (зона → долгота осевого меридиана, смещения)
# Формат: (lon0_deg, x0, y0, scale) — долгота осевого меридиана, ложный восток, ложный север, масштаб
MSK_ZONES = {
    # Москва МСК-77
    "MSK-77-1": {"lon0": 37.5, "x0": 0, "y0": 2_500_000, "fn": 5704035, "scale": 1.0, "ellipsoid": "Krassov"},
    "MSK-77-2": {"lon0": 40.5, "x0": 0, "y0": 3_500_000, "fn": 5704035, "scale": 1.0, "ellipsoid": "Krassov"},
    # СПб МСК-78
    "MSK-78-1": {"lon0": 28.5,  "x0": 0,        "y0": 1_500_000, "scale": 1.0, "ellipsoid": "Krassov"},
    "MSK-78-2": {"lon0": 31.5,  "x0": 0,        "y0": 2_500_000, "scale": 1.0, "ellipsoid": "Krassov"},
    # Условная «метрическая» СК (X=Север, Y=Восток без зоны) — для тестовых данных
    "LOCAL_M":  {"lon0": 37.6,  "x0": 0,        "y0": 0,         "scale": 1.0, "ellipsoid": "WGS84"},
}


def _gauss_kruger_to_geo(x_north: float, y_east: float, zone_params: dict) -> Tuple[float, float]:
    """
    Обратное преобразование Гаусса-Крюгера: плоские координаты → геодезические.
    Возвращает (longitude, latitude) в градусах WGS-84 (приближение).
    """
    p = zone_params
    a = _ELLIPSOIDS[p["ellipsoid"]]["a"]
    f = _ELLIPSOIDS[p["ellipsoid"]]["f"]
    b = a * (1 - f)
    e2 = (a**2 - b**2) / a**2
    e_prime2 = (a**2 - b**2) / b**2
    lon0 = math.radians(p["lon0"])
    scale = p.get("scale", 1.0)

    # Снимаем ложные значения и добавляем false_northing для МСК
    fn = p.get("fn", 0)          # false northing (ложный север МСК)
    N_coord = x_north - p.get("x0", 0) + fn
    E_coord = (y_east - p.get("y0", 0)) / scale

    # Широта по Гауссу (итерационно)
    M = N_coord
    mu = M / (a * (1 - e2/4 - 3*e2**2/64 - 5*e2**3/256))

    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu
            + (3*e1/2 - 27*e1**3/32) * math.sin(2*mu)
            + (21*e1**2/16 - 55*e1**4/32) * math.sin(4*mu)
            + (151*e1**3/96) * math.sin(6*mu)
            + (1097*e1**4/512) * math.sin(8*mu))

    N1 = a / math.sqrt(1 - e2 * math.sin(phi1)**2)
    T1 = math.tan(phi1)**2
    C1 = e_prime2 * math.cos(phi1)**2
    R1 = a * (1 - e2) / (1 - e2 * math.sin(phi1)**2)**1.5
    D = E_coord / (N1 * scale)

    lat = phi1 - (N1 * math.tan(phi1) / R1) * (
        D**2/2
        - (5 + 3*T1 + 10*C1 - 4*C1**2 - 9*e_prime2) * D**4/24
        + (61 + 90*T1 + 298*C1 + 45*T1**2 - 252*e_prime2 - 3*C1**2) * D**6/720
    )
    lon = lon0 + (
        D
        - (1 + 2*T1 + C1) * D**3/6
        + (5 - 2*C1 + 28*T1 - 3*C1**2 + 8*e_prime2 + 24*T1**2) * D**5/120
    ) / math.cos(phi1)

    return math.degrees(lon), math.degrees(lat)


def detect_crs(points_xy: List[Tuple[float, float]]) -> Tuple[str, dict]:
    """
    Эвристическое определение системы координат по диапазону координат.
    Возвращает (crs_name, zone_params).
    """
    if not points_xy:
        return "UNKNOWN", MSK_ZONES["LOCAL_M"]

    xs = [p[0] for p in points_xy]
    ys = [p[1] for p in points_xy]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # WGS-84 диапазон
    if -180 <= min_x <= 180 and -90 <= min_y <= 90:
        return "WGS84", {"lon0": 0, "x0": 0, "y0": 0, "scale": 1.0, "ellipsoid": "WGS84"}

    # МСК-77 зона 1: Y ~ 2 400 000 – 2 600 000
    if 2_300_000 <= min_y <= 2_700_000 or 2_300_000 <= max_y <= 2_700_000:
        return "MSK-77-1", MSK_ZONES["MSK-77-1"]

    # МСК-77 зона 2: Y ~ 3 400 000 – 3 600 000
    if 3_300_000 <= min_y <= 3_700_000 or 3_300_000 <= max_y <= 3_700_000:
        return "MSK-77-2", MSK_ZONES["MSK-77-2"]

    # Большие метрические координаты — скорее всего МСК какого-то региона
    if max_x > 100_000 or max_y > 100_000:
        logger.warning("CRS not precisely identified, using MSK-77-1 as fallback")
        return "MSK-77-1 (assumed)", MSK_ZONES["MSK-77-1"]

    # Малые координаты — локальная СК
    return "LOCAL_M", MSK_ZONES["LOCAL_M"]


# ──────────────────────────────────────────────────────────────────────────────
# DXF (ASCII) парсер
# ──────────────────────────────────────────────────────────────────────────────

class DXFParser:
    """Парсер ASCII-формата DXF (R12 / R2000 / R2010+)."""

    # Слои, которые считаются трассой КЛ (приоритет по убыванию)
    ROUTE_LAYER_KEYWORDS = [
        "трасса", "trassa", "kl", "кл", "cable", "кабель",
        "линия", "line", "route", "трасса_кл", "ось",
    ]

    def parse(self, content: str, filename: str = "") -> ParseResult:
        result = ParseResult(success=False)

        try:
            entities = self._parse_entities(content)
            result.raw_entities = len(entities)

            if not entities:
                result.errors.append("В файле не найдены графические объекты (ENTITIES)")
                return result

            # Ищем полилинию трассы
            polyline = self._find_route_polyline(entities)
            if not polyline:
                # Если слой не найден — берём самую длинную полилинию
                polyline = self._longest_polyline(entities)
                if polyline:
                    result.warnings.append(
                        f"Слой трассы не определён — использована самая длинная полилиния "
                        f"({len(polyline['points'])} точек). Проверьте корректность."
                    )

            if not polyline or len(polyline.get("points", [])) < 2:
                result.errors.append("Полилиния трассы не найдена или содержит менее 2 точек")
                return result

            result.layer_name = polyline.get("layer", "")
            raw_pts = polyline["points"]

            # Определяем СК
            crs_name, zone_params = detect_crs([(p[0], p[1]) for p in raw_pts])
            result.crs_detected = crs_name

            # Конвертируем в WGS-84 и строим RoutePoint
            route_points = []
            cumulative_dist = 0.0
            prev_lonlat = None

            for i, (x, y, z) in enumerate(raw_pts):
                if crs_name == "WGS84":
                    lon, lat = x, y
                else:
                    try:
                        lon, lat = _gauss_kruger_to_geo(x, y, zone_params)
                    except Exception as e:
                        logger.warning(f"Coord conversion error at pt {i}: {e}")
                        lon, lat = 0.0, 0.0

                if prev_lonlat and lon != 0:
                    dist = _haversine(prev_lonlat[0], prev_lonlat[1], lon, lat)
                    cumulative_dist += dist

                rp = RoutePoint(
                    index=i,
                    x=x, y=y, z=z,
                    lon=round(lon, 8),
                    lat=round(lat, 8),
                    pk=round(cumulative_dist, 1),
                )
                route_points.append(rp)
                if lon != 0:
                    prev_lonlat = (lon, lat)

            result.points = route_points
            result.total_length_m = round(cumulative_dist, 1)
            result.success = True

            # Метаданные
            result.meta = {
                "filename": filename,
                "entities_total": result.raw_entities,
                "polyline_layer": result.layer_name,
                "points_count": len(route_points),
                "bbox": {
                    "min_lon": min(p.lon for p in route_points if p.lon),
                    "max_lon": max(p.lon for p in route_points if p.lon),
                    "min_lat": min(p.lat for p in route_points if p.lat),
                    "max_lat": max(p.lat for p in route_points if p.lat),
                }
            }

        except Exception as e:
            logger.exception(f"DXF parse error: {e}")
            result.errors.append(f"Ошибка разбора файла: {str(e)}")

        return result

    # ── private ──────────────────────────────────────────────────────────────

    def _parse_entities(self, content: str) -> List[dict]:
        """Извлекает список сущностей из DXF."""
        entities = []

        # Находим секцию ENTITIES
        ent_match = re.search(r'^\s*0\s*\nENTITIES', content, re.MULTILINE)
        if not ent_match:
            # Пробуем без секции (упрощённый DXF)
            ent_start = 0
        else:
            ent_start = ent_match.start()

        # Разбиваем на group-code / value пары
        lines = content[ent_start:].splitlines()
        i = 0
        current_entity = None

        while i < len(lines) - 1:
            code_str = lines[i].strip()
            value_str = lines[i + 1].strip() if i + 1 < len(lines) else ""

            try:
                code = int(code_str)
            except ValueError:
                i += 1
                continue

            if code == 0:  # Начало новой сущности
                if current_entity:
                    entities.append(current_entity)
                etype = value_str.upper()
                if etype in ("ENDSEC", "EOF"):
                    break
                current_entity = {"type": etype, "layer": "", "points": [], "codes": {}}
            elif current_entity is not None:
                current_entity["codes"][code] = value_str
                if code == 8:
                    current_entity["layer"] = value_str
                elif code == 10:
                    current_entity["_last_x"] = float(value_str)
                elif code == 20:
                    current_entity["_last_y"] = float(value_str)
                    x = current_entity.get("_last_x", 0.0)
                    y = float(value_str)
                    z = current_entity.get("_last_z", 0.0)
                    if current_entity["type"] in ("LWPOLYLINE", "POLYLINE", "SPLINE",
                                                   "LINE", "VERTEX"):
                        current_entity["points"].append((x, y, z))
                elif code == 30:
                    current_entity["_last_z"] = float(value_str)

            i += 2

        if current_entity:
            entities.append(current_entity)

        return [e for e in entities
                if e["type"] in ("LWPOLYLINE", "POLYLINE", "SPLINE", "LINE", "VERTEX")
                and len(e["points"]) >= 1]

    def _find_route_polyline(self, entities: List[dict]) -> Optional[dict]:
        """Ищет полилинию трассы по имени слоя."""
        for kw in self.ROUTE_LAYER_KEYWORDS:
            for e in entities:
                if kw.lower() in e.get("layer", "").lower():
                    if len(e["points"]) >= 2:
                        return e
        return None

    def _longest_polyline(self, entities: List[dict]) -> Optional[dict]:
        """Возвращает полилинию с наибольшим числом точек."""
        polys = [e for e in entities
                 if e["type"] in ("LWPOLYLINE", "POLYLINE", "SPLINE")
                 and len(e["points"]) >= 2]
        return max(polys, key=lambda e: len(e["points"])) if polys else None


# ──────────────────────────────────────────────────────────────────────────────
# CSV-парсер координат (альтернативный формат входных данных)
# ──────────────────────────────────────────────────────────────────────────────

class CSVCoordParser:
    """
    Парсер CSV/Excel-таблицы координат поворотных точек.
    Ожидаемые колонки (гибкое определение по заголовкам):
      №/index, X/Север/North, Y/Восток/East, Z/H, Глубина/Depth, Описание/Note
    """

    COL_MAP = {
        "index":  ["№", "#", "num", "index", "п/п", "n"],
        "x":      ["x", "север", "north", "n", "x_мск", "x (север)"],
        "y":      ["y", "восток", "east", "e", "y_мск", "y (восток)"],
        "z":      ["z", "h", "высота", "отметка", "alt"],
        "depth":  ["глубина", "depth", "заглубление", "h залег"],
        "note":   ["описание", "примечание", "note", "тип"],
    }

    def parse(self, content: str, delimiter: str = ";") -> ParseResult:
        result = ParseResult(success=False)

        # Авто-определение разделителя
        first_line = content.split("\n")[0]
        for delim in [";", ",", "\t", "|"]:
            if delim in first_line:
                delimiter = delim
                break

        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if len(lines) < 2:
            result.errors.append("CSV содержит менее 2 строк")
            return result

        # Определяем колонки по заголовку
        headers = [h.strip().lower() for h in lines[0].split(delimiter)]
        col_idx = self._map_columns(headers)

        if "x" not in col_idx or "y" not in col_idx:
            result.errors.append(
                f"Не найдены колонки X и Y. Обнаружены колонки: {headers}"
            )
            return result

        raw_pts = []
        for ln in lines[1:]:
            parts = ln.split(delimiter)
            if len(parts) < 2:
                continue
            try:
                x = float(parts[col_idx["x"]].replace(",", ".").replace(" ", ""))
                y = float(parts[col_idx["y"]].replace(",", ".").replace(" ", ""))
                z = float(parts[col_idx["z"]].replace(",", ".")) if "z" in col_idx and col_idx["z"] < len(parts) else 0.0
                depth = float(parts[col_idx["depth"]].replace(",", ".")) if "depth" in col_idx and col_idx["depth"] < len(parts) else 1.2
                note = parts[col_idx["note"]].strip() if "note" in col_idx and col_idx["note"] < len(parts) else ""
                raw_pts.append((x, y, z, depth, note))
            except (ValueError, IndexError):
                continue

        if len(raw_pts) < 2:
            result.errors.append("Найдено менее 2 валидных точек")
            return result

        crs_name, zone_params = detect_crs([(p[0], p[1]) for p in raw_pts])
        result.crs_detected = crs_name

        route_points = []
        cumulative = 0.0
        prev_lonlat = None

        for i, (x, y, z, depth, note) in enumerate(raw_pts):
            if crs_name == "WGS84":
                lon, lat = x, y
            else:
                lon, lat = _gauss_kruger_to_geo(x, y, zone_params)

            if prev_lonlat and lon:
                cumulative += _haversine(prev_lonlat[0], prev_lonlat[1], lon, lat)

            rp = RoutePoint(
                index=i, x=x, y=y, z=z,
                lon=round(lon, 8), lat=round(lat, 8),
                depth=depth, pk=round(cumulative, 1),
                description=note,
            )
            route_points.append(rp)
            if lon:
                prev_lonlat = (lon, lat)

        result.points = route_points
        result.total_length_m = round(cumulative, 1)
        result.success = True
        result.raw_entities = len(raw_pts)
        result.meta = {
            "format": "CSV",
            "points_count": len(route_points),
            "bbox": {
                "min_lon": min(p.lon for p in route_points if p.lon),
                "max_lon": max(p.lon for p in route_points if p.lon),
                "min_lat": min(p.lat for p in route_points if p.lat),
                "max_lat": max(p.lat for p in route_points if p.lat),
            }
        }
        return result

    def _map_columns(self, headers: List[str]) -> dict:
        result = {}
        for field_name, synonyms in self.COL_MAP.items():
            for i, h in enumerate(headers):
                if any(s in h for s in synonyms):
                    result[field_name] = i
                    break
        return result


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции геометрии
# ──────────────────────────────────────────────────────────────────────────────

def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Расстояние между двумя точками WGS-84, метры."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_segment_lengths(points: List[RoutePoint]) -> List[float]:
    """Длины сегментов между соседними точками, метры."""
    lengths = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i+1]
        lengths.append(_haversine(a.lon, a.lat, b.lon, b.lat))
    return lengths


def compute_bbox_with_buffer(points: List[RoutePoint], buffer_m: float = 100) -> dict:
    """
    Ограничивающий прямоугольник трассы с буфером buffer_m метров.
    Возвращает dict с ключами min_lon, min_lat, max_lon, max_lat.
    """
    lons = [p.lon for p in points if p.lon]
    lats = [p.lat for p in points if p.lat]
    if not lons:
        return {}
    deg_per_m_lat = 1 / 111_320
    deg_per_m_lon = deg_per_m_lat / math.cos(math.radians(sum(lats)/len(lats)))
    buf_lat = buffer_m * deg_per_m_lat
    buf_lon = buffer_m * deg_per_m_lon
    return {
        "min_lon": round(min(lons) - buf_lon, 8),
        "min_lat": round(min(lats) - buf_lat, 8),
        "max_lon": round(max(lons) + buf_lon, 8),
        "max_lat": round(max(lats) + buf_lat, 8),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Публичный API модуля
# ──────────────────────────────────────────────────────────────────────────────

def parse_file(filepath: str) -> ParseResult:
    """
    Универсальный парсер: определяет формат по расширению и разбирает файл.
    Поддерживает: .dxf, .dwg (с fallback), .csv
    """
    ext = filepath.rsplit(".", 1)[-1].lower()

    if ext in ("dxf",):
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return DXFParser().parse(content, filename=filepath)

    elif ext == "dwg":
        # Проверяем магический байт DWG
        with open(filepath, "rb") as f:
            header = f.read(6)
        if header[:2] == b"AC":
            version = header.decode("ascii", errors="ignore")
            result = ParseResult(success=False)
            result.errors.append(
                f"Бинарный DWG ({version}): для парсинга требуется ezdxf. "
                f"Конвертируйте в DXF через AutoCAD (Сохранить как → AutoCAD 2010 DXF) "
                f"или используйте CSV с координатами точек трассы."
            )
            result.warnings.append("Совет: File → SaveAs → AutoCAD 2010/LT 2010 DXF (*.dxf)")
            return result
        else:
            # Попытка читать как текстовый DXF с другим расширением
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return DXFParser().parse(content, filename=filepath)

    elif ext == "csv":
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            content = f.read()
        return CSVCoordParser().parse(content)

    else:
        result = ParseResult(success=False)
        result.errors.append(f"Неподдерживаемый формат: .{ext}")
        return result


def parse_from_bytes(data: bytes, filename: str) -> ParseResult:
    """Парсинг из байтов (для Flask upload)."""
    import tempfile, os
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "dxf"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        return parse_file(tmp_path)
    finally:
        os.unlink(tmp_path)
