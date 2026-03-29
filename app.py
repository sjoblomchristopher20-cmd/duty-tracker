from flask import Flask, request, redirect, url_for, session, render_template_string
from datetime import datetime, timezone

from storage import (
    get_all_users,
    get_user_by_username,
    create_user,
    update_user,
    delete_user,
    get_all_tasks,
    create_task,
    update_task,
    delete_task,
    auto_archive_old_tasks,
)

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

SECTIONS = ["Maintenance", "Distro", "HQ"]
CLAIM_ACCESS_OPTIONS = ["All"] + SECTIONS

RANKS = {
    "PVT": 1,
    "PV2": 1,
    "PFC": 1,
    "SPC": 1,
    "CPL": 2,
    "SGT": 2,
    "SSG": 3,
    "SFC": 4,
    "MSG": 5,
    "1SG": 6,
    "CW1": 7,
    "CW2": 8,
    "2LT": 9'
    "1LT": 10,
    "CPT": 11,
    "ADMIN": 999,
}

STATUS_AVAILABLE = "available"
STATUS_CLAIMED = "claimed"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_ARCHIVED = "archived"

HTML = """
<!doctype html>
<html>
<head>
    <title>Duty Tracker</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 24px;
            color: #111;
        }
        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 20px;
        }
        .topbar-right form {
            margin: 0;
        }
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }
        .panel-form, .panel {
            border: 1px solid #ddd;
            padding: 16px;
            margin-bottom: 20px;
            background: #fafafa;
        }
        input, select, button, textarea {
            width: 100%;
            padding: 10px;
            margin: 6px 0 12px 0;
            box-sizing: border-box;
        }
        button {
            cursor: pointer;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 24px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 10px;
            text-align: left;
            vertical-align: top;
        }
        .note {
            color: #b00020;
            margin: 8px 0;
        }
        .section-buttons a,
        .history-tabs a {
            display: inline-block;
            padding: 8px 12px;
            margin-right: 8px;
            border: 1px solid #ccc;
            text-decoration: none;
            color: #111;
            background: #f7f7f7;
        }
        .section-buttons a.active,
        .history-tabs a.active {
            background: #e8f0fe;
            border-color: #0b57d0;
        }
        .inline-form {
            margin: 0;
        }
        .muted {
            color: #666;
        }
        .small {
            font-size: 12px;
        }
    </style>
</head>
<body>
{% if not current_user %}
    <h1>Duty Tracker</h1>

    <div class="section-buttons">
        {% for option in public_section_options %}
            <a href="/?public_section={{ option }}" class="{% if public_section == option %}active{% endif %}">{{ option }}</a>
        {% endfor %}
    </div>

    <h2>Section Leaderboard</h2>
    <table>
        <tr>
            <th>Section</th>
            <th>Total Points</th>
        </tr>
        {% for row in public_section_rows %}
        <tr>
            <td>{{ row.section }}</td>
            <td>{{ row.points }}</td>
        </tr>
        {% endfor %}
    </table>

    <div class="panel-form" style="max-width: 420px;">
        <h2>Login</h2>
        <form method="POST" action="/login">
            <input type="hidden" name="public_section" value="{{ public_section }}">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
            {% if login_error %}
                <p class="note">{{ login_error }}</p>
            {% endif %}
        </form>
    </div>
{% else %}
    <div class="topbar">
        <div>
            <h1>Duty Tracker</h1>
            <div>
                Logged in as <strong>{{ current_user.display_name }}</strong>
                {% if show_admin_panel %} | Master Admin{% endif %}
                | {{ current_user.rank }}
                | {{ current_user.section }}
                | Points: <strong>{{ current_user.points }}</strong>
            </div>
        </div>
        <div class="topbar-right">
            <form method="POST" action="/logout">
                <button type="submit">Logout</button>
            </form>
        </div>
    </div>

    <div class="grid-2">
        <div>
            <h2>Individual Leaderboard</h2>
            <table>
                <tr>
                    <th>Name</th>
                    <th>Section</th>
                    <th>Points</th>
                </tr>
                {% for user in leaderboard %}
                <tr>
                    <td>{{ user.display_name }}</td>
                    <td>{{ user.section }}</td>
                    <td>{{ user.points }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>

        <div>
            <h2>Section Leaderboard</h2>
            <table>
                <tr>
                    <th>Section</th>
                    <th>Total Points</th>
                </tr>
                {% for row in section_totals %}
                <tr>
                    <td>{{ row.section }}</td>
                    <td>{{ row.points }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>

    {% if show_admin_panel %}
    <h2>Master Admin Panel</h2>
    <div class="grid-2">
        <form class="panel-form" method="POST" action="/add_user">
            <h3>Create User</h3>
            <input type="text" name="first_name" placeholder="First name" required>
            <input type="text" name="last_name" placeholder="Last name" required>
            <input type="password" name="password" placeholder="Password" required>

            <select name="rank" required>
                {% for rank_name in rank_names %}
                    <option value="{{ rank_name }}">{{ rank_name }}</option>
                {% endfor %}
            </select>

            <select name="section" required>
                {% for section in sections %}
                    <option value="{{ section }}">{{ section }}</option>
                {% endfor %}
            </select>

            <button type="submit">Create User</button>
        </form>

        <form class="panel-form" method="POST" action="/reset_password">
            <h3>Reset Password</h3>
            <select name="target_username" required>
                {% for user in resettable_users %}
                    <option value="{{ user.username }}">{{ user.display_name }} ({{ user.username }})</option>
                {% endfor %}
            </select>
            <input type="password" name="new_password" placeholder="New password" required>
            <button type="submit">Reset Password</button>
        </form>
    </div>

    <h2>All Users</h2>
    <table>
        <tr>
            <th>Name</th>
            <th>Username</th>
            <th>Rank</th>
            <th>Section</th>
            <th>Points</th>
            <th>Action</th>
        </tr>
        {% for user in manageable_users %}
        <tr>
            <td>{{ user.display_name }}</td>
            <td>{{ user.username }}</td>
            <td>{{ user.rank }}</td>
            <td>{{ user.section }}</td>
            <td>{{ user.points }}</td>
            <td>
                <form class="inline-form" method="POST" action="/delete_user/{{ user.username }}">
                    <button type="submit">Delete User</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    {% if can_create_tasks %}
    <h2>Task Controls</h2>
    <form class="panel-form" method="POST" action="/add_task" style="max-width: 420px;">
        <h3>Create Task</h3>
        <input type="text" name="title" placeholder="Task title" required>
        <input type="number" name="points" placeholder="Points" min="1" required>

        <select name="section_origin" required>
            {% for section in sections %}
                <option value="{{ section }}">{{ section }}</option>
            {% endfor %}
        </select>

        <select name="claim_access" required>
            {% for option in claim_access_options %}
                <option value="{{ option }}">{{ option }}</option>
            {% endfor %}
        </select>

        <button type="submit">Create Task</button>
    </form>
    {% endif %}

    <h2>Available Tasks</h2>
    {% if available_tasks %}
        <table>
            <tr>
                <th>Title</th>
                <th>Points</th>
                <th>Origin</th>
                <th>Access</th>
                <th>Action</th>
            </tr>
            {% for task in available_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.section_origin }}</td>
                <td>{{ task.claim_access }}</td>
                <td>
                    {% if can_claim_map[task.id] %}
                    <form class="inline-form" method="POST" action="/claim_task/{{ task.id }}">
                        <button type="submit">Claim</button>
                    </form>
                    {% else %}
                    <span class="muted">Unavailable</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    {% else %}
        <p class="muted">No available tasks right now.</p>
    {% endif %}

    <h2>My Tasks</h2>
    {% if my_tasks %}
        <table>
            <tr>
                <th>Title</th>
                <th>Points</th>
                <th>Status</th>
                <th>Action</th>
            </tr>
            {% for task in my_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.status }}</td>
                <td>
                    {% if can_submit_map[task.id] %}
                    <form class="inline-form" method="POST" action="/submit_task/{{ task.id }}">
                        <button type="submit">Submit</button>
                    </form>
                    {% else %}
                    <span class="muted">Waiting</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    {% else %}
        <p class="muted">You have no active tasks right now.</p>
    {% endif %}

    <h2>Approval Queue</h2>
    {% if pending_tasks %}
        <table>
            <tr>
                <th>Title</th>
                <th>Points</th>
                <th>Completed By</th>
                <th>Section</th>
                <th>Action</th>
            </tr>
            {% for task in pending_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.claimed_by }}</td>
                <td>{{ task.claimed_by_section }}</td>
                <td>
                    {% if can_approve_map[task.id] %}
                    <form class="inline-form" method="POST" action="/approve_task/{{ task.id }}" style="display:inline-block;">
                        <button type="submit">Approve</button>
                    </form>
                    <form class="inline-form" method="POST" action="/reject_task/{{ task.id }}" style="display:inline-block;">
                        <input type="text" name="rejection_note" placeholder="Reason" required>
                        <button type="submit">Reject</button>
                    </form>
                    {% else %}
                    <span class="muted">No access</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    {% else %}
        <p class="muted">No tasks pending approval.</p>
    {% endif %}

    <h2>History</h2>
    <div class="history-tabs">
        <a href="/?history_tab=approved" class="{% if history_tab == 'approved' %}active{% endif %}">Approved</a>
        <a href="/?history_tab=archived" class="{% if history_tab == 'archived' %}active{% endif %}">Archived</a>
    </div>

    <form class="panel" method="GET" action="/">
        <input type="hidden" name="history_tab" value="{{ history_tab }}">

        <div class="grid-2">
            <div>
                <label>Completed By Name</label>
                <select name="filter_name">
                    <option value="">All</option>
                    {% for name in completed_names %}
                        <option value="{{ name }}" {% if filter_name == name %}selected{% endif %}>{{ name }}</option>
                    {% endfor %}
                </select>
            </div>

            <div>
                <label>Completed By Section</label>
                <select name="filter_completed_section">
                    <option value="">All</option>
                    {% for section in sections %}
                        <option value="{{ section }}" {% if filter_completed_section == section %}selected{% endif %}>{{ section }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>

        <div style="max-width: 420px;">
            <label>Origin Section</label>
            <select name="filter_origin">
                <option value="">All</option>
                {% for section in sections %}
                    <option value="{{ section }}" {% if filter_origin == section %}selected{% endif %}>{{ section }}</option>
                {% endfor %}
            </select>
        </div>

        <button type="submit">Apply Filters</button>
        <a href="/?history_tab={{ history_tab }}">Clear Filters</a>
    </form>

    <p class="small muted">Showing {{ history_rows|length }} task(s)</p>

    {% if history_rows %}
        <table>
            <tr>
                <th>Title</th>
                <th>Points</th>
                <th>Completed By</th>
                <th>Completed Section</th>
                <th>Origin Section</th>
                <th>Status</th>
                <th>Action</th>
            </tr>
            {% for task in history_rows %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.claimed_by or "" }}</td>
                <td>{{ task.claimed_by_section or "" }}</td>
                <td>{{ task.section_origin }}</td>
                <td>{{ task.status }}</td>
                <td>
                    {% if can_delete_map[task.id] %}
                    <form class="inline-form" method="POST" action="/delete_task/{{ task.id }}">
                        <button type="submit">Delete</button>
                    </form>
                    {% else %}
                    <span class="muted">—</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    {% else %}
        <p class="muted">No tasks found for this history view.</p>
    {% endif %}
{% endif %}
</body>
</html>
"""


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def format_display_name(first_name: str, last_name: str) -> str:
    return f"{first_name} {last_name}".strip()


