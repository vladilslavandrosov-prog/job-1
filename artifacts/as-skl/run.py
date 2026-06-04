import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    print("=" * 60)
    print("  АС СКЛ v2.0 — Согласование кабельных линий")
    print(f"  URL: http://0.0.0.0:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
