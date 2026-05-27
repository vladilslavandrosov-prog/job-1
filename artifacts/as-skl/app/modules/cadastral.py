"""
Модуль кадастровой сверки трассы КЛ.

Алгоритм:
1. Вычисляем bbox трассы с буфером 100 м
2. Запрашиваем API PKK Росреестра → список кадастровых участков
3. Для каждого участка проверяем пересечение с полилинией трассы
   (полигональная геометрия через numpy, без shapely)
4. Для каждого пересечения определяем форму собственности
5. Применяем матрицу → список инстанций согласования
"""

import math
import time
import logging
import requests
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from .dwg_parser import RoutePoint, compute_bbox_with_buffer, _haversine

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Структуры данных
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CadastralParcel:
    """Кадастровый земельный участок."""
    cn: str                    # Кадастровый номер
    area: float = 0.0          # Площадь, кв.м
    category: str = ""         # Категория земель
    owner_type: str = ""       # Форма собственности: private / municipal / federal / state
    owner_name: str = ""       # Наименование правообладателя (если доступно)
    polygon: List[Tuple[float,float]] = field(default_factory=list)  # [(lon, lat), ...]
    address: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Intersection:
    """Пересечение трассы с объектом."""
    object_type: str           # federal_road / gas / telecom / private_land / …
    object_name: str           # Человекочитаемое название объекта
    cadastral_number: str = "" # Кад. номер (если применимо)
    pk_start: float = 0.0      # Пикет начала пересечения, м
    pk_end: float = 0.0        # Пикет конца пересечения, м
    length_m: float = 0.0      # Длина пересечения / сближения, м
    distance_m: float = 0.0    # Минимальное расстояние (для зон сближения)
    owner_type: str = ""       # Форма собственности
    owner_name: str = ""
    severity: str = "warning"  # critical / warning / info
    geometry: List[Tuple[float,float]] = field(default_factory=list)


@dataclass
class ApprovalItem:
    """Одна позиция в реестре согласований."""
    id: int
    instance_name: str
    legal_basis: str
    review_days: Optional[int]
    priority: str              # critical / important / recommended
    intersection_ref: str      # На какое пересечение ссылается
    attachments: List[str] = field(default_factory=list)
    status: str = "pending"    # pending / generated / sent / approved / rejected


@dataclass
class CadastralResult:
    """Результат полного кадастрового анализа."""
    success: bool
    parcels: List[CadastralParcel] = field(default_factory=list)
    intersections: List[Intersection] = field(default_factory=list)
    approvals: List[ApprovalItem] = field(default_factory=list)
    critical_path_days: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    api_calls_made: int = 0
    processing_time_s: float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Геометрия (без shapely — только numpy/math)
# ──────────────────────────────────────────────────────────────────────────────