def get_current_user():
    username = session.get("username")
    if not username:
        return None
    return get_user_by_username(username)


def is_master_admin(user):
    return bool(user and user.get("is_master_admin"))


def is_sgt_plus(user):
    return bool(user and user.get("rank_level", 0) >= 2)


def is_msg_plus(user):
    return bool(user and user.get("rank_level", 0) >= 6)


def can_create_tasks(user):
    return is_master_admin(user) or is_sgt_plus(user)


def can_create_users(user):
    return is_master_admin(user)


def can_reset_passwords(user):
    return is_master_admin(user)


def can_delete_users(user):
    return is_master_admin(user)


def can_force_delete(user):
    return is_master_admin(user)


def can_see_task(task, user):
    if not user:
        return False
    if task["claim_access"] == "All":
        return True
    return user.get("section") == task.get("claim_access")


def can_claim_task(task, user):
    return (
        bool(user)
        and task.get("status") == STATUS_AVAILABLE
        and can_see_task(task, user)
    )


def can_submit_task(task, user):
    return (
        bool(user)
        and task.get("claimed_by_username") == user.get("username")
        and task.get("status") == STATUS_CLAIMED
    )


def can_approve_task(task, user):
    return bool(user) and task.get("status") == STATUS_PENDING and (
        is_master_admin(user) or user.get("section") == task.get("section_origin")
    )


