import os
from datetime import datetime, timezone
from google.cloud import firestore

db = firestore.Client()

USERS_COLLECTION = "users"
TASKS_COLLECTION = "tasks"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _clean_dict(data: dict) -> dict:
    """Remove None values only where helpful for writes."""
    return {k: v for k, v in data.items()}


def _normalize_user(doc_id: str, data: dict) -> dict:
    data = data or {}
    return {
        "username": data.get("username", doc_id),
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "display_name": data.get("display_name", ""),
        "password": data.get("password", ""),
        "rank": data.get("rank", ""),
        "rank_level": int(data.get("rank_level", 0) or 0),
        "section": data.get("section", ""),
        "points": int(data.get("points", 0) or 0),
        "is_master_admin": bool(data.get("is_master_admin", False)),
        "created_at": data.get("created_at"),
    }


def _normalize_task(doc_id: str, data: dict) -> dict:
    data = data or {}
    return {
        "id": data.get("id", doc_id),
        "title": data.get("title", ""),
        "points": int(data.get("points", 0) or 0),
        "section_origin": data.get("section_origin", ""),
        "claim_access": data.get("claim_access", "All"),
        "created_by": data.get("created_by", ""),
        "created_by_rank": int(data.get("created_by_rank", 0) or 0),
        "created_by_section": data.get("created_by_section", ""),
        "claimed_by": data.get("claimed_by"),
        "claimed_by_rank": (
            int(data["claimed_by_rank"]) if data.get("claimed_by_rank") is not None else None
        ),
        "claimed_by_section": data.get("claimed_by_section"),
        "status": data.get("status", "available"),
        "rejection_note": data.get("rejection_note", ""),
        "last_action": data.get("last_action", ""),
        "approved_date": data.get("approved_date"),
        "archived_date": data.get("archived_date"),
    }


# -----------------
# User helpers
# -----------------

def get_all_users():
    docs = db.collection(USERS_COLLECTION).stream()
    users = []
    for doc in docs:
        users.append(_normalize_user(doc.id, doc.to_dict()))
    return users


def get_user_by_username(username: str):
    if not username:
        return None
    doc = db.collection(USERS_COLLECTION).document(username).get()
    if not doc.exists:
        return None
    return _normalize_user(doc.id, doc.to_dict())


def get_user_by_display_name(display_name: str):
    if not display_name:
        return None
    matches = (
        db.collection(USERS_COLLECTION)
        .where("display_name", "==", display_name)
        .limit(1)
        .stream()
    )
    for doc in matches:
        return _normalize_user(doc.id, doc.to_dict())
    return None


def create_user(user_data: dict):
    username = user_data["username"]
    db.collection(USERS_COLLECTION).document(username).set(_clean_dict(user_data))


def update_user(username: str, updates: dict):
    db.collection(USERS_COLLECTION).document(username).set(
        _clean_dict(updates), merge=True
    )


def delete_user(username: str):
    db.collection(USERS_COLLECTION).document(username).delete()


# -----------------
# Task helpers
# -----------------

def get_all_tasks():
    docs = db.collection(TASKS_COLLECTION).stream()
    tasks = []
    for doc in docs:
        tasks.append(_normalize_task(doc.id, doc.to_dict()))
    return tasks


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
    ref.set(_clean_dict(payload))
    return ref.id


def update_task(task_id: str, updates: dict):
    db.collection(TASKS_COLLECTION).document(str(task_id)).set(
        _clean_dict(updates), merge=True
    )


def delete_task(task_id: str):
    db.collection(TASKS_COLLECTION).document(str(task_id)).delete()


def auto_archive_old_tasks(from_status: str, to_status: str, days_old: int = 30):
    """
    Optional simple archiver.
    Archives approved tasks older than N days based on approved_date.
    If approved_date is missing or malformed, it skips that task.
    """
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
