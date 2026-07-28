"""
АС СКЛ v2.0 — REST API (in-memory backend, без PostgreSQL)
"""
import os, uuid, json, logging, hmac
from datetime import datetime, timezone
from flask import (
    Blueprint, request, jsonify, send_file,
    render_template, redirect, url_for, session, current_app,
)
from .modules.dwg_parser import parse_from_bytes, RoutePoint
from .modules.cadastral import CadastralAnalyzer, result_to_dict
from .modules.pdf_generator import PDFGenerator
from .db import project_save, project_get, project_update, project_list

logger = logging.getLogger(__name__)
main_bp = Blueprint("main", __name__)
api_bp  = Blueprint("api",  __name__)


# ── UI ────────────────────────────────────────────────────────────────────────
@main_bp.route("/")
def index():
    path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    html = open(path, encoding="utf-8").read()
    return html, 200, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "X-Frame-Options": "SAMEORIGIN",
    }

@main_bp.route("/favicon.ico")
def favicon(): return "", 204


# ── Auth (тестовая, один пользователь) ──────────────────────────────────────
@main_bp.route("/login", methods=["GET", "POST"])
def login():
    error = False
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        valid = hmac.compare_digest(username, current_app.config["AUTH_USERNAME"]) \
            and hmac.compare_digest(password, current_app.config["AUTH_PASSWORD"])
        if valid:
            session.clear()
            session["authenticated"] = True
            session.permanent = True
            return redirect(url_for("main.index"))
        error = True
    return render_template("login.html", error=error)


@main_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("main.login"))


# ── Health ────────────────────────────────────────────────────────────────────
@api_bp.route("/health")
def health():
    return jsonify({
        "status": "ok", "version": "2.0.0",
        "service": "АС СКЛ", "db": "in-memory"
    })


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
        allowed = {"dwg", "dxf", "csv"}  # парсер (dwg_parser.py) поддерживает только эти форматы
        if ext not in allowed:
            return jsonify({"error": f"Формат .{ext} не поддерживается"}), 400
        data = f.read()
        result = parse_from_bytes(data, f.filename)
        route_points = result.points
        parse_errors = result.errors
        parse_warnings = result.warnings
        crs_detected = result.crs_detected
        project_name = request.form.get("project", f.filename.rsplit(".", 1)[0])
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
        xy = [(p.get("x", 0), p.get("y", 0)) for p in raw_points]
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
                index=i, x=x, y=y, z=float(pt.get("z", 0)),
                lon=round(lon, 8), lat=round(lat, 8),
                depth=float(pt.get("depth", 1.2)), pk=round(cum, 1),
                description=pt.get("description", ""),
            ))
        meta = {"format": "JSON", "points_count": len(route_points)}
    else:
        return jsonify({"error": "Ожидается файл или JSON"}), 400

    pid = str(uuid.uuid4())
    total_length = route_points[-1].pk if route_points else 0
    now = datetime.now(timezone.utc).isoformat()

    project_save({
        "id": pid,
        "name": project_name,
        "status": "parsed",
        "total_length_m": total_length,
        "crs": crs_detected,
        "route": [_rp(p) for p in route_points],
        "meta": meta,
        "cadastral_result": None,
        "pdf_path": None,
        "created_at": now,
        "updated_at": now,
    })

    return jsonify({
        "success": True, "project_id": pid, "project_name": project_name,
        "route_summary": {
            "points_count": len(route_points),
            "total_length_m": total_length,
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
    project = project_get(pid)
    if not project:
        return jsonify({"error": "Проект не найден"}), 404

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

    project_update(pid, cadastral_result=rd, status="analyzed")

    return jsonify({"success": cad.success, "project_id": pid, **rd})


# ── Generate PDF ──────────────────────────────────────────────────────────────
@api_bp.route("/generate/<pid>", methods=["POST"])
def generate(pid):
    project = project_get(pid)
    if not project:
        return jsonify({"error": "Проект не найден"}), 404
    if not project.get("cadastral_result"):
        return jsonify({"error": "Сначала выполните кадастровую сверку /analyze"}), 400

    body = request.get_json(silent=True) or {}
    approval_ids = body.get("approval_ids", None)

    gen = PDFGenerator()
    try:
        pdf_path = gen.generate_package(project, approval_ids=approval_ids)
    except Exception:
        logger.exception(f"PDF generation failed for project {pid}")
        return jsonify({"error": "Не удалось сформировать PDF-пакет"}), 500

    project_update(pid, status="generated", pdf_path=pdf_path)

    return jsonify({"success": True, "download_url": f"/api/v1/download/{pid}"})


@api_bp.route("/download/<pid>")
def download(pid):
    project = project_get(pid)
    if not project or not project.get("pdf_path"):
        return jsonify({"error": "PDF не найден"}), 404
    return send_file(project["pdf_path"], as_attachment=True,
                     download_name=f"АС_СКЛ_{project['name']}.pdf",
                     mimetype="application/pdf")


# ── Project CRUD ──────────────────────────────────────────────────────────────
@api_bp.route("/project/<pid>")
def get_project(pid):
    project = project_get(pid)
    if not project:
        return jsonify({"error": "Не найден"}), 404
    return jsonify(project)

@api_bp.route("/projects")
def list_projects():
    return jsonify({"projects": project_list()})

@api_bp.route("/project/<pid>/approval/<int:aid>", methods=["PATCH"])
def update_approval(pid, aid):
    project = project_get(pid)
    if not project:
        return jsonify({"error": "Проект не найден"}), 404

    body = request.get_json(silent=True) or {}
    cad = project.get("cadastral_result") or {}
    updated = None
    for a in cad.get("approvals", []):
        if a["id"] == aid:
            if "status" in body: a["status"] = body["status"]
            if "note" in body: a["note"] = body["note"]
            updated = a
            break

    if not updated:
        return jsonify({"error": "Согласование не найдено"}), 404

    project_update(pid, cadastral_result=cad)

    return jsonify({"success": True, "approval": updated})


# ── Helpers ───────────────────────────────────────────────────────────────────
def _rp(p: RoutePoint) -> dict:
    return {
        "index": p.index, "x": p.x, "y": p.y, "z": p.z,
        "lon": p.lon, "lat": p.lat, "depth": p.depth,
        "pk": p.pk, "description": p.description,
    }

def _drp(d: dict) -> RoutePoint:
    return RoutePoint(
        index=d["index"], x=d["x"], y=d["y"], z=d.get("z", 0),
        lon=d["lon"], lat=d["lat"], depth=d.get("depth", 1.2),
        pk=d["pk"], description=d.get("description", ""),
    )
