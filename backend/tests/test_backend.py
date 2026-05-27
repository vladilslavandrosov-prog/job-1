"""
Unit-тесты АС СКЛ — парсинг DWG и кадастровая сверка.
Запуск: python -m pytest tests/test_backend.py -v
  или:  python tests/test_backend.py
"""
import sys, os, json, math, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.modules.dwg_parser import (
    DXFParser, CSVCoordParser, detect_crs, _gauss_kruger_to_geo,
    _haversine, compute_bbox_with_buffer, RoutePoint, MSK_ZONES
)
from app.modules.cadastral import (
    CadastralAnalyzer, _point_in_polygon, _segments_intersect,
    _polyline_polygon_intersection_length, _make_demo_parcels,
    compute_bbox_with_buffer as cbwb
)
from app import create_app


# ──────────────────────────────────────────────────────────────────────────────
# Тесты: геометрия
# ──────────────────────────────────────────────────────────────────────────────

class TestGeometry(unittest.TestCase):

    def test_haversine_zero(self):
        """Расстояние до самой себя = 0."""
        self.assertAlmostEqual(_haversine(37.6, 55.7, 37.6, 55.7), 0, places=3)

    def test_haversine_known(self):
        """Москва–Санкт-Петербург ≈ 634 км."""
        dist = _haversine(37.617, 55.755, 30.315, 59.939)
        self.assertGreater(dist, 600_000)
        self.assertLess(dist, 700_000)

    def test_point_in_polygon_inside(self):
        square = [(0,0),(1,0),(1,1),(0,1)]
        self.assertTrue(_point_in_polygon(0.5, 0.5, square))

    def test_point_in_polygon_outside(self):
        square = [(0,0),(1,0),(1,1),(0,1)]
        self.assertFalse(_point_in_polygon(2.0, 2.0, square))

    def test_point_in_polygon_edge(self):
        square = [(0,0),(1,0),(1,1),(0,1)]
        # Точки на краях могут быть inside или outside — проверяем только крайние
        self.assertFalse(_point_in_polygon(-0.001, 0.5, square))

    def test_segments_intersect_crossing(self):
        """Перпендикулярные отрезки пересекаются."""
        pt = _segments_intersect((0,0),(1,0),(0.5,-0.5),(0.5,0.5))
        self.assertIsNotNone(pt)
        self.assertAlmostEqual(pt[0], 0.5, places=5)
        self.assertAlmostEqual(pt[1], 0.0, places=5)

    def test_segments_intersect_parallel(self):
        """Параллельные отрезки не пересекаются."""
        pt = _segments_intersect((0,0),(1,0),(0,1),(1,1))
        self.assertIsNone(pt)

    def test_segments_intersect_non_overlapping(self):
        """Коллинеарные непересекающиеся отрезки."""
        pt = _segments_intersect((0,0),(1,0),(2,0),(3,0))
        self.assertIsNone(pt)


# ──────────────────────────────────────────────────────────────────────────────
# Тесты: системы координат
# ──────────────────────────────────────────────────────────────────────────────

class TestCRS(unittest.TestCase):

    def test_detect_wgs84(self):
        """Координаты в диапазоне WGS-84 → WGS84."""
        crs, _ = detect_crs([(37.6, 55.7), (37.8, 55.9)])
        self.assertEqual(crs, "WGS84")

    def test_detect_msk77_zone1(self):
        """Координаты МСК-77 зона 1 → MSK-77-1."""
        pts = [(471234.0, 2410118.0), (471712.0, 2411912.0)]
        crs, _ = detect_crs(pts)
        self.assertIn("MSK-77", crs)

    def test_gauss_kruger_roundtrip(self):
        """
        Прямое и обратное преобразование Гаусса-Крюгера:
        точка МСК-77 → WGS-84 → проверяем попадание в разумный диапазон (Москва).
        """
        x, y = 471234.520, 2410118.340
        zone = MSK_ZONES["MSK-77-1"]
        lon, lat = _gauss_kruger_to_geo(x, y, zone)
        # Москва: lon ≈ 37–38, lat ≈ 55–56
        self.assertGreater(lon, 36.0)
        self.assertLess(lon, 40.0)
        self.assertGreater(lat, 54.0)  # Moscow area
        self.assertLess(lat, 57.0)

    def test_bbox_with_buffer(self):
        """bbox с буфером 100 м шире исходного."""
        pts = [
            RoutePoint(0, 0,0,0, lon=37.6, lat=55.7),
            RoutePoint(1, 0,0,0, lon=37.8, lat=55.9),
        ]
        bbox = compute_bbox_with_buffer(pts, 100)
        self.assertLess(bbox["min_lon"], 37.6)
        self.assertGreater(bbox["max_lon"], 37.8)
        self.assertLess(bbox["min_lat"], 55.7)
        self.assertGreater(bbox["max_lat"], 55.9)