def _point_in_polygon(px: float, py: float, polygon: List[Tuple[float,float]]) -> bool:
    """Ray casting algorithm для проверки точки в полигоне."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def _segments_intersect(p1, p2, p3, p4) -> Optional[Tuple[float,float]]:
    """
    Проверяет пересечение отрезков (p1,p2) и (p3,p4).
    Возвращает точку пересечения или None.
    """
    x1,y1 = p1; x2,y2 = p2; x3,y3 = p3; x4,y4 = p4
    denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
    if abs(denom) < 1e-15:
        return None
    t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
    u = -((x1-x2)*(y1-y3) - (y1-y2)*(x1-x3)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        ix = x1 + t*(x2-x1)
        iy = y1 + t*(y2-y1)
        return (ix, iy)
    return None


def _polyline_polygon_intersection_length(
    route: List[RoutePoint],
    polygon: List[Tuple[float,float]]
) -> Tuple[float, float, float, List[Tuple[float,float]]]:
    """
    Вычисляет длину (в метрах) участка полилинии трассы внутри полигона.
    Возвращает (length_m, pk_start, pk_end, intersection_geom).
    """
    if not polygon or len(polygon) < 3:
        return 0.0, 0.0, 0.0, []

    inside_segments = []
    pk_starts = []
    pk_ends = []

    for i in range(len(route) - 1):
        a = route[i]
        b = route[i + 1]
        pa = (a.lon, a.lat)
        pb = (b.lon, b.lat)

        a_inside = _point_in_polygon(a.lon, a.lat, polygon)
        b_inside = _point_in_polygon(b.lon, b.lat, polygon)

        # Находим все пересечения сегмента с рёбрами полигона
        crosses = []
        for j in range(len(polygon)):
            p3 = polygon[j]
            p4 = polygon[(j+1) % len(polygon)]
            pt = _segments_intersect(pa, pb, p3, p4)
            if pt:
                # t — параметр на сегменте трассы
                dx = pb[0] - pa[0]
                dy = pb[1] - pa[1]
                denom = math.sqrt(dx**2 + dy**2)
                t = math.sqrt((pt[0]-pa[0])**2 + (pt[1]-pa[1])**2) / denom if denom else 0
                crosses.append((t, pt))
        crosses.sort(key=lambda x: x[0])

        # Строим участки внутри полигона
        seg_len = _haversine(a.lon, a.lat, b.lon, b.lat)
        seg_pk_len = b.pk - a.pk

        if a_inside and b_inside:
            inside_segments.append((pa, pb))
            pk_starts.append(a.pk)
            pk_ends.append(b.pk)
        elif a_inside and crosses:
            t, pt = crosses[0]
            inside_segments.append((pa, pt))
            pk_starts.append(a.pk)
            pk_ends.append(a.pk + t * seg_pk_len)
        elif b_inside and crosses:
            t, pt = crosses[-1]
            inside_segments.append((pt, pb))
            pk_starts.append(a.pk + t * seg_pk_len)
            pk_ends.append(b.pk)
        elif len(crosses) >= 2:
            t1, pt1 = crosses[0]
            t2, pt2 = crosses[-1]
            inside_segments.append((pt1, pt2))
            pk_starts.append(a.pk + t1 * seg_pk_len)
            pk_ends.append(a.pk + t2 * seg_pk_len)

    total_len = sum(
        _haversine(seg[0][0], seg[0][1], seg[1][0], seg[1][1])
        for seg in inside_segments
    )
    geom = [pt for seg in inside_segments for pt in seg]
    pk_s = min(pk_starts) if pk_starts else 0.0
    pk_e = max(pk_ends) if pk_ends else 0.0

    return round(total_len, 1), round(pk_s, 0), round(pk_e, 0), geom


def _min_distance_polyline_to_linestring(
    route: List[RoutePoint],
    line: List[Tuple[float,float]]
) -> Tuple[float, float]:
    """
    Минимальное расстояние (м) от полилинии трассы до отрезка line.
    Возвращает (min_dist_m, pk_at_min).
    """
    min_dist = float("inf")
    pk_at_min = 0.0

    for rp in route:
        for j in range(len(line)-1):
            # Расстояние от точки rp до отрезка line[j]–line[j+1]
            ax, ay = line[j]; bx, by = line[j+1]
            px, py = rp.lon, rp.lat
            dx, dy = bx-ax, by-ay
            t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / (dx**2+dy**2+1e-20)))
            nx, ny = ax + t*dx, ay + t*dy
            dist = _haversine(px, py, nx, ny)
            if dist < min_dist:
                min_dist = dist
                pk_at_min = rp.pk

    return round(min_dist, 1), round(pk_at_min, 0)


# ──────────────────────────────────────────────────────────────────────────────
# PKK API клиент (Росреестр)
# ──────────────────────────────────────────────────────────────────────────────

class PKKClient:
    """
    Клиент публичной кадастровой карты Росреестра.
    Документация неофициальная — API используется pkk.rosreestr.ru.
    """

    BASE = "https://pkk.rosreestr.ru"
    FEATURES_URL = BASE + "/api/features/{layer}"
    OBJECT_URL   = BASE + "/api/features/{layer}/{cn}"

    # Слои PKK
    LAYER_PARCELS  = 1   # Земельные участки
    LAYER_OKS      = 5   # Объекты капстроительства
    LAYER_ZONES    = 10  # Зоны с особыми условиями

    OWNER_TYPE_MAP = {
        "1": "federal",
        "2": "municipal",
        "3": "private",
        "4": "state",
        "5": "mixed",
    }
    CATEGORY_MAP = {
        "003001000000": "Земли нас. пунктов",
        "003002000000": "Земли с/х назначения",
        "003003000000": "Земли промышленности",
        "003004000000": "Земли особо охр. территорий",
        "003005000000": "Земли лесного фонда",
        "003006000000": "Земли водного фонда",
        "003007000000": "Земли запаса",
        "003008000000": "Земли транспорта",
    }

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AS-SKL/2.0 (cable-line-approval-system)",
            "Referer": "https://pkk.rosreestr.ru/",
            "Accept": "application/json",
        })
        self._call_count = 0

    def get_parcels_by_bbox(
        self,
        bbox: dict,
        limit: int = 200
    ) -> List[CadastralParcel]:
        """
        Запрашивает земельные участки в bbox.
        bbox: {min_lon, min_lat, max_lon, max_lat}
        """
        parcels = []
        bbox_str = (f"{bbox['min_lon']},{bbox['min_lat']},"
                    f"{bbox['max_lon']},{bbox['max_lat']}")

        # PKK делит ответ постранично, обходим
        page = 0
        while True:
            try:
                url = self.FEATURES_URL.format(layer=self.LAYER_PARCELS)
                params = {
                    "text":  "",
                    "bbox":  bbox_str,
                    "limit": min(limit, 40),  # PKK возвращает макс 40 за раз
                    "skip":  page * 40,
                    "inBbox": "true",
                }
                resp = self.session.get(url, params=params, timeout=self.timeout)
                self._call_count += 1

                if resp.status_code != 200:
                    logger.warning(f"PKK API returned {resp.status_code}")
                    break

                data = resp.json()
                features = data.get("features", [])
                if not features:
                    break

                for feat in features:
                    parcel = self._parse_parcel_feature(feat)
                    if parcel:
                        parcels.append(parcel)

                if len(features) < 40:
                    break  # Последняя страница

                page += 1
                time.sleep(0.3)  # Вежливая задержка

            except requests.exceptions.ConnectionError:
                logger.warning("PKK API недоступен — используем демо-данные")
                break
            except Exception as e:
                logger.warning(f"PKK API error: {e}")
                break

        return parcels

    def get_parcel_details(self, cn: str) -> Optional[dict]:
        """Детальная информация по кадастровому номеру."""
        try:
            url = self.OBJECT_URL.format(layer=self.LAYER_PARCELS, cn=cn)
            resp = self.session.get(url, timeout=self.timeout)
            self._call_count += 1
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"PKK detail error for {cn}: {e}")
        return None

    def _parse_parcel_feature(self, feat: dict) -> Optional[CadastralParcel]:
        attrs = feat.get("attrs", {})
        cn = attrs.get("cn", feat.get("id", ""))
        if not cn:
            return None

        # Геометрия (GeoJSON)
        geom = feat.get("geometry") or feat.get("extent")
        polygon = []
        if geom:
            polygon = self._extract_polygon(geom)

        owner_code = str(attrs.get("areatype", attrs.get("ownerType", "3")))
        cat_code = str(attrs.get("category_type", attrs.get("category", "")))

        return CadastralParcel(
            cn=cn,
            area=float(attrs.get("area_value", 0) or 0),
            category=self.CATEGORY_MAP.get(cat_code, cat_code or "Не определена"),
            owner_type=self.OWNER_TYPE_MAP.get(owner_code, "private"),
            owner_name=attrs.get("right_reg", attrs.get("name", "")),
            address=attrs.get("address", ""),
            polygon=polygon,
            raw=attrs,
        )

    def _extract_polygon(self, geom: dict) -> List[Tuple[float,float]]:
        """Извлекает список точек полигона из GeoJSON или extent-bbox."""

        # PKK иногда отдаёт extent-словарь напрямую (без вложения в geometry).
        # Определяем его по наличию xmin/ymin/xmax/ymax.
        if all(k in geom for k in ("xmin", "ymin", "xmax", "ymax")):
            xmin = geom["xmin"]; ymin = geom["ymin"]
            xmax = geom["xmax"]; ymax = geom["ymax"]
            # Защита: если координаты выглядят как Web Mercator (>200), конвертируем
            if abs(xmin) > 180 or abs(ymin) > 90:
                xmin, ymin = self._merc_to_wgs(xmin, ymin)
                xmax, ymax = self._merc_to_wgs(xmax, ymax)
            return [(xmin,ymin),(xmax,ymin),(xmax,ymax),(xmin,ymax)]

        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])

        if gtype == "Polygon" and coords:
            ring = coords[0]
            pts = [(c[0], c[1]) for c in ring]
            # Защита от Web Mercator в координатах полигона
            if pts and (abs(pts[0][0]) > 180 or abs(pts[0][1]) > 90):
                pts = [self._merc_to_wgs(x, y) for x, y in pts]
            return pts
        elif gtype == "MultiPolygon" and coords:
            rings = [ring for poly in coords for ring in poly]
            longest = max(rings, key=len) if rings else []
            pts = [(c[0], c[1]) for c in longest]
            if pts and (abs(pts[0][0]) > 180 or abs(pts[0][1]) > 90):
                pts = [self._merc_to_wgs(x, y) for x, y in pts]
            return pts
        elif gtype == "Point" and len(coords) >= 2:
            cx, cy = coords[0], coords[1]
            if abs(cx) > 180 or abs(cy) > 90:
                cx, cy = self._merc_to_wgs(cx, cy)
            r = 0.001  # ~100 м в градусах
            return [(cx-r,cy-r),(cx+r,cy-r),(cx+r,cy+r),(cx-r,cy+r)]

        # Fallback: extent вложен внутри geom
        if "extent" in geom:
            e = geom["extent"]
            xmin = e.get("xmin", 0); ymin = e.get("ymin", 0)
            xmax = e.get("xmax", 0); ymax = e.get("ymax", 0)
            if abs(xmin) > 180 or abs(ymin) > 90:
                xmin, ymin = self._merc_to_wgs(xmin, ymin)
                xmax, ymax = self._merc_to_wgs(xmax, ymax)
            return [(xmin,ymin),(xmax,ymin),(xmax,ymax),(xmin,ymax)]

        return []

    @staticmethod
    def _merc_to_wgs(x: float, y: float) -> Tuple[float, float]:
        """Конвертирует Web Mercator (EPSG:3857) → WGS-84 (lon, lat)."""
        lon = x * 180.0 / 20037508.342789244
        lat = math.degrees(2.0 * math.atan(math.exp(y * math.pi / 20037508.342789244)) - math.pi / 2)
        return round(lon, 7), round(lat, 7)


# ──────────────────────────────────────────────────────────────────────────────
# Демо-данные (когда PKK API недоступен)
# ──────────────────────────────────────────────────────────────────────────────

def _make_demo_parcels(bbox: dict) -> List[CadastralParcel]:
    """Генерирует реалистичные тестовые кадастровые участки для демо-режима."""
    cx = (bbox["min_lon"] + bbox["max_lon"]) / 2
    cy = (bbox["min_lat"] + bbox["max_lat"]) / 2
    dx = (bbox["max_lon"] - bbox["min_lon"]) / 5
    dy = (bbox["max_lat"] - bbox["min_lat"]) / 4

    def rect(lon0, lat0, w, h):
        return [(lon0,lat0),(lon0+w,lat0),(lon0+w,lat0+h),(lon0,lat0+h)]

    return [
        CadastralParcel(
            cn="77:01:0001023:44", area=14900, category="Земли нас. пунктов",
            owner_type="municipal", owner_name="г. Москва",
            polygon=rect(bbox["min_lon"], cy, dx*1.5, dy*1.2),
        ),
        CadastralParcel(
            cn="77:01:0001024:12", area=34000, category="Земли нас. пунктов",
            owner_type="private", owner_name="Иванов А.П.",
            polygon=rect(bbox["min_lon"]+dx*1.5, cy-dy*0.5, dx*1.2, dy*1.8),
        ),
        CadastralParcel(
            cn="77:01:0001025:07", area=122000, category="Земли транспорта",
            owner_type="federal", owner_name="РФ (Росавтодор)",
            polygon=rect(bbox["min_lon"]+dx*2.8, bbox["min_lat"], dx*0.4, dy*4),
        ),
        CadastralParcel(
            cn="77:01:0001025:08", area=95000, category="Земли нас. пунктов",
            owner_type="federal", owner_name="РФ (Росимущество)",
            polygon=rect(bbox["min_lon"]+dx*3.3, cy-dy, dx*1.0, dy*2),
        ),
        CadastralParcel(
            cn="77:01:0001026:01", area=18000, category="Земли нас. пунктов",
            owner_type="municipal", owner_name="г. Москва",
            polygon=rect(bbox["min_lon"]+dx*4.4, cy, dx*0.55, dy*1.0),
        ),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Главный анализатор
# ──────────────────────────────────────────────────────────────────────────────

class CadastralAnalyzer:
    """
    Выполняет полную кадастровую сверку трассы:
    1. Получает участки через PKK API (или демо-данные)
    2. Анализирует пересечения геометрически
    3. Применяет матрицу согласований
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.buffer_m = self.config.get("CADASTRAL_BUFFER_M", 100)
        self.approval_matrix = self.config.get("APPROVAL_MATRIX", {})
        self.pkk = PKKClient(timeout=self.config.get("PKK_TIMEOUT", 15))

    def analyze(self, route: List[RoutePoint], demo_mode: bool = False) -> CadastralResult:
        t0 = time.time()
        result = CadastralResult(success=False)

        if len(route) < 2:
            result.errors.append("Маршрут содержит менее 2 точек")
            return result

        # 1. Bbox с буфером
        bbox = compute_bbox_with_buffer(route, self.buffer_m)
        if not bbox:
            result.errors.append("Не удалось вычислить bbox трассы")
            return result

        # 2. Запрос кадастровых данных
        if demo_mode:
            parcels = _make_demo_parcels(bbox)
            result.warnings.append("Используются демо-данные (PKK API отключён)")
        else:
            parcels = self.pkk.get_parcels_by_bbox(bbox)
            result.api_calls_made = self.pkk._call_count
            if not parcels:
                result.warnings.append(
                    "PKK API вернул 0 участков — возможно API недоступен. "
                    "Переключаюсь на демо-данные."
                )
                parcels = _make_demo_parcels(bbox)

        result.parcels = parcels

        # 3. Анализ пересечений
        intersections = []
        approval_id = 1

        for parcel in parcels:
            if not parcel.polygon:
                continue

            length_m, pk_s, pk_e, geom = _polyline_polygon_intersection_length(
                route, parcel.polygon
            )

            if length_m < 1.0:  # Меньше 1 м — игнорируем
                continue

            # Определяем тип объекта для матрицы
            obj_type = self._classify_parcel(parcel)
            severity = "critical" if obj_type in (
                "federal_road", "railway", "gas", "telecom", "heritage"
            ) else "warning"

            intr = Intersection(
                object_type=obj_type,
                object_name=self._object_name(parcel),
                cadastral_number=parcel.cn,
                pk_start=pk_s, pk_end=pk_e,
                length_m=length_m,
                owner_type=parcel.owner_type,
                owner_name=parcel.owner_name,
                severity=severity,
                geometry=geom,
            )
            intersections.append(intr)

        result.intersections = intersections

        # 4. Матрица → реестр согласований
        approvals = []
        seen_instances = set()  # Дедупликация

        for intr in intersections:
            matrix_items = self.approval_matrix.get(intr.object_type, [])
            if not matrix_items:
                # Fallback по форме собственности
                matrix_items = self.approval_matrix.get(
                    f"{intr.owner_type}_land", []
                )

            for item in matrix_items:
                key = item["name"]
                if key in seen_instances:
                    continue
                seen_instances.add(key)

                attachments = self._default_attachments(intr.object_type)
                approvals.append(ApprovalItem(
                    id=approval_id,
                    instance_name=item["name"],
                    legal_basis=item["basis"],
                    review_days=item.get("days"),
                    priority=item.get("priority", "important"),
                    intersection_ref=(
                        f"{intr.object_name} · "
                        f"ПК {int(intr.pk_start//1000)}+{int(intr.pk_start%1000):03d} — "
                        f"ПК {int(intr.pk_end//1000)}+{int(intr.pk_end%1000):03d}"
                    ),
                    attachments=attachments,
                ))
                approval_id += 1

        result.approvals = approvals

        # 5. Критический путь
        critical_days = [
            a.review_days for a in approvals
            if a.priority == "critical" and a.review_days
        ]
        result.critical_path_days = max(critical_days) if critical_days else 0

        result.success = True
        result.processing_time_s = round(time.time() - t0, 2)
        return result

    # ── private ──────────────────────────────────────────────────────────────

    def _classify_parcel(self, parcel: CadastralParcel) -> str:
        """Определяет тип объекта для матрицы согласований."""
        cat = parcel.category.lower()
        name = (parcel.owner_name or "").lower()
        cn = parcel.cn.lower()

        if "транспорт" in cat or "росавтодор" in name or "автодор" in name:
            return "federal_road"
        if "лесн" in cat:
            return "forest"
        if "водн" in cat:
            return "water_object"

        owner = parcel.owner_type
        if owner == "private":
            return "private_land"
        if owner == "municipal":
            return "municipal_land"
        if owner in ("federal", "state"):
            return "federal_land"
        return "municipal_land"

    def _object_name(self, parcel: CadastralParcel) -> str:
        name = parcel.owner_name or ""
        return f"{parcel.cn} ({parcel.category})" + (f", {name}" if name else "")

    def _default_attachments(self, obj_type: str) -> List[str]:
        base = ["Письмо-запрос", "Выкопировка из плана (М 1:1000)", "Согласование ОПС"]
        extras = {
            "gas":        ["Профиль пересечения", "Выписка кабельного журнала"],
            "telecom":    ["Профиль пересечения"],
            "federal_road": ["Продольный профиль", "Выписка кабельного журнала", "ГИБДД ордер"],
            "railway":    ["Профиль пересечения", "Технические условия РЖД"],
            "private_land": ["Выписка из ЕГРН на участок"],
            "federal_land": ["Выписка из ЕГРН на участок"],
            "municipal_land": ["Выписка из ЕГРН на участок"],
        }
        return base + extras.get(obj_type, [])


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные сериализаторы
# ──────────────────────────────────────────────────────────────────────────────

