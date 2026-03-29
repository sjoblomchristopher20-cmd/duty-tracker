import os

from flask import Flask, request, redirect, url_for, session, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash

from storage import (
    get_all_users,
    get_user_by_username,
    create_user,
    update_user,
    delete_user,
    get_all_tasks,
    get_task,
    create_task,
    update_task,
    delete_task,
    auto_archive_old_tasks,
    utc_now_iso,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

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
    "2LT": 9,
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
        .grid-3 {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 16px;
            margin-bottom: 24px;
        }
        .panel-form, .panel, .stat-card {
            border: 1px solid #ddd;
            padding: 16px;
            margin-bottom: 20px;
            background: #fafafa;
        }
        .stat-value {
            font-size: 28px;
            font-weight: bold;
            margin-top: 8px;
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
        .success {
            color: #0b6b2c;
            margin: 8px 0;
            font-weight: bold;
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
        .admin-actions form {
            display: inline-block;
            margin-right: 8px;
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
            {% if message %}
                <p class="success">{{ message }}</p>
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
                {% if not current_user.is_active %} | <span class="note">INACTIVE</span>{% endif %}
            </div>
        </div>
        <div class="topbar-right">
            <form method="POST" action="/logout">
                <button type="submit">Logout</button>
            </form>
        </div>
    </div>

    {% if message %}
        <p class="success">{{ message }}</p>
    {% endif %}
    {% if error %}
        <p class="note">{{ error }}</p>
    {% endif %}

    <div class="grid-3">
        <div class="stat-card">
            <div>Available Tasks</div>
            <div class="stat-value">{{ available_tasks|length }}</div>
        </div>
        <div class="stat-card">
            <div>My Active Tasks</div>
            <div class="stat-value">{{ my_tasks|length }}</div>
        </div>
        <div class="stat-card">
            <div>Pending Approval</div>
            <div class="stat-value">{{ pending_tasks|length }}</div>
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
                    <th>Status</th>
                </tr>
                {% for user in leaderboard %}
                <tr>
                    <td>{{ user.display_name }}</td>
                    <td>{{ user.section }}</td>
                    <td>{{ user.points }}</td>
                    <td>{% if user.is_active %}Active{% else %}Inactive{% endif %}</td>
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
            <th>First Name</th>
            <th>Last Name</th>
            <th>Username</th>
            <th>Rank</th>
            <th>Section</th>
            <th>Points</th>
            <th>Status</th>
            <th>Save</th>
            <th>Actions</th>
        </tr>
        {% for user in manageable_users %}
        <tr>
            <form method="POST" action="/update_user/{{ user.username }}">
                <td>{{ user.first_name }}</td>
                <td>
                    <input type="text" name="last_name" value="{{ user.last_name }}" required>
                </td>
                <td>{{ user.username }}</td>
                <td>
                    <select name="rank" required>
                        {% for rank_name in rank_names %}
                            <option value="{{ rank_name }}" {% if user.rank == rank_name %}selected{% endif %}>
                                {{ rank_name }}
                            </option>
                        {% endfor %}
                    </select>
                </td>
                <td>
                    <select name="section" required>
                        {% for section in sections %}
                            <option value="{{ section }}" {% if user.section == section %}selected{% endif %}>
                                {{ section }}
                            </option>
                        {% endfor %}
                    </select>
                </td>
                <td>{{ user.points }}</td>
                <td>{% if user.is_active %}Active{% else %}Inactive{% endif %}</td>
                <td>
                    <button type="submit">Save</button>
                </td>
            </form>
            <td class="admin-actions">
                <form class="inline-form" method="POST" action="/toggle_user_active/{{ user.username }}">
                    <button type="submit">
                        {% if user.is_active %}Deactivate{% else %}Activate{% endif %}
                    </button>
                </form>

                {% if not user.is_active %}
                <form class="inline-form" method="POST" action="/delete_user/{{ user.username }}">
                    <button type="submit">Delete</button>
                </form>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    {% if can_create_tasks %}
    <h2>Task Controls</h2>
    <form class="panel-form" method="POST" action="/add_task" style="max-width: 520px;">
        <h3>Create Task</h3>
        <input type="text" name="title" placeholder="Task title" required>
        <input type="number" name="points" placeholder="Points" min="1" required>

        <label>Claim Access</label>
        <select name="claim_access" required>
            {% for option in claim_access_options %}
                <option value="{{ option }}">{{ option }}</option>
            {% endfor %}
        </select>

        <label>Due Date (optional)</label>
        <input type="date" name="due_date">

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
                <th>Due</th>
                <th>Action</th>
            </tr>
            {% for task in available_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.section_origin }}</td>
                <td>{{ task.claim_access }}</td>
                <td>{{ task.due_date or "" }}</td>
                <td>
                    {% if can_claim_map[task.id] %}
                    <form class="inline-form" method="POST" action="/claim_task/{{ task.id }}" style="display:inline-block;">
                        <button type="submit">Claim</button>
                    </form>
                    {% endif %}

                    {% if can_delete_map[task.id] %}
                    <form class="inline-form" method="POST" action="/delete_task/{{ task.id }}" style="display:inline-block;">
                        <button type="submit">Delete</button>
                    </form>
                    {% endif %}

                    {% if not can_claim_map[task.id] and not can_delete_map[task.id] %}
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
                <th>Due</th>
                <th>Rejection Note</th>
                <th>Action</th>
            </tr>
            {% for task in my_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.status }}</td>
                <td>{{ task.due_date or "" }}</td>
                <td>{{ task.rejection_note or "" }}</td>
                <td>
                    {% if can_submit_map[task.id] %}
                    <form class="inline-form" method="POST" action="/submit_task/{{ task.id }}" style="display:inline-block;">
                        <button type="submit">Submit</button>
                    </form>
                    {% endif %}

                    {% if can_delete_map[task.id] %}
                    <form class="inline-form" method="POST" action="/delete_task/{{ task.id }}" style="display:inline-block;">
                        <button type="submit">Delete</button>
                    </form>
                    {% endif %}

                    {% if not can_submit_map[task.id] and not can_delete_map[task.id] %}
                    <span class="muted">Waiting</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    {% else %}
        <p class="muted">You have no active tasks right now.</p>
    {% endif %}

    {% if can_approve %}
    <h2>Approval Queue</h2>
    {% if pending_tasks %}
        <table>
            <tr>
                <th>Title</th>
                <th>Points</th>
                <th>Completed By</th>
                <th>Completed Rank</th>
                <th>Section</th>
                <th>Submitted</th>
                <th>Action</th>
            </tr>
            {% for task in pending_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.claimed_by }}</td>
                <td>{{ rank_name_from_level(task.claimed_by_rank) }}</td>
                <td>{{ task.claimed_by_section }}</td>
                <td>{{ task.submitted_at or "" }}</td>
                <td>
                    {% if can_approve_map[task.id] %}
                    <form class="inline-form" method="POST" action="/approve_task/{{ task.id }}" style="display:inline-block;">
                        <button type="submit">Approve</button>
                    </form>
                    <form class="inline-form" method="POST" action="/reject_task/{{ task.id }}" style="display:inline-block;">
                        <input type="text" name="rejection_note" placeholder="Reason" required>
                        <button type="submit">Reject</button>
                    </form>
                    {% endif %}

                    {% if can_delete_map[task.id] %}
                    <form class="inline-form" method="POST" action="/delete_task/{{ task.id }}" style="display:inline-block;">
                        <button type="submit">Delete</button>
                    </form>
                    {% endif %}

                    {% if not can_approve_map[task.id] and not can_delete_map[task.id] %}
                    <span class="muted">No access</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    {% else %}
        <p class="muted">No tasks pending approval.</p>
    {% endif %}
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
                <th>Approved By</th>
                <th>Rejected By</th>
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
                <td>{{ task.approved_by or "" }}</td>
                <td>{{ task.rejected_by or "" }}</td>
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


def format_display_name(first_name: str, last_name: str) -> str:
    return f"{first_name} {last_name}".strip()


def set_message(text: str):
    session["message"] = text


def set_error(text: str):
    session["error"] = text


def pop_message():
    return session.pop("message", None)


def pop_error():
    return session.pop("error", None)


def rank_name_from_level(level):
    try:
        level = int(level or 0)
    except (TypeError, ValueError):
        return ""
    matches = [name for name, value in RANKS.items() if value == level]
    return " / ".join(matches) if matches else str(level)


def get_current_user():
    username = session.get("username")
    if not username:
        return None
    return get_user_by_username(username)


def is_master_admin(user):
    return bool(user and user.get("is_master_admin"))


def is_sgt_plus(user):
    return bool(user and int(user.get("rank_level", 0)) >= 2)


def can_create_tasks(user):
    return is_master_admin(user) or is_sgt_plus(user)


def can_approve_tasks(user):
    return bool(user) and (is_master_admin(user) or is_sgt_plus(user))


def can_claim_task(task, user):
    if not user or not user.get("is_active", True):
        return False

    if task.get("status") != STATUS_AVAILABLE:
        return False

    if task.get("claim_access") != "All" and user.get("section") != task.get("claim_access"):
        return False

    return True


def can_submit_task(task, user):
    return (
        bool(user)
        and task.get("claimed_by_username") == user.get("username")
        and task.get("status") == STATUS_CLAIMED
    )


def can_approve_task(task, user):
    if not user or task.get("status") != STATUS_PENDING:
        return False

    if is_master_admin(user):
        return True

    if user.get("section") != task.get("section_origin"):
        return False

    approver_rank = int(user.get("rank_level", 0) or 0)
    claimant_rank = int(task.get("claimed_by_rank", 0) or 0)

    return approver_rank >= claimant_rank + 1


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
    active_users = [u for u in users if u.get("is_active", True)]
    return sorted(active_users, key=lambda u: (-int(u.get("points", 0)), u.get("display_name", "")))


def build_section_totals(users, only_section=None):
    rows = []
    for section in SECTIONS:
        if only_section and section != only_section:
            continue
        total = sum(
            int(u.get("points", 0) or 0)
            for u in users
            if u.get("section") == section and u.get("is_active", True)
        )
        rows.append({"section": section, "points": total})
    return rows


@app.context_processor
def inject_helpers():
    return {
        "rank_name_from_level": rank_name_from_level,
    }


@app.route("/setup", methods=["GET"])
def setup():
    existing = get_user_by_username("training_room")
    if not existing:
        create_user({
            "username": "training_room",
            "first_name": "Training",
            "last_name": "Room",
            "display_name": "Training Room",
            "password": generate_password_hash("admin123"),
            "rank": "ADMIN",
            "rank_level": 999,
            "section": "HQ",
            "points": 0,
            "is_master_admin": True,
            "is_active": True,
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
            can_approve=False,
            login_error=session.pop("login_error", None),
            message=pop_message(),
            error=pop_error(),
            public_section=public_section,
            public_section_options=["All"] + SECTIONS,
            public_section_rows=build_section_totals(
                all_users,
                None if public_section == "All" else public_section
            ),
        )

    show_admin_panel = is_master_admin(current_user)
    can_approve = can_approve_tasks(current_user)

    leaderboard = build_leaderboard(all_users)
    section_totals = build_section_totals(all_users)

    available_tasks = [
        task for task in all_tasks
        if task.get("status") == STATUS_AVAILABLE
        and (task.get("claim_access") == "All" or current_user.get("section") == task.get("claim_access"))
    ]

    my_tasks = [
        task for task in all_tasks
        if task.get("claimed_by_username") == current_user.get("username")
        and task.get("status") in [STATUS_CLAIMED, STATUS_PENDING]
    ]

    pending_tasks = [
        task for task in all_tasks
        if can_approve_task(task, current_user)
    ]

    approved_history = [task for task in all_tasks if task.get("status") == STATUS_APPROVED]
    archived_history = [task for task in all_tasks if task.get("status") == STATUS_ARCHIVED]
    history_rows = approved_history if history_tab == "approved" else archived_history

    if filter_name:
        history_rows = [t for t in history_rows if (t.get("claimed_by") or "") == filter_name]
    if filter_completed_section:
        history_rows = [t for t in history_rows if (t.get("claimed_by_section") or "") == filter_completed_section]
    if filter_origin:
        history_rows = [t for t in history_rows if (t.get("section_origin") or "") == filter_origin]

    completed_names = sorted(
        {t.get("claimed_by") for t in approved_history + archived_history if t.get("claimed_by")}
    )

    can_claim_map = {task["id"]: can_claim_task(task, current_user) for task in available_tasks}
    can_submit_map = {task["id"]: can_submit_task(task, current_user) for task in my_tasks}
    can_approve_map = {task["id"]: can_approve_task(task, current_user) for task in pending_tasks}

    all_visible_tasks_for_delete = available_tasks + my_tasks + pending_tasks + history_rows
    can_delete_map = {
        task["id"]: can_delete_open_task(task, current_user) or is_master_admin(current_user)
        for task in all_visible_tasks_for_delete
    }

    resettable_users = [u for u in all_users if not u.get("is_master_admin")]
    manageable_users = [u for u in all_users if not u.get("is_master_admin")]

    return render_template_string(
        HTML,
        current_user=current_user,
        show_admin_panel=show_admin_panel,
        can_create_tasks=can_create_tasks(current_user),
        can_approve=can_approve,
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
        message=pop_message(),
        error=pop_error(),
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
    if not user:
        session["login_error"] = "Invalid username or password."
        return redirect(url_for("home", public_section=public_section))

    stored_password = user.get("password", "")
    valid_password = False

    if stored_password.startswith("pbkdf2:") or stored_password.startswith("scrypt:"):
        valid_password = check_password_hash(stored_password, password)
    else:
        valid_password = stored_password == password
        if valid_password:
            update_user(user["username"], {"password": generate_password_hash(password)})

    if not valid_password:
        session["login_error"] = "Invalid username or password."
        return redirect(url_for("home", public_section=public_section))

    if not user.get("is_active", True):
        session["login_error"] = "This account is inactive."
        return redirect(url_for("home", public_section=public_section))

    session["username"] = user["username"]
    update_user(user["username"], {"last_login_at": utc_now_iso()})
    set_message("Login successful.")
    return redirect(url_for("home"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/add_user", methods=["POST"])
def add_user_route():
    current_user = get_current_user()
    if not is_master_admin(current_user):
        set_error("Unauthorized.")
        return redirect(url_for("home"))

    first_name = request.form["first_name"].strip()
    last_name = request.form["last_name"].strip()
    password = request.form["password"]
    rank = request.form["rank"]
    section = request.form["section"]

    if not first_name or not last_name or rank not in RANKS or section not in SECTIONS:
        set_error("Invalid user data.")
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
        "password": generate_password_hash(password),
        "rank": rank,
        "rank_level": RANKS[rank],
        "section": section,
        "points": 0,
        "is_master_admin": False,
        "is_active": True,
        "created_at": utc_now_iso(),
    })
    set_message(f"User created: {username}")
    return redirect(url_for("home"))


@app.route("/reset_password", methods=["POST"])
def reset_password():
    current_user = get_current_user()
    if not is_master_admin(current_user):
        set_error("Unauthorized.")
        return redirect(url_for("home"))

    target_username = request.form["target_username"].strip()
    new_password = request.form["new_password"]

    target_user = get_user_by_username(target_username)
    if target_user and not target_user.get("is_master_admin") and new_password:
        update_user(target_username, {"password": generate_password_hash(new_password)})
        set_message(f"Password reset for {target_username}.")
    else:
        set_error("Could not reset password.")

    return redirect(url_for("home"))


@app.route("/update_user/<username>", methods=["POST"])
def update_user_route(username):
    current_user = get_current_user()
    if not is_master_admin(current_user):
        set_error("Unauthorized.")
        return redirect(url_for("home"))

    target_user = get_user_by_username(username)
    if not target_user or target_user.get("is_master_admin"):
        set_error("Cannot update that user.")
        return redirect(url_for("home"))

    last_name = request.form["last_name"].strip()
    rank = request.form["rank"]
    section = request.form["section"]

    if not last_name or rank not in RANKS or section not in SECTIONS:
        set_error("Invalid user update.")
        return redirect(url_for("home"))

    update_user(username, {
        "last_name": last_name,
        "display_name": format_display_name(target_user.get("first_name", ""), last_name),
        "rank": rank,
        "rank_level": RANKS[rank],
        "section": section,
    })

    set_message(f"Updated user {username}.")
    return redirect(url_for("home"))


@app.route("/toggle_user_active/<username>", methods=["POST"])
def toggle_user_active(username):
    current_user = get_current_user()
    if not is_master_admin(current_user):
        set_error("Unauthorized.")
        return redirect(url_for("home"))

    target_user = get_user_by_username(username)
    if not target_user or target_user.get("is_master_admin"):
        set_error("Cannot modify that user.")
        return redirect(url_for("home"))

    new_state = not bool(target_user.get("is_active", True))
    update_user(username, {"is_active": new_state})
    set_message(f"{username} is now {'active' if new_state else 'inactive'}.")
    return redirect(url_for("home"))


@app.route("/delete_user/<username>", methods=["POST"])
def delete_user_route(username):
    current_user = get_current_user()
    if not is_master_admin(current_user):
        set_error("Unauthorized.")
        return redirect(url_for("home"))

    target_user = get_user_by_username(username)
    if not target_user:
        set_error("User not found.")
        return redirect(url_for("home"))

    if target_user.get("is_master_admin"):
        set_error("Cannot delete that user.")
        return redirect(url_for("home"))

    if target_user.get("is_active", True):
        set_error("Deactivate the user before deleting them.")
        return redirect(url_for("home"))

    delete_user(username)
    set_message(f"Deleted user {username}.")
    return redirect(url_for("home"))


@app.route("/add_task", methods=["POST"])
def add_task_route():
    current_user = get_current_user()
    if not can_create_tasks(current_user):
        set_error("Unauthorized.")
        return redirect(url_for("home"))

    title = request.form["title"].strip()
    try:
        points = int(request.form["points"])
    except (KeyError, ValueError, TypeError):
        set_error("Invalid task values.")
        return redirect(url_for("home"))

    claim_access = request.form["claim_access"]
    due_date = request.form.get("due_date", "").strip() or None
    section_origin = current_user.get("section", "")
    min_rank_level = 1

    if not title or points < 1 or section_origin not in SECTIONS or claim_access not in CLAIM_ACCESS_OPTIONS:
        set_error("Invalid task data.")
        return redirect(url_for("home"))

    create_task({
        "title": title,
        "points": points,
        "section_origin": section_origin,
        "claim_access": claim_access,
        "min_rank_level": min_rank_level,
        "due_date": due_date,
        "created_by": current_user["username"],
        "created_by_rank": current_user.get("rank_level", 0),
        "created_by_section": current_user.get("section", ""),
        "claimed_by": None,
        "claimed_by_username": None,
        "claimed_by_rank": None,
        "claimed_by_section": None,
        "claimed_at": None,
        "submitted_at": None,
        "approved_at": None,
        "approved_by": None,
        "approved_by_rank": None,
        "approved_by_section": None,
        "rejected_at": None,
        "rejected_by": None,
        "rejected_by_rank": None,
        "rejected_by_section": None,
        "status": STATUS_AVAILABLE,
        "rejection_note": "",
        "last_action": f"Created by {current_user['display_name']}",
        "approved_date": None,
        "archived_date": None,
    })
    set_message("Task created.")
    return redirect(url_for("home"))


@app.route("/claim_task/<task_id>", methods=["POST"])
def claim_task_route(task_id):
    current_user = get_current_user()
    task = get_task(task_id)
    if not task or not can_claim_task(task, current_user):
        set_error("You cannot claim that task.")
        return redirect(url_for("home"))

    update_task(task_id, {
        "claimed_by": current_user["display_name"],
        "claimed_by_username": current_user["username"],
        "claimed_by_rank": current_user.get("rank_level", 0),
        "claimed_by_section": current_user.get("section", ""),
        "claimed_at": utc_now_iso(),
        "status": STATUS_CLAIMED,
        "last_action": f"Claimed by {current_user['display_name']}",
    })
    set_message("Task claimed.")
    return redirect(url_for("home"))


@app.route("/submit_task/<task_id>", methods=["POST"])
def submit_task_route(task_id):
    current_user = get_current_user()
    task = get_task(task_id)
    if not task or not can_submit_task(task, current_user):
        set_error("You cannot submit that task.")
        return redirect(url_for("home"))

    update_task(task_id, {
        "status": STATUS_PENDING,
        "submitted_at": utc_now_iso(),
        "rejection_note": "",
        "last_action": f"Submitted by {current_user['display_name']}",
    })
    set_message("Task submitted for approval.")
    return redirect(url_for("home"))


@app.route("/approve_task/<task_id>", methods=["POST"])
def approve_task_route(task_id):
    current_user = get_current_user()
    if not can_approve_tasks(current_user):
        return "Unauthorized", 403

    task = get_task(task_id)
    if not task or not can_approve_task(task, current_user):
        set_error("You cannot approve that task.")
        return redirect(url_for("home"))

    claimed_by_username = task.get("claimed_by_username")
    claimant = get_user_by_username(claimed_by_username) if claimed_by_username else None
    if claimant:
        update_user(claimant["username"], {
            "points": int(claimant.get("points", 0) or 0) + int(task.get("points", 0) or 0)
        })

    now_iso = utc_now_iso()
    update_task(task_id, {
        "status": STATUS_APPROVED,
        "approved_at": now_iso,
        "approved_date": now_iso,
        "approved_by": current_user["display_name"],
        "approved_by_rank": current_user.get("rank_level", 0),
        "approved_by_section": current_user.get("section", ""),
        "rejection_note": "",
        "last_action": f"Approved by {current_user['display_name']}",
    })
    set_message("Task approved.")
    return redirect(url_for("home"))


@app.route("/reject_task/<task_id>", methods=["POST"])
def reject_task_route(task_id):
    current_user = get_current_user()
    if not can_approve_tasks(current_user):
        return "Unauthorized", 403

    task = get_task(task_id)
    if not task or not can_approve_task(task, current_user):
        set_error("You cannot reject that task.")
        return redirect(url_for("home"))

    rejection_note = request.form["rejection_note"].strip()

    update_task(task_id, {
        "status": STATUS_CLAIMED,
        "rejection_note": rejection_note,
        "rejected_at": utc_now_iso(),
        "rejected_by": current_user["display_name"],
        "rejected_by_rank": current_user.get("rank_level", 0),
        "rejected_by_section": current_user.get("section", ""),
        "last_action": f"Rejected by {current_user['display_name']}: {rejection_note}",
    })
    set_message("Task rejected and returned to claimant.")
    return redirect(url_for("home"))


@app.route("/delete_task/<task_id>", methods=["POST"])
def delete_task_route(task_id):
    current_user = get_current_user()
    task = get_task(task_id)
    if not task:
        set_error("Task not found.")
        return redirect(url_for("home"))

    if not (can_delete_open_task(task, current_user) or is_master_admin(current_user)):
        set_error("You cannot delete that task.")
        return redirect(url_for("home"))

    if task.get("status") == STATUS_APPROVED:
        claimed_by_username = task.get("claimed_by_username")
        claimant = get_user_by_username(claimed_by_username) if claimed_by_username else None
        if claimant:
            current_points = int(claimant.get("points", 0) or 0)
            task_points = int(task.get("points", 0) or 0)
            new_points = max(0, current_points - task_points)
            update_user(claimant["username"], {"points": new_points})

    delete_task(task_id)
    set_message("Task deleted.")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
