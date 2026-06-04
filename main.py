import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

app = create_app()

if __name__ == "__main__":
    print("=" * 60)
    print("  АС СКЛ v2.0 — Согласование кабельных линий")
    print(f"  URL: http://0.0.0.0:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)
