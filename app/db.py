"""In-memory storage для АС СКЛ v2.0 (без PostgreSQL)"""
import threading
from datetime import datetime, timezone

_store: dict[str, dict] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_save(project: dict) -> None:
    with _lock:
        _store[project["id"]] = project


def project_get(pid: str) -> dict | None:
    with _lock:
        return _store.get(pid)


def project_update(pid: str, **fields) -> bool:
    with _lock:
        if pid not in _store:
            return False
        _store[pid].update(fields)
        _store[pid]["updated_at"] = _now()
        return True


def project_list() -> list[dict]:
    with _lock:
        return [
            {k: v for k, v in p.items() if k in ("id", "name", "status", "total_length_m")}
            for p in sorted(_store.values(), key=lambda p: p.get("created_at", ""), reverse=True)
        ]
