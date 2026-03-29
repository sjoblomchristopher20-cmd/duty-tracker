from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from google.cloud import firestore

db = firestore.Client()

USERS_COLLECTION = "users"
TASKS_COLLECTION = "tasks"


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def parse_iso_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def get_all_users() -> List[Dict[str, Any]]:
    docs = db.collection(USERS_COLLECTION).stream()
    rows: List[Dict[str, Any]] = []
    for doc in docs:
        row = doc.to_dict()
        row["id"] = doc.id
        rows.append(row)
    return rows


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    doc = db.collection(USERS_COLLECTION).document(username).get()
    if not doc.exists:
        return None
    row = doc.to_dict()
    row["id"] = doc.id
    return row


def get_user_by_display_name(display_name: str) -> Optional[Dict[str, Any]]:
    docs = (
        db.collection(USERS_COLLECTION)
        .where("display_name", "==", display_name)
        .limit(1)
        .stream()
    )
    for doc in docs:
        row = doc.to_dict()
        row["id"] = doc.id
        return row
    return None


def create_user(user_data: Dict[str, Any]) -> None:
    username = user_data["username"]
    db.collection(USERS_COLLECTION).document(username).set(user_data)


def update_user(username: str, updates: Dict[str, Any]) -> None:
    db.collection(USERS_COLLECTION).document(username).update(updates)


def delete_user(username: str) -> None:
    db.collection(USERS_COLLECTION).document(username).delete()


def get_all_tasks() -> List[Dict[str, Any]]:
    docs = db.collection(TASKS_COLLECTION).stream()
    rows: List[Dict[str, Any]] = []
    for doc in docs:
        row = doc.to_dict()
        row["id"] = doc.id
        rows.append(row)
    return rows


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    doc = db.collection(TASKS_COLLECTION).document(task_id).get()
    if not doc.exists:
        return None
    row = doc.to_dict()
    row["id"] = doc.id
    return row


def create_task(task_data: Dict[str, Any]) -> str:
    ref = db.collection(TASKS_COLLECTION).document()
    task_data["created_at"] = utc_now_iso()
    ref.set(task_data)
    return ref.id


def update_task(task_id: str, updates: Dict[str, Any]) -> None:
    db.collection(TASKS_COLLECTION).document(task_id).update(updates)


def delete_task(task_id: str) -> None:
    db.collection(TASKS_COLLECTION).document(task_id).delete()


def auto_archive_old_tasks(status_approved: str, status_archived: str, days: int = 30) -> None:
    cutoff = datetime.utcnow() - timedelta(days=days)

    docs = (
        db.collection(TASKS_COLLECTION)
        .where("status", "==", status_approved)
        .stream()
    )

    batch = db.batch()
    changed = 0

    for doc in docs:
        row = doc.to_dict()
        approved_dt = parse_iso_date(row.get("approved_date"))
        if approved_dt and approved_dt <= cutoff:
            batch.update(
                doc.reference,
                {
                    "status": status_archived,
                    "archived_date": utc_now_iso(),
                    "last_action": "Auto-archived after 30 days",
                },
            )
            changed += 1

    if changed:
        batch.commit()