# ──────────────────────────────────────────────────────────────────────────────
# Тесты: DXF парсер
# ──────────────────────────────────────────────────────────────────────────────

SAMPLE_DXF = """  0
SECTION
  2
ENTITIES
  0
LWPOLYLINE
  8
ТРАССА_КЛ
 90
        4
 70
     0
 10
471234.520
 20
2410118.340
 30
0.0
 10
471586.220
 20
2410823.450
 30
0.0
 10
471712.450
 20
2411284.110
 30
0.0
 10
472054.110
 20
2412194.320
 30
0.0
  0
ENDSEC
  0
EOF
"""

class TestDXFParser(unittest.TestCase):

    def setUp(self):
        self.parser = DXFParser()

    def test_parse_basic(self):
        result = self.parser.parse(SAMPLE_DXF, "test.dxf")
        self.assertTrue(result.success, f"Parse failed: {result.errors}")
        self.assertEqual(len(result.points), 4)

    def test_layer_detection(self):
        result = self.parser.parse(SAMPLE_DXF)
        self.assertIn("ТРАССА", result.layer_name.upper())

    def test_coordinate_conversion(self):
        result = self.parser.parse(SAMPLE_DXF)
        for pt in result.points:
            self.assertGreater(pt.lon, 36.0, "Долгота вне диапазона Москвы")
            self.assertLess(pt.lon, 40.0)
            self.assertGreater(pt.lat, 54.0, "Широта вне диапазона Москвы")
            self.assertLess(pt.lat, 57.0)

    def test_total_length(self):
        result = self.parser.parse(SAMPLE_DXF)
        self.assertGreater(result.total_length_m, 0, "Длина трассы = 0")
        self.assertLess(result.total_length_m, 50_000, "Длина трассы нереально большая")

    def test_pks_monotonic(self):
        """Пикеты строго возрастают."""
        result = self.parser.parse(SAMPLE_DXF)
        pks = [p.pk for p in result.points]
        for i in range(len(pks)-1):
            self.assertLessEqual(pks[i], pks[i+1])

    def test_empty_file(self):
        result = self.parser.parse("", "empty.dxf")
        self.assertFalse(result.success)
        self.assertTrue(len(result.errors) > 0)

    def test_wrong_layer_fallback(self):
        """Если слой не найден — берётся самая длинная полилиния."""
        dxf_no_layer = SAMPLE_DXF.replace("ТРАССА_КЛ", "MISC_LAYER")
        result = self.parser.parse(dxf_no_layer)
        self.assertTrue(result.success)
        self.assertTrue(len(result.warnings) > 0)


# ──────────────────────────────────────────────────────────────────────────────
# Тесты: CSV парсер
# ──────────────────────────────────────────────────────────────────────────────

SAMPLE_CSV = """№;X (Север);Y (Восток);Z;Глубина;Описание
1;471234.520;2410118.340;0;1.2;ТП-1 (начало)
2;471358.910;2410118.340;0;1.2;Поворот Т-2
3;471586.220;2410823.450;0;1.5;Пересечение дороги
4;471712.450;2411284.110;0;1.2;Прямолинейный участок
5;472054.110;2412194.320;0;1.2;ТП-2 (конец)
"""

