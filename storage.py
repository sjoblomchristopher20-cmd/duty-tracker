from datetime import datetime, timezone
from google.cloud import firestore

db = firestore.Client()

USERS_COLLECTION = "users"
TASKS_COLLECTION = "tasks"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_dict(data: dict) -> dict:
    return dict(data)


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_user(doc_id: str, data: dict) -> dict:
    data = data or {}
    return {
        "username": data.get("username", doc_id),
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "display_name": data.get("display_name", ""),
        "password": data.get("password", ""),
        "rank": data.get("rank", ""),
        "rank_level": _safe_int(data.get("rank_level"), 0),
        "section": data.get("section", ""),
        "points": _safe_int(data.get("points"), 0),
        "is_master_admin": bool(data.get("is_master_admin", False)),
        "is_active": bool(data.get("is_active", True)),
        "created_at": data.get("created_at"),
        "last_login_at": data.get("last_login_at"),
    }


def _normalize_task(doc_id: str, data: dict) -> dict:
    data = data or {}
    claimed_by_rank_raw = data.get("claimed_by_rank")
    approved_by_rank_raw = data.get("approved_by_rank")
    rejected_by_rank_raw = data.get("rejected_by_rank")

    return {
        "id": data.get("id", doc_id),
        "title": data.get("title", ""),
        "points": _safe_int(data.get("points"), 0),
        "section_origin": data.get("section_origin", ""),
        "claim_access": data.get("claim_access", "All"),
        "min_rank_level": _safe_int(data.get("min_rank_level"), 1),
        "due_date": data.get("due_date"),
        "created_by": data.get("created_by", ""),
        "created_by_rank": _safe_int(data.get("created_by_rank"), 0),
        "created_by_section": data.get("created_by_section", ""),
        "claimed_by": data.get("claimed_by"),
        "claimed_by_username": data.get("claimed_by_username"),
        "claimed_by_rank": _safe_int(claimed_by_rank_raw, None) if claimed_by_rank_raw is not None else None,
        "claimed_by_section": data.get("claimed_by_section"),
        "claimed_at": data.get("claimed_at"),
        "submitted_at": data.get("submitted_at"),
        "approved_at": data.get("approved_at"),
        "approved_by": data.get("approved_by"),
        "approved_by_rank": _safe_int(approved_by_rank_raw, None) if approved_by_rank_raw is not None else None,
        "approved_by_section": data.get("approved_by_section"),
        "rejected_at": data.get("rejected_at"),
        "rejected_by": data.get("rejected_by"),
        "rejected_by_rank": _safe_int(rejected_by_rank_raw, None) if rejected_by_rank_raw is not None else None,
        "rejected_by_section": data.get("rejected_by_section"),
        "status": data.get("status", "available"),
        "rejection_note": data.get("rejection_note", ""),
        "last_action": data.get("last_action", ""),
        "approved_date": data.get("approved_date"),
        "archived_date": data.get("archived_date"),
        "created_at": data.get("created_at"),
    }


def get_all_users():
    docs = db.collection(USERS_COLLECTION).stream()
    return [_normalize_user(doc.id, doc.to_dict()) for doc in docs]


def get_user_by_username(username: str):
    if not username:
        return None

    doc = db.collection(USERS_COLLECTION).document(username).get()
    if not doc.exists:
        return None

    return _normalize_user(doc.id, doc.to_dict())


def create_user(user_data: dict):
    username = user_data["username"]
    payload = dict(user_data)
    payload.setdefault("created_at", utc_now_iso())
    payload.setdefault("is_active", True)
    db.collection(USERS_COLLECTION).document(username).set(_clean_dict(payload))


def update_user(username: str, updates: dict):
    db.collection(USERS_COLLECTION).document(username).set(
        _clean_dict(updates),
        merge=True,
    )


def delete_user(username: str):
    db.collection(USERS_COLLECTION).document(username).delete()


def get_all_tasks():
    docs = db.collection(TASKS_COLLECTION).stream()
    return [_normalize_task(doc.id, doc.to_dict()) for doc in docs]


def get_task(task_id: str):
    if not task_id:
        return None

    doc = db.collection(TASKS_COLLECTION).document(str(task_id)).get()
    if not doc.exists:
        return None

    return _normalize_task(doc.id, doc.to_dict())


def create_task(task_data: dict):
    ref = db.collection(TASKS_COLLECTION).document()
    payload = dict(task_data)
    payload["id"] = ref.id
    payload.setdefault("created_at", utc_now_iso())
    payload.setdefault("min_rank_level", 1)
    ref.set(_clean_dict(payload))
    return ref.id


def update_task(task_id: str, updates: dict):
    db.collection(TASKS_COLLECTION).document(str(task_id)).set(
        _clean_dict(updates),
        merge=True,
    )


def delete_task(task_id: str):
    db.collection(TASKS_COLLECTION).document(str(task_id)).delete()


def auto_archive_old_tasks(from_status: str, to_status: str, days_old: int = 30):
    now = datetime.now(timezone.utc)
    docs = (
        db.collection(TASKS_COLLECTION)
        .where("status", "==", from_status)
        .stream()
    )

    for doc in docs:
        task = _normalize_task(doc.id, doc.to_dict())
        approved_date = task.get("approved_date")
        if not approved_date:
            continue

        try:
            approved_dt = datetime.fromisoformat(approved_date.replace("Z", "+00:00"))
        except Exception:
            continue

        age_days = (now - approved_dt).days
        if age_days >= days_old:
            doc.reference.set(
                {
                    "status": to_status,
                    "archived_date": utc_now_iso(),
                    "last_action": f"Auto-archived after {days_old} days",
                },
                merge=True,
            )