def can_delete_open_task(task, user):
    return bool(user) and (
        is_master_admin(user)
        or (
            can_create_tasks(user)
            and task.get("status") in [STATUS_AVAILABLE, STATUS_CLAIMED, STATUS_PENDING]
            and task.get("created_by") == user.get("username")
        )
    )


def build_leaderboard(users):
    return sorted(users, key=lambda u: (-int(u.get("points", 0)), u.get("display_name", "")))


def build_section_totals(users, only_section=None):
    rows = []
    for section in SECTIONS:
        if only_section and section != only_section:
            continue
        total = sum(int(u.get("points", 0) or 0) for u in users if u.get("section") == section)
        rows.append({"section": section, "points": total})
    return rows


@app.route("/setup", methods=["GET"])
def setup():
    existing = get_user_by_username("training_room")
    if not existing:
        create_user({
            "username": "training_room",
            "first_name": "Training",
            "last_name": "Room",
            "display_name": "Training Room",
            "password": "admin123",
            "rank": "ADMIN",
            "rank_level": 999,
            "section": "HQ",
            "points": 0,
            "is_master_admin": True,
            "created_at": utc_now_iso(),
        })
    return "Setup complete"


@app.route("/", methods=["GET"])
def home():
    auto_archive_old_tasks(STATUS_APPROVED, STATUS_ARCHIVED)

    current_user = get_current_user()
    public_section = request.args.get("public_section", "All")
    if public_section not in ["All"] + SECTIONS:
        public_section = "All"

    history_tab = request.args.get("history_tab", "approved")
    if history_tab not in ["approved", "archived"]:
        history_tab = "approved"

    filter_name = request.args.get("filter_name", "").strip()
    filter_completed_section = request.args.get("filter_completed_section", "").strip()
    filter_origin = request.args.get("filter_origin", "").strip()

    all_users = get_all_users()
    all_tasks = get_all_tasks()

    if not current_user:
        return render_template_string(
            HTML,
            current_user=None,
            show_admin_panel=False,
            login_error=session.pop("login_error", None),
            public_section=public_section,
            public_section_options=["All"] + SECTIONS,
            public_section_rows=build_section_totals(
                all_users,
                None if public_section == "All" else public_section
            ),
        )

    leaderboard = build_leaderboard(all_users)
    section_totals = build_section_totals(all_users)

    available_tasks = [
        task for task in all_tasks
        if task["status"] == STATUS_AVAILABLE and can_see_task(task, current_user)
    ]

    my_tasks = [
        task for task in all_tasks
        if task.get("claimed_by_username") == current_user["username"]
        and task["status"] in [STATUS_CLAIMED, STATUS_PENDING]
    ]

    pending_tasks = [
        task for task in all_tasks
        if can_approve_task(task, current_user)
    ]

    approved_history = [task for task in all_tasks if task["status"] == STATUS_APPROVED]
    archived_history = [task for task in all_tasks if task["status"] == STATUS_ARCHIVED]

    history_rows = approved_history if history_tab == "approved" else archived_history

    if filter_name:
        history_rows = [t for t in history_rows if (t.get("claimed_by") or "") == filter_name]
    if filter_completed_section:
        history_rows = [t for t in history_rows if (t.get("claimed_by_section") or "") == filter_completed_section]
    if filter_origin:
        history_rows = [t for t in history_rows if (t.get("section_origin") or "") == filter_origin]

    completed_names = sorted({t.get("claimed_by") for t in approved_history + archived_history if t.get("claimed_by")})

    can_claim_map = {task["id"]: can_claim_task(task, current_user) for task in available_tasks}
    can_submit_map = {task["id"]: can_submit_task(task, current_user) for task in my_tasks}
    can_approve_map = {task["id"]: can_approve_task(task, current_user) for task in pending_tasks}
    can_delete_map = {
        task["id"]: can_delete_open_task(task, current_user) or can_force_delete(current_user)
        for task in history_rows
    }

    resettable_users = [u for u in all_users if not u.get("is_master_admin")]
    manageable_users = [u for u in all_users if not u.get("is_master_admin")]

    show_admin_panel = bool(current_user and current_user.get("is_master_admin"))

    return render_template_string(
        HTML,
        current_user=current_user,
        show_admin_panel=show_admin_panel,
        can_create_users=can_create_users(current_user),
        can_reset_passwords=can_reset_passwords(current_user),
        can_create_tasks=can_create_tasks(current_user),
        can_see_archived=is_sgt_plus(current_user) or is_master_admin(current_user),
        is_msg_plus=is_msg_plus(current_user),
        can_force_delete=can_force_delete(current_user),
        leaderboard=leaderboard,
        section_totals=section_totals,
        sections=SECTIONS,
        rank_names=list(RANKS.keys()),
        claim_access_options=CLAIM_ACCESS_OPTIONS,
        available_tasks=available_tasks,
        my_tasks=my_tasks,
        pending_tasks=pending_tasks,
        history_tab=history_tab,
        history_rows=history_rows,
        completed_names=completed_names,
        filter_name=filter_name,
        filter_completed_section=filter_completed_section,
        filter_origin=filter_origin,
        can_claim_map=can_claim_map,
        can_submit_map=can_submit_map,
        can_approve_map=can_approve_map,
        can_delete_map=can_delete_map,
        resettable_users=resettable_users,
        manageable_users=manageable_users,
        login_error=None,
        public_section=public_section,
        public_section_options=["All"] + SECTIONS,
        public_section_rows=[],
    )


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"].strip()
    password = request.form["password"]
    public_section = request.form.get("public_section", "All")

    user = get_user_by_username(username)
    if not user or user.get("password") != password:
        session["login_error"] = "Invalid username or password."
        return redirect(url_for("home", public_section=public_section))

    session["username"] = user["username"]
    return redirect(url_for("home"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/add_user", methods=["POST"])
def add_user_route():
    current_user = get_current_user()
    if not can_create_users(current_user):
        return redirect(url_for("home"))

    first_name = request.form["first_name"].strip()
    last_name = request.form["last_name"].strip()
    password = request.form["password"]
    rank = request.form["rank"]
    section = request.form["section"]

    if not first_name or not last_name or rank not in RANKS or section not in SECTIONS:
        return redirect(url_for("home"))

    username = f"{last_name.lower()}{first_name[0].lower()}"
    base = username
    suffix = 2
    while get_user_by_username(username):
        username = f"{base}{suffix}"
        suffix += 1

    create_user({
        "first_name": first_name,
        "last_name": last_name,
        "display_name": format_display_name(first_name, last_name),
        "username": username,
        "password": password,
        "rank": rank,
        "rank_level": RANKS[rank],
        "section": section,
        "points": 0,
        "is_master_admin": False,
        "created_at": utc_now_iso(),
    })

    return redirect(url_for("home"))


@app.route("/reset_password", methods=["POST"])
def reset_password():
    current_user = get_current_user()
    if not can_reset_passwords(current_user):
        return redirect(url_for("home"))

    target_username = request.form["target_username"].strip()
    new_password = request.form["new_password"]

    target_user = get_user_by_username(target_username)
    if target_user and not target_user.get("is_master_admin") and new_password:
        update_user(target_username, {"password": new_password})

    return redirect(url_for("home"))


@app.route("/delete_user/<username>", methods=["POST"])
def delete_user_route(username):
    current_user = get_current_user()
    if not can_delete_users(current_user):
        return redirect(url_for("home"))

    target_user = get_user_by_username(username)
    if target_user and not target_user.get("is_master_admin"):
        delete_user(username)

    return redirect(url_for("home"))


@app.route("/add_task", methods=["POST"])
def add_task_route():
    current_user = get_current_user()
    if not can_create_tasks(current_user):
        return redirect(url_for("home"))

    title = request.form["title"].strip()
    try:
        points = int(request.form["points"])
    except (KeyError, ValueError, TypeError):
        return redirect(url_for("home"))

    section_origin = request.form["section_origin"]
    claim_access = request.form["claim_access"]

    if not title or points < 1 or section_origin not in SECTIONS or claim_access not in CLAIM_ACCESS_OPTIONS:
        return redirect(url_for("home"))

    create_task({
        "title": title,
        "points": points,
        "section_origin": section_origin,
        "claim_access": claim_access,
        "created_by": current_user["username"],
        "created_by_rank": current_user.get("rank_level", 0),
        "created_by_section": current_user.get("section", ""),
        "claimed_by": None,
        "claimed_by_username": None,
        "claimed_by_rank": None,
        "claimed_by_section": None,
        "status": STATUS_AVAILABLE,
        "rejection_note": "",
        "last_action": f"Created by {current_user['display_name']}",
        "approved_date": None,
        "archived_date": None,
    })

    return redirect(url_for("home"))


@app.route("/claim_task/<task_id>", methods=["POST"])
def claim_task_route(task_id):
    current_user = get_current_user()
    task = next((t for t in get_all_tasks() if t["id"] == task_id), None)
    if not task or not can_claim_task(task, current_user):
        return redirect(url_for("home"))

    update_task(task_id, {
        "claimed_by": current_user["display_name"],
        "claimed_by_username": current_user["username"],
        "claimed_by_rank": current_user.get("rank_level", 0),
        "claimed_by_section": current_user.get("section", ""),
        "status": STATUS_CLAIMED,
        "last_action": f"Claimed by {current_user['display_name']}",
    })
    return redirect(url_for("home"))


@app.route("/submit_task/<task_id>", methods=["POST"])
def submit_task_route(task_id):
    current_user = get_current_user()
    task = next((t for t in get_all_tasks() if t["id"] == task_id), None)
    if not task or not can_submit_task(task, current_user):
        return redirect(url_for("home"))

    update_task(task_id, {
        "status": STATUS_PENDING,
        "rejection_note": "",
        "last_action": f"Submitted by {current_user['display_name']}",
    })
    return redirect(url_for("home"))


@app.route("/approve_task/<task_id>", methods=["POST"])
def approve_task_route(task_id):
    current_user = get_current_user()
    task = next((t for t in get_all_tasks() if t["id"] == task_id), None)
    if not task or not can_approve_task(task, current_user):
        return redirect(url_for("home"))

    claimed_by_username = task.get("claimed_by_username")
    claimant = get_user_by_username(claimed_by_username) if claimed_by_username else None
    if claimant:
        update_user(claimant["username"], {
            "points": int(claimant.get("points", 0)) + int(task.get("points", 0))
        })

    update_task(task_id, {
        "status": STATUS_APPROVED,
        "approved_date": utc_now_iso(),
        "rejection_note": "",
        "last_action": f"Approved by {current_user['display_name']}",
    })
    return redirect(url_for("home"))


@app.route("/reject_task/<task_id>", methods=["POST"])
def reject_task_route(task_id):
    current_user = get_current_user()
    task = next((t for t in get_all_tasks() if t["id"] == task_id), None)
    if not task or not can_approve_task(task, current_user):
        return redirect(url_for("home"))

    rejection_note = request.form["rejection_note"].strip()

    update_task(task_id, {
        "status": STATUS_CLAIMED,
        "rejection_note": rejection_note,
        "last_action": f"Rejected by {current_user['display_name']}: {rejection_note}",
    })
    return redirect(url_for("home"))


@app.route("/delete_task/<task_id>", methods=["POST"])
def delete_task_route(task_id):
    current_user = get_current_user()
    task = next((t for t in get_all_tasks() if t["id"] == task_id), None)
    if not task:
        return redirect(url_for("home"))

    if not (can_delete_open_task(task, current_user) or can_force_delete(current_user)):
        return redirect(url_for("home"))

    delete_task(task_id)
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