class TestCSVParser(unittest.TestCase):

    def test_parse_csv(self):
        result = CSVCoordParser().parse(SAMPLE_CSV)
        self.assertTrue(result.success, f"CSV parse failed: {result.errors}")
        self.assertEqual(len(result.points), 5)

    def test_depths_correct(self):
        result = CSVCoordParser().parse(SAMPLE_CSV)
        self.assertAlmostEqual(result.points[0].depth, 1.2)
        self.assertAlmostEqual(result.points[2].depth, 1.5)

    def test_descriptions(self):
        result = CSVCoordParser().parse(SAMPLE_CSV)
        self.assertIn("ТП-1", result.points[0].description)

    def test_too_few_rows(self):
        result = CSVCoordParser().parse("X;Y\n100;200\n")
        self.assertFalse(result.success)


# ──────────────────────────────────────────────────────────────────────────────
# Тесты: кадастровый анализатор (демо-режим)
# ──────────────────────────────────────────────────────────────────────────────

def _make_test_route() -> list:
    """Тестовый маршрут из 8 точек (Москва, МСК-77-1)."""
    from app.modules.dwg_parser import _gauss_kruger_to_geo, MSK_ZONES
    coords_msk = [
        (471234.520, 2410118.340),
        (471358.910, 2410118.340),
        (471358.910, 2410529.780),
        (471586.220, 2410823.450),
        (471712.450, 2411284.110),
        (471712.450, 2411912.890),
        (471938.670, 2412194.320),
        (472054.110, 2412194.320),
    ]
    zone = MSK_ZONES["MSK-77-1"]
    pts = []
    cum = 0.0
    prev = None
    for i, (x, y) in enumerate(coords_msk):
        lon, lat = _gauss_kruger_to_geo(x, y, zone)
        if prev:
            cum += _haversine(prev[0], prev[1], lon, lat)
        pts.append(RoutePoint(
            index=i, x=x, y=y, z=0,
            lon=round(lon,8), lat=round(lat,8),
            depth=1.2, pk=round(cum,1),
        ))
        prev = (lon, lat)
    return pts


class TestCadastralAnalyzer(unittest.TestCase):

    def setUp(self):
        from app.config import Config
        self.config = {
            "CADASTRAL_BUFFER_M": 100,
            "PKK_TIMEOUT": 15,
            "APPROVAL_MATRIX": Config.APPROVAL_MATRIX,
        }
        self.route = _make_test_route()

    def test_demo_mode_returns_parcels(self):
        analyzer = CadastralAnalyzer(config=self.config)
        result = analyzer.analyze(self.route, demo_mode=True)
        self.assertTrue(result.success, f"Analyze failed: {result.errors}")
        self.assertGreater(len(result.parcels), 0, "Нет кадастровых участков")

    def test_intersections_found(self):
        analyzer = CadastralAnalyzer(config=self.config)
        result = analyzer.analyze(self.route, demo_mode=True)
        self.assertGreater(len(result.intersections), 0, "Пересечения не найдены")

    def test_approvals_generated(self):
        analyzer = CadastralAnalyzer(config=self.config)
        result = analyzer.analyze(self.route, demo_mode=True)
        self.assertGreater(len(result.approvals), 0, "Согласования не сформированы")

    def test_approvals_have_required_fields(self):
        analyzer = CadastralAnalyzer(config=self.config)
        result = analyzer.analyze(self.route, demo_mode=True)
        for a in result.approvals:
            self.assertTrue(a.instance_name, "Нет названия инстанции")
            self.assertTrue(a.legal_basis, "Нет правового основания")
            self.assertIn(a.priority, ("critical","important","recommended"))

    def test_no_duplicate_instances(self):
        """Одна инстанция не должна появляться дважды."""
        analyzer = CadastralAnalyzer(config=self.config)
        result = analyzer.analyze(self.route, demo_mode=True)
        names = [a.instance_name for a in result.approvals]
        self.assertEqual(len(names), len(set(names)), f"Дубли: {names}")

    def test_critical_path_positive(self):
        analyzer = CadastralAnalyzer(config=self.config)
        result = analyzer.analyze(self.route, demo_mode=True)
        self.assertGreaterEqual(result.critical_path_days, 0)

    def test_empty_route(self):
        analyzer = CadastralAnalyzer(config=self.config)
        result = analyzer.analyze([], demo_mode=True)
        self.assertFalse(result.success)

    def test_single_point(self):
        analyzer = CadastralAnalyzer(config=self.config)
        result = analyzer.analyze(self.route[:1], demo_mode=True)
        self.assertFalse(result.success)


