"""АС СКЛ v2.0 — Application factory"""
from datetime import timedelta
from flask import Flask, request, session, redirect, url_for, jsonify
from .config import Config

# Эндпоинты, доступные без авторизации
AUTH_EXEMPT_ENDPOINTS = {"api.health", "main.login", "main.logout"}


def create_app(config_class=Config):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)
    app.permanent_session_lifetime = timedelta(days=7)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    @app.before_request
    def require_auth():
        if request.endpoint in AUTH_EXEMPT_ENDPOINTS or request.endpoint == "static":
            return None
        if session.get("authenticated"):
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "Требуется авторизация"}), 401
        return redirect(url_for("main.login"))

    return app
