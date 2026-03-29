from flask import Flask, request, redirect, url_for, render_template_string, session
from typing import Dict, Any, List

from storage import (
    utc_now_iso,
    get_all_users,
    get_user_by_username,
    get_user_by_display_name,
    create_user,
    update_user,
    delete_user,
    get_all_tasks,
    get_task,
    create_task,
    update_task,
    delete_task,
    auto_archive_old_tasks,
)

app = Flask(__name__)
app.secret_key = "change-this-secret-before-real-use"

RANKS = {
    "PVT": 1, "PV2": 1, "PFC": 1, "SPC": 1,
    "SGT": 2, "SSG": 3, "SFC": 4, "1SG": 5,
    "MSG": 6, "CW1": 7, "CW2": 8,
    "2LT": 9, "1LT": 10, "CPT": 11,
}

SECTIONS = ["Maintenance", "Distro", "HQ"]
CLAIM_ACCESS_OPTIONS = ["All", "Maintenance", "Distro", "HQ"]

STATUS_AVAILABLE = "available"
STATUS_CLAIMED = "claimed"
STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_ARCHIVED = "archived"


def format_display_name(first_name, last_name, rank):
    return f"{rank} {last_name}, {first_name[0].upper()}"


def get_current_user():
    username = session.get("username")
    return get_user_by_username(username) if username else None


def is_master_admin(user):
    return user and user.get("is_master_admin")


def is_sgt_plus(user):
    return user and user["rank_level"] >= 2


def can_create_tasks(user):
    return is_master_admin(user) or is_sgt_plus(user)


# ------------------------
# ROUTES
# ------------------------

@app.route("/")
def home():
    auto_archive_old_tasks(STATUS_APPROVED, STATUS_ARCHIVED)

    current_user = get_current_user()
    users = get_all_users()
    tasks = get_all_tasks()

    leaderboard = sorted(
        [u for u in users if not u.get("is_master_admin")],
        key=lambda x: -x["points"]
    )

    available_tasks = [t for t in tasks if t["status"] == STATUS_AVAILABLE]
    my_tasks = [t for t in tasks if t.get("claimed_by") == (current_user["display_name"] if current_user else None)]

    return render_template_string("""
    <h1>Duty Tracker</h1>

    {% if not current_user %}
    <form method="POST" action="/login">
        <input name="username" placeholder="Username">
        <input name="password" placeholder="Password">
        <button>Login</button>
    </form>
    {% else %}
    <p>Logged in as {{ current_user.display_name }}</p>
    <form method="POST" action="/logout"><button>Logout</button></form>

    <h2>Leaderboard</h2>
    {% for u in leaderboard %}
        <p>{{ u.display_name }} - {{ u.points }}</p>
    {% endfor %}

    <h2>Create Task</h2>
    <form method="POST" action="/add_task">
        <input name="title" placeholder="Task">
        <input name="points" type="number" placeholder="Points">
        <select name="section_origin">
            {% for s in sections %}<option>{{ s }}</option>{% endfor %}
        </select>
        <select name="claim_access">
            {% for s in claim_access_options %}<option>{{ s }}</option>{% endfor %}
        </select>
        <button>Create</button>
    </form>

    <h2>Available Tasks</h2>
    {% for t in available_tasks %}
        <p>{{ t.title }}
        <form method="POST" action="/claim_task/{{ t.id }}">
            <button>Claim</button>
        </form>
        </p>
    {% endfor %}

    <h2>My Tasks</h2>
    {% for t in my_tasks %}
        <p>{{ t.title }} ({{ t.status }})
        <form method="POST" action="/submit_task/{{ t.id }}">
            <button>Submit</button>
        </form>
        </p>
    {% endfor %}
    {% endif %}
    """,
        current_user=current_user,
        leaderboard=leaderboard,
        available_tasks=available_tasks,
        my_tasks=my_tasks,
        sections=SECTIONS,
        claim_access_options=CLAIM_ACCESS_OPTIONS
    )


@app.route("/login", methods=["POST"])
def login():
    user = get_user_by_username(request.form["username"])
    if user and user["password"] == request.form["password"]:
        session["username"] = user["username"]
    return redirect("/")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


@app.route("/add_task", methods=["POST"])
def add_task():
    user = get_current_user()
    if not can_create_tasks(user):
        return redirect("/")

    create_task({
        "title": request.form["title"],
        "points": int(request.form["points"]),
        "section_origin": request.form["section_origin"],
        "claim_access": request.form["claim_access"],
        "created_by": user["display_name"],
        "created_by_rank": user["rank_level"],
        "created_by_section": user["section"],
        "claimed_by": None,
        "claimed_by_rank": None,
        "claimed_by_section": None,
        "status": STATUS_AVAILABLE,
        "rejection_note": "",
        "last_action": "Created",
        "approved_date": None,
        "archived_date": None,
    })

    return redirect("/")


@app.route("/claim_task/<task_id>", methods=["POST"])
def claim_task(task_id):
    user = get_current_user()
    task = get_task(task_id)

    if task:
        update_task(task_id, {
            "claimed_by": user["display_name"],
            "claimed_by_rank": user["rank_level"],
            "claimed_by_section": user["section"],
            "status": STATUS_CLAIMED,
        })

    return redirect("/")


@app.route("/submit_task/<task_id>", methods=["POST"])
def submit_task(task_id):
    update_task(task_id, {
        "status": STATUS_PENDING
    })
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