# ──────────────────────────────────────────────────────────────────────────────
# Тесты: Flask API
# ──────────────────────────────────────────────────────────────────────────────

class TestFlaskAPI(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_health(self):
        r = self.client.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["status"], "ok")

    def test_upload_json_valid(self):
        payload = {
            "project": "Тест",
            "points": [
                {"x": 471234.52, "y": 2410118.34},
                {"x": 471586.22, "y": 2410823.45},
                {"x": 472054.11, "y": 2412194.32},
            ]
        }
        r = self.client.post("/api/v1/upload",
                             data=json.dumps(payload),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data["success"])
        self.assertIn("project_id", data)
        self.assertEqual(data["route_summary"]["points_count"], 3)
        return data["project_id"]

    def test_upload_too_few_points(self):
        payload = {"points": [{"x": 100, "y": 200}]}
        r = self.client.post("/api/v1/upload",
                             data=json.dumps(payload),
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_upload_no_body(self):
        r = self.client.post("/api/v1/upload")
        self.assertEqual(r.status_code, 400)

    def test_analyze_demo(self):
        # Сначала загружаем маршрут
        payload = {
            "project": "Тест-анализ",
            "points": [
                {"x": 471234.52, "y": 2410118.34},
                {"x": 471586.22, "y": 2410823.45},
                {"x": 471712.45, "y": 2411284.11},
                {"x": 472054.11, "y": 2412194.32},
            ]
        }
        r = self.client.post("/api/v1/upload",
                             data=json.dumps(payload),
                             content_type="application/json")
        pid = json.loads(r.data)["project_id"]

        # Запускаем анализ
        r2 = self.client.post(f"/api/v1/analyze/{pid}",
                              data=json.dumps({"demo_mode": True}),
                              content_type="application/json")
        self.assertEqual(r2.status_code, 200)
        data = json.loads(r2.data)
        self.assertTrue(data["success"])
        self.assertIn("summary", data)
        self.assertGreater(data["summary"]["total_parcels"], 0)
        self.assertGreater(data["summary"]["total_approvals"], 0)

    def test_analyze_not_found(self):
        r = self.client.post("/api/v1/analyze/nonexistent-id",
                             data=json.dumps({"demo_mode": True}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_get_project(self):
        payload = {
            "project": "Тест-get",
            "points": [
                {"x": 471234.52, "y": 2410118.34},
                {"x": 472054.11, "y": 2412194.32},
            ]
        }
        r = self.client.post("/api/v1/upload",
                             data=json.dumps(payload),
                             content_type="application/json")
        pid = json.loads(r.data)["project_id"]

        r2 = self.client.get(f"/api/v1/project/{pid}")
        self.assertEqual(r2.status_code, 200)
        data = json.loads(r2.data)
        self.assertEqual(data["id"], pid)
        self.assertEqual(data["name"], "Тест-get")

    def test_list_projects(self):
        r = self.client.get("/api/v1/projects")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn("projects", data)

    def test_main_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("АС СКЛ".encode("utf-8"), r.data)

    def test_upload_csv_file(self):
        csv_content = (
            "№;X (Север);Y (Восток);Z;Глубина\n"
            "1;471234.520;2410118.340;0;1.2\n"
            "2;471586.220;2410823.450;0;1.5\n"
            "3;472054.110;2412194.320;0;1.2\n"
        ).encode("utf-8")
        from io import BytesIO
        r = self.client.post("/api/v1/upload",
                             data={"file": (BytesIO(csv_content), "route.csv"),
                                   "project": "CSV-тест"},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["route_summary"]["points_count"], 3)


# ──────────────────────────────────────────────────────────────────────────────
# Запуск
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for cls in [
        TestGeometry,
        TestCRS,
        TestDXFParser,
        TestCSVParser,
        TestCadastralAnalyzer,
        TestFlaskAPI,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
