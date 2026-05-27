"""
АС СКЛ v2.0 — полный REST API
"""
import os, uuid, json, logging
from flask import Blueprint, request, jsonify, render_template_string, send_file
from .modules.dwg_parser import parse_from_bytes, RoutePoint
from .modules.cadastral import CadastralAnalyzer, result_to_dict
from .modules.pdf_generator import PDFGenerator

logger = logging.getLogger(__name__)
main_bp = Blueprint("main", __name__)
api_bp  = Blueprint("api",  __name__)

_PROJECTS: dict = {}   # in-memory store (→ Redis/Postgres в продакшн)


# ── UI ────────────────────────────────────────────────────────────────────────
@main_bp.route("/")
def index():
    path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    html = open(path, encoding="utf-8").read()
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}

@main_bp.route("/favicon.ico")
def favicon(): return "", 204


# ── Health ────────────────────────────────────────────────────────────────────
@api_bp.route("/health")
def health():
    return jsonify({"status": "ok", "version": "2.0.0",
                    "service": "АС СКЛ"})


# ── Upload ────────────────────────────────────────────────────────────────────
@api_bp.route("/upload", methods=["POST"])
def upload():
    route_points, parse_errors, parse_warnings, crs_detected = [], [], [], ""
    project_name = "Новый проект"
    meta = {}

    if "file" in request.files:
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "Файл не выбран"}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower()
        allowed = {"dwg","dxf","pdf","csv","xlsx"}
        if ext not in allowed:
            return jsonify({"error": f"Формат .{ext} не поддерживается"}), 400
        data = f.read()
        from .modules.dwg_parser import parse_from_bytes
        result = parse_from_bytes(data, f.filename)
        route_points = result.points
        parse_errors = result.errors
        parse_warnings = result.warnings
        crs_detected = result.crs_detected
        project_name = request.form.get("project", f.filename.rsplit(".",1)[0])
        meta = result.meta
        if not result.success or not route_points:
            return jsonify({"success": False, "errors": parse_errors,
                            "warnings": parse_warnings}), 422

    elif request.is_json:
        body = request.get_json(silent=True) or {}
        raw_points = body.get("points", [])
        project_name = body.get("project", project_name)
        if len(raw_points) < 2:
            return jsonify({"error": "Минимум 2 точки"}), 400
        from .modules.dwg_parser import detect_crs, _gauss_kruger_to_geo, _haversine
        xy = [(p.get("x",0), p.get("y",0)) for p in raw_points]
        crs_name, zone_params = detect_crs(xy)
        crs_detected = crs_name
        cum = 0.0; prev = None
        for i, pt in enumerate(raw_points):
            x = float(pt.get("x", pt.get("lon", 0)))
            y = float(pt.get("y", pt.get("lat", 0)))
            if crs_name == "WGS84": lon, lat = x, y
            else: lon, lat = _gauss_kruger_to_geo(x, y, zone_params)
            if prev: cum += _haversine(prev[0], prev[1], lon, lat)
            prev = (lon, lat)
            route_points.append(RoutePoint(
                index=i, x=x, y=y, z=float(pt.get("z",0)),
                lon=round(lon,8), lat=round(lat,8),
                depth=float(pt.get("depth",1.2)), pk=round(cum,1),
                description=pt.get("description",""),
            ))
        meta = {"format": "JSON", "points_count": len(route_points)}
    else:
        return jsonify({"error": "Ожидается файл или JSON"}), 400

    pid = str(uuid.uuid4())
    _PROJECTS[pid] = {
        "id": pid, "name": project_name, "status": "parsed",
        "route": [_rp(p) for p in route_points],
        "total_length_m": route_points[-1].pk if route_points else 0,
        "crs": crs_detected, "cadastral_result": None, "meta": meta,
    }
    return jsonify({
        "success": True, "project_id": pid, "project_name": project_name,
        "route_summary": {
            "points_count": len(route_points),
            "total_length_m": _PROJECTS[pid]["total_length_m"],
            "crs_detected": crs_detected,
            "bbox": meta.get("bbox"),
        },
        "route": [_rp(p) for p in route_points],
        "warnings": parse_warnings,
        "next_step": f"/api/v1/analyze/{pid}",
    })