def result_to_dict(result: CadastralResult) -> dict:
    """Сериализует CadastralResult в JSON-совместимый словарь."""
    def parcel_to_d(p: CadastralParcel):
        return {
            "cn": p.cn, "area": p.area, "category": p.category,
            "owner_type": p.owner_type, "owner_name": p.owner_name,
            "address": p.address,
            "polygon": p.polygon,
        }

    def intr_to_d(i: Intersection):
        return {
            "object_type": i.object_type,
            "object_name": i.object_name,
            "cadastral_number": i.cadastral_number,
            "pk_start": i.pk_start, "pk_end": i.pk_end,
            "length_m": i.length_m, "distance_m": i.distance_m,
            "owner_type": i.owner_type, "owner_name": i.owner_name,
            "severity": i.severity,
        }

    def approval_to_d(a: ApprovalItem):
        return {
            "id": a.id,
            "instance_name": a.instance_name,
            "legal_basis": a.legal_basis,
            "review_days": a.review_days,
            "priority": a.priority,
            "intersection_ref": a.intersection_ref,
            "attachments": a.attachments,
            "status": a.status,
        }

    return {
        "success": result.success,
        "parcels": [parcel_to_d(p) for p in result.parcels],
        "intersections": [intr_to_d(i) for i in result.intersections],
        "approvals": [approval_to_d(a) for a in result.approvals],
        "summary": {
            "total_parcels": len(result.parcels),
            "total_intersections": len(result.intersections),
            "total_approvals": len(result.approvals),
            "critical_approvals": sum(1 for a in result.approvals if a.priority == "critical"),
            "important_approvals": sum(1 for a in result.approvals if a.priority == "important"),
            "critical_path_days": result.critical_path_days,
            "processing_time_s": result.processing_time_s,
        },
        "errors": result.errors,
        "warnings": result.warnings,
    }
