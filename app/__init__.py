"""АС СКЛ v2.0 — Application factory"""
import hmac
from flask import Flask, request, Response
from .config import Config

# Эндпоинты, доступные без авторизации (например, для healthcheck хостинга)
AUTH_EXEMPT_ENDPOINTS = {"api.health"}


def create_app(config_class=Config):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)
    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    @app.before_request
    def require_auth():
        if request.endpoint in AUTH_EXEMPT_ENDPOINTS:
            return None
        auth = request.authorization
        valid = bool(auth) and hmac.compare_digest(auth.username, app.config["AUTH_USERNAME"]) \
            and hmac.compare_digest(auth.password, app.config["AUTH_PASSWORD"])
        if not valid:
            return Response(
                "Требуется авторизация", 401,
                {"WWW-Authenticate": 'Basic realm="AS SKL"'},
            )
        return None

    return app