# ── Analyze ───────────────────────────────────────────────────────────────────
@api_bp.route("/analyze/<pid>", methods=["POST"])
def analyze(pid):
    project = _PROJECTS.get(pid)
    if not project: return jsonify({"error": "Проект не найден"}), 404
    body = request.get_json(silent=True) or {}
    demo = body.get("demo_mode", False)
    from flask import current_app
    config = {
        "CADASTRAL_BUFFER_M": 100,
        "PKK_TIMEOUT": 15,
        "APPROVAL_MATRIX": current_app.config.get("APPROVAL_MATRIX", {}),
    }
    route = [_drp(p) for p in project["route"]]
    analyzer = CadastralAnalyzer(config=config)
    cad = analyzer.analyze(route, demo_mode=demo)
    rd = result_to_dict(cad)
    project["cadastral_result"] = rd
    project["status"] = "analyzed"
    return jsonify({"success": cad.success, "project_id": pid, **rd})


# ── Generate PDF ──────────────────────────────────────────────────────────────
@api_bp.route("/generate/<pid>", methods=["POST"])
def generate(pid):
    """Генерирует PDF-комплект для выбранных инстанций."""
    project = _PROJECTS.get(pid)
    if not project: return jsonify({"error": "Проект не найден"}), 404
    if not project.get("cadastral_result"):
        return jsonify({"error": "Сначала выполните кадастровую сверку /analyze"}), 400
    body = request.get_json(silent=True) or {}
    approval_ids = body.get("approval_ids", None)  # None = все

    gen = PDFGenerator()
    pdf_path = gen.generate_package(project, approval_ids=approval_ids)
    project["status"] = "generated"
    project["pdf_path"] = pdf_path
    return jsonify({"success": True, "download_url": f"/api/v1/download/{pid}"})


@api_bp.route("/download/<pid>")
def download(pid):
    project = _PROJECTS.get(pid)
    if not project or not project.get("pdf_path"):
        return jsonify({"error": "PDF не найден"}), 404
    return send_file(project["pdf_path"], as_attachment=True,
                     download_name=f"АС_СКЛ_{project['name']}.pdf",
                     mimetype="application/pdf")


# ── Project CRUD ──────────────────────────────────────────────────────────────
@api_bp.route("/project/<pid>")
def get_project(pid):
    p = _PROJECTS.get(pid)
    return (jsonify(p), 200) if p else (jsonify({"error": "Не найден"}), 404)

@api_bp.route("/projects")
def list_projects():
    return jsonify({"projects": [
        {"id": p["id"], "name": p["name"], "status": p["status"],
         "total_length_m": p["total_length_m"]}
        for p in _PROJECTS.values()
    ]})

@api_bp.route("/project/<pid>/approval/<int:aid>", methods=["PATCH"])
def update_approval(pid, aid):
    """Обновляет статус согласования (pending/sent/approved/rejected)."""
    project = _PROJECTS.get(pid)
    if not project: return jsonify({"error": "Проект не найден"}), 404
    body = request.get_json(silent=True) or {}
    cad = project.get("cadastral_result", {})
    for a in cad.get("approvals", []):
        if a["id"] == aid:
            if "status" in body: a["status"] = body["status"]
            if "note" in body: a["note"] = body["note"]
            return jsonify({"success": True, "approval": a})
    return jsonify({"error": "Согласование не найдено"}), 404


# ── Helpers ───────────────────────────────────────────────────────────────────
def _rp(p: RoutePoint): return {
    "index": p.index, "x": p.x, "y": p.y, "z": p.z,
    "lon": p.lon, "lat": p.lat, "depth": p.depth,
    "pk": p.pk, "description": p.description,
}
def _drp(d): return RoutePoint(
    index=d["index"], x=d["x"], y=d["y"], z=d.get("z",0),
    lon=d["lon"], lat=d["lat"], depth=d.get("depth",1.2),
    pk=d["pk"], description=d.get("description",""),
)
