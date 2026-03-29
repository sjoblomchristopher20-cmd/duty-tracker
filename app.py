from flask import Flask, request, redirect, url_for, render_template_string, session
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
    "PVT": 1,
    "PV2": 1,
    "PFC": 1,
    "SPC": 1,
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
}

SECTIONS = ["Maintenance", "Distro", "HQ"]
CLAIM_ACCESS_OPTIONS = ["All", "Maintenance", "Distro", "HQ"]

STATUS_AVAILABLE = "available"
STATUS_CLAIMED = "claimed"
STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_ARCHIVED = "archived"


def format_display_name(first_name: str, last_name: str, rank: str) -> str:
    first_initial = first_name[0].upper() if first_name else ""
    return f"{rank} {last_name}, {first_initial}"


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

    if is_master_admin(user):
        return task["status"] == STATUS_AVAILABLE

    if task["status"] != STATUS_AVAILABLE:
        return False

    if task["claim_access"] == "All":
        return True

    return task["claim_access"] == user["section"]


def can_claim_task(task, user):
    return can_see_task(task, user)


def can_submit_task(task, user):
    return bool(
        user
        and task.get("claimed_by") == user["display_name"]
        and task["status"] == STATUS_CLAIMED
    )


def can_delete_open_task(task, user):
    return bool(
        user
        and task["status"] == STATUS_AVAILABLE
        and (
            task["created_by"] == user["display_name"]
            or is_master_admin(user)
        )
    )


def can_see_pending_task(task, user):
    if not user or task["status"] != STATUS_PENDING:
        return False

    if is_master_admin(user):
        return True

    if not is_sgt_plus(user):
        return False

    if task["claim_access"] == "All":
        return True

    return user["section"] == task["claim_access"]


def can_approve_task(task, approver):
    if not can_see_pending_task(task, approver):
        return False

    if task.get("claimed_by") == approver["display_name"]:
        return False

    if is_master_admin(approver):
        return True

    if task["claim_access"] != "All" and approver["section"] != task["claim_access"]:
        return False

    creator_level = task.get("created_by_rank", 0)
    claimant_level = task.get("claimed_by_rank", 0) or 0
    approver_level = approver["rank_level"]

    if task["created_by"] == approver["display_name"]:
        return True

    if creator_level >= 3 and claimant_level == 1 and approver_level >= 2:
        return True

    return approver_level > creator_level


def build_leaderboard(users):
    board_users = [u for u in users if not u.get("is_master_admin")]
    return sorted(
        board_users,
        key=lambda u: (-u["points"], -u["rank_level"], u["last_name"], u["first_name"])
    )


def build_section_totals(users, section_filter="All"):
    totals = {section: 0 for section in SECTIONS}
    for user in users:
        if not user.get("is_master_admin"):
            totals[user["section"]] += user["points"]

    rows = [{"section": section, "points": points} for section, points in totals.items()]

    if section_filter != "All":
        rows = [row for row in rows if row["section"] == section_filter]

    return sorted(rows, key=lambda row: (-row["points"], row["section"]))


def filter_history(history_tasks, name_filter="", completed_section_filter="", origin_filter=""):
    filtered = history_tasks

    if name_filter:
        filtered = [t for t in filtered if t.get("claimed_by") == name_filter]

    if completed_section_filter:
        filtered = [t for t in filtered if t.get("claimed_by_section") == completed_section_filter]

    if origin_filter:
        filtered = [t for t in filtered if t.get("section_origin") == origin_filter]

    return filtered


HTML = """
<!doctype html>
<html>
<head>
    <title>Duty Tracker</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 24px;
            background: #ffffff;
            color: #111111;
        }

        h1, h2, h3 {
            margin-bottom: 10px;
        }

        h2 {
            margin-top: 30px;
        }

        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            padding-bottom: 12px;
            border-bottom: 2px solid #ddd;
            margin-bottom: 20px;
        }

        .topbar-right form {
            margin: 0;
            padding: 0;
            border: none;
            background: transparent;
            width: auto;
        }

        .login-box, .panel-form, .filter-form {
            margin-bottom: 20px;
            padding: 12px;
            border: 1px solid #ccc;
            width: 400px;
            background: #f9f9f9;
        }

        .filter-form {
            width: 100%;
            max-width: 900px;
        }

        input, select, textarea, button {
            margin: 5px 0;
            padding: 8px;
            width: 100%;
            box-sizing: border-box;
        }

        textarea {
            min-height: 70px;
            resize: vertical;
        }

        table {
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 25px;
        }

        th, td {
            border: 1px solid #ccc;
            padding: 10px;
            text-align: left;
            vertical-align: top;
        }

        th {
            background: #f2f2f2;
        }

        .claimed {
            color: #8a3b00;
            font-weight: bold;
        }

        .awaiting {
            color: #0b57d0;
            font-weight: bold;
        }

        .approved {
            color: green;
            font-weight: bold;
        }

        .archived {
            color: #666;
            font-weight: bold;
        }

        .note {
            color: #555;
            font-style: italic;
        }

        .pill {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 999px;
            background: #eee;
            font-size: 12px;
        }

        .grid-2 {
            display: grid;
            grid-template-columns: repeat(2, minmax(320px, 1fr));
            gap: 20px;
        }

        .empty-note {
            color: #666;
            font-style: italic;
            margin-top: 8px;
        }

        td form {
            margin: 0;
            padding: 0;
            border: none;
            width: auto;
            background: transparent;
        }

        td button {
            width: auto;
            min-width: 90px;
        }

        .small-input {
            width: 100%;
            margin-bottom: 6px;
        }

        .button-row {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }

        .button-row button,
        .button-row a {
            width: auto;
        }

        .tab-links {
            margin: 8px 0 18px 0;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        .tab-links a {
            text-decoration: none;
            padding: 8px 12px;
            border: 1px solid #ccc;
            background: #f7f7f7;
            color: #111;
        }

        .tab-links a.active {
            background: #e8f0fe;
            border-color: #0b57d0;
        }

        .section-buttons {
            margin: 14px 0 18px 0;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .section-buttons a {
            text-decoration: none;
            padding: 8px 12px;
            border: 1px solid #ccc;
            background: #f7f7f7;
            color: #111;
        }

        .section-buttons a.active {
            background: #e8f0fe;
            border-color: #0b57d0;
        }
    </style>
</head>
<body>
    {% if not current_user %}
        <h1>Duty Tracker</h1>

        <div class="section-buttons">
            {% for option in public_section_options %}
                <a href="/?public_section={{ option }}" class="{% if public_section == option %}active{% endif %}">
                    {{ option }}
                </a>
            {% endfor %}
        </div>

        <h2>Section Leaderboard{% if public_section != "All" %} - {{ public_section }}{% endif %}</h2>
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

        <form class="login-box" method="POST" action="/login">
            <h2>Login</h2>
            <input type="hidden" name="public_section" value="{{ public_section }}">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
            {% if login_error %}
                <p class="note">{{ login_error }}</p>
            {% endif %}
        </form>

    {% else %}
        <div class="topbar">
            <div>
                <h1>Duty Tracker</h1>
                <div>
                    Logged in as <strong>{{ current_user.display_name }}</strong>
                    {% if current_user.is_master_admin %} | Master Admin{% endif %}
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

        {% if can_create_users %}
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
                    <form method="POST" action="/delete_user/{{ user.username }}">
                        <button type="submit">Delete User</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
        {% endif %}

        {% if can_create_tasks %}
        <h2>Task Controls</h2>
        <form class="panel-form" method="POST" action="/add_task">
            <h3>Create Task</h3>
            <input type="text" name="title" placeholder="Task title" required>
            <input type="number" name="points" placeholder="Points" min="1" required>

            {% if is_msg_plus %}
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
            {% else %}
            <input type="hidden" name="section_origin" value="{{ current_user.section }}">
            <input type="hidden" name="claim_access" value="All">
            <p class="note">Task origin defaults to your section. Scope defaults to All.</p>
            {% endif %}

            <button type="submit">Create Task</button>
        </form>
        {% endif %}

        <h2>Available Tasks</h2>
        {% if available_tasks %}
        <table>
            <tr>
                <th>Task</th>
                <th>Points</th>
                <th>Origin</th>
                <th>Claim Access</th>
                <th>Created By</th>
                <th>Action</th>
            </tr>
            {% for task in available_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.section_origin }}</td>
                <td><span class="pill">{{ task.claim_access }}</span></td>
                <td>{{ task.created_by }}</td>
                <td>
                    <div class="button-row">
                        {% if can_claim_map[task.id] %}
                        <form method="POST" action="/claim_task/{{ task.id }}">
                            <button type="submit">Claim</button>
                        </form>
                        {% endif %}

                        {% if can_delete_map[task.id] %}
                        <form method="POST" action="/delete_task/{{ task.id }}">
                            <button type="submit">Delete</button>
                        </form>
                        {% endif %}
                    </div>
                </td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p class="empty-note">No available tasks right now.</p>
        {% endif %}

        <h2>My Tasks</h2>
        {% if my_tasks %}
        <table>
            <tr>
                <th>Task</th>
                <th>Points</th>
                <th>Origin</th>
                <th>Status</th>
                <th>Rejection Note</th>
                <th>Action</th>
            </tr>
            {% for task in my_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.section_origin }}</td>
                <td>
                    {% if task.status == "claimed" %}
                        <span class="claimed">Claimed</span>
                    {% elif task.status == "pending_approval" %}
                        <span class="awaiting">Pending Approval</span>
                    {% endif %}
                </td>
                <td>{{ task.rejection_note or "-" }}</td>
                <td>
                    {% if task.status == "claimed" and can_submit_map[task.id] %}
                    <form method="POST" action="/submit_task/{{ task.id }}">
                        <button type="submit">Submit for Approval</button>
                    </form>
                    {% elif task.status == "pending_approval" %}
                    <span class="note">Waiting on approval</span>
                    {% else %}
                    <span class="note">Waiting</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p class="empty-note">You have no active tasks right now.</p>
        {% endif %}

        {% if can_create_tasks %}
        <h2>Approval Queue</h2>
        {% if pending_tasks %}
        <table>
            <tr>
                <th>Task</th>
                <th>Points</th>
                <th>Created By</th>
                <th>Claimed By</th>
                <th>Claimed By Section</th>
                <th>Approve</th>
                <th>Reject</th>
            </tr>
            {% for task in pending_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.created_by }}</td>
                <td>{{ task.claimed_by }}</td>
                <td>{{ task.claimed_by_section }}</td>
                <td>
                    {% if can_approve_map[task.id] %}
                    <form method="POST" action="/approve_task/{{ task.id }}">
                        <button type="submit">Approve</button>
                    </form>
                    {% else %}
                    <span class="note">Not authorized</span>
                    {% endif %}
                </td>
                <td>
                    {% if can_approve_map[task.id] %}
                    <form method="POST" action="/reject_task/{{ task.id }}">
                        <select class="small-input" name="rejection_action" required>
                            <option value="return">Return to claimant</option>
                            <option value="reopen">Reject and reopen</option>
                        </select>
                        <textarea name="rejection_note" placeholder="Optional note"></textarea>
                        <button type="submit">Reject</button>
                    </form>
                    {% else %}
                    <span class="note">Not authorized</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p class="empty-note">No tasks pending approval.</p>
        {% endif %}
        {% endif %}

        <h2>History</h2>
        <div class="tab-links">
            <a href="/?history_tab=approved" class="{% if history_tab == 'approved' %}active{% endif %}">Approved</a>
            {% if can_see_archived %}
            <a href="/?history_tab=archived" class="{% if history_tab == 'archived' %}active{% endif %}">Archived</a>
            {% endif %}
        </div>

        {% if can_create_tasks %}
        <form class="filter-form" method="GET" action="/">
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
                <div>
                    <label>Origin Section</label>
                    <select name="filter_origin">
                        <option value="">All</option>
                        {% for section in sections %}
                        <option value="{{ section }}" {% if filter_origin == section %}selected{% endif %}>{{ section }}</option>
                        {% endfor %}
                    </select>
                </div>
            </div>
            <div class="button-row">
                <button type="submit">Apply Filters</button>
                <a href="/?history_tab={{ history_tab }}">Clear Filters</a>
            </div>
        </form>
        <p class="note">Showing {{ history_rows|length }} task(s).</p>
        {% endif %}

        {% if history_rows %}
        <table>
            <tr>
                <th>Task</th>
                <th>Points</th>
                <th>Origin</th>
                <th>Completed By</th>
                <th>Completed By Section</th>
                <th>Status</th>
                <th>Approved Date</th>
                {% if history_tab == "archived" %}
                <th>Archived Date</th>
                {% endif %}
                {% if can_force_delete %}
                <th>Force Delete</th>
                {% endif %}
            </tr>
            {% for task in history_rows %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.section_origin }}</td>
                <td>{{ task.claimed_by }}</td>
                <td>{{ task.claimed_by_section }}</td>
                <td>
                    {% if task.status == "approved" %}
                    <span class="approved">Approved</span>
                    {% elif task.status == "archived" %}
                    <span class="archived">Archived</span>
                    {% endif %}
                </td>
                <td>{{ task.approved_date or "-" }}</td>
                {% if history_tab == "archived" %}
                <td>{{ task.archived_date or "-" }}</td>
                {% endif %}
                {% if can_force_delete %}
                <td>
                    <form method="POST" action="/force_delete_task/{{ task.id }}">
                        <button type="submit">Force Delete</button>
                    </form>
                </td>
                {% endif %}
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p class="empty-note">No tasks found for this history view.</p>
        {% endif %}
    {% endif %}
</body>
</html>
"""


@app.route("/setup")
def setup():
    if not get_user_by_username("training_room"):
        create_user({
            "username": "training_room",
            "password": "admin123",
            "first_name": "Training",
            "last_name": "Room",
            "display_name": "Training Room",
            "rank": "ADMIN",
            "rank_level": 99,
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
            login_error=session.pop("login_error", None),
            public_section=public_section,
            public_section_options=["All"] + SECTIONS,
            public_section_rows=build_section_totals(all_users, public_section),
        )

    leaderboard = build_leaderboard(all_users)
    section_totals = build_section_totals(all_users)

    available_tasks = [
        task for task in all_tasks
        if task["status"] == STATUS_AVAILABLE and can_see_task(task, current_user)
    ]

    my_tasks = [
        task for task in all_tasks
        if task.get("claimed_by") == current_user["display_name"]
        and task["status"] in [STATUS_CLAIMED, STATUS_PENDING]
    ]

    pending_tasks = [
        task for task in all_tasks
        if can_see_pending_task(task, current_user)
    ]

    approved_history = [task for task in all_tasks if task["status"] == STATUS_APPROVED]
    archived_history = [task for task in all_tasks if task["status"] == STATUS_ARCHIVED]

    base_history = approved_history if history_tab == "approved" else archived_history
    history_rows = filter_history(
        base_history,
        name_filter=filter_name,
        completed_section_filter=filter_completed_section,
        origin_filter=filter_origin,
    )

    completed_names = sorted({
        task["claimed_by"]
        for task in approved_history + archived_history
        if task.get("claimed_by")
    })

    can_claim_map = {task["id"]: can_claim_task(task, current_user) for task in available_tasks}
    can_submit_map = {task["id"]: can_submit_task(task, current_user) for task in my_tasks}
    can_approve_map = {task["id"]: can_approve_task(task, current_user) for task in pending_tasks}
    can_delete_map = {task["id"]: can_delete_open_task(task, current_user) for task in available_tasks}

    resettable_users = [u for u in all_users if not u.get("is_master_admin")]
    manageable_users = [u for u in all_users if not u.get("is_master_admin")]

    return render_template_string(
        HTML,
        current_user=current_user,
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
    if user and user["password"] == password:
        session["username"] = user["username"]
        return redirect(url_for("home"))

    session["login_error"] = "Invalid username or password."
    return redirect(url_for("home", public_section=public_section))


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
        "display_name": format_display_name(first_name, last_name, rank),
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
    points = int(request.form["points"])
    section_origin = request.form["section_origin"]
    claim_access = request.form["claim_access"]

    if not title or points < 1 or section_origin not in SECTIONS or claim_access not in CLAIM_ACCESS_OPTIONS:
        return redirect(url_for("home"))

    create_task({
        "title": title,
        "points": points,
        "section_origin": section_origin,
        "claim_access": claim_access,
        "created_by": current_user["display_name"],
        "created_by_rank": current_user["rank_level"],
        "created_by_section": current_user["section"],
        "claimed_by": None,
        "claimed_by_rank": None,
        "claimed_by_section": None,
        "status": STATUS_AVAILABLE,
        "rejection_note": "",
        "last_action": "Created",
        "approved_date": None,
        "archived_date": None,
    })

    return redirect(url_for("home"))


@app.route("/claim_task/<task_id>", methods=["POST"])
def claim_task_route(task_id):
    current_user = get_current_user()
    task = get_task(task_id)
    if not current_user or not task:
        return redirect(url_for("home"))

    if can_claim_task(task, current_user):
        update_task(task_id, {
            "claimed_by": current_user["display_name"],
            "claimed_by_rank": current_user["rank_level"],
            "claimed_by_section": current_user["section"],
            "status": STATUS_CLAIMED,
            "rejection_note": "",
            "last_action": f"Claimed by {current_user['display_name']}",
        })

    return redirect(url_for("home"))


@app.route("/submit_task/<task_id>", methods=["POST"])
def submit_task_route(task_id):
    current_user = get_current_user()
    task = get_task(task_id)
    if not current_user or not task:
        return redirect(url_for("home"))

    if can_submit_task(task, current_user):
        update_task(task_id, {
            "status": STATUS_PENDING,
            "last_action": f"Submitted by {current_user['display_name']}",
        })

    return redirect(url_for("home"))


@app.route("/approve_task/<task_id>", methods=["POST"])
def approve_task_route(task_id):
    current_user = get_current_user()
    task = get_task(task_id)
    if not current_user or not task or not can_approve_task(task, current_user):
        return redirect(url_for("home"))

    completer = get_user_by_display_name(task["claimed_by"])
    if completer and not completer.get("is_master_admin"):
        update_user(completer["username"], {
            "points": completer["points"] + task["points"]
        })

    update_task(task_id, {
        "status": STATUS_APPROVED,
        "rejection_note": "",
        "approved_date": utc_now_iso(),
        "last_action": f"Approved by {current_user['display_name']}",
    })

    return redirect(url_for("home"))


@app.route("/reject_task/<task_id>", methods=["POST"])
def reject_task_route(task_id):
    current_user = get_current_user()
    task = get_task(task_id)
    if not current_user or not task or not can_approve_task(task, current_user):
        return redirect(url_for("home"))

    rejection_action = request.form["rejection_action"]
    rejection_note = request.form.get("rejection_note", "").strip()

    if rejection_action == "return":
        update_task(task_id, {
            "status": STATUS_CLAIMED,
            "rejection_note": rejection_note,
            "last_action": f"Returned to claimant by {current_user['display_name']}",
        })
    elif rejection_action == "reopen":
        update_task(task_id, {
            "status": STATUS_AVAILABLE,
            "claimed_by": None,
            "claimed_by_rank": None,
            "claimed_by_section": None,
            "rejection_note": rejection_note,
            "last_action": f"Rejected and reopened by {current_user['display_name']}",
        })

    return redirect(url_for("home"))


@app.route("/delete_task/<task_id>", methods=["POST"])
def delete_task_route(task_id):
    current_user = get_current_user()
    task = get_task(task_id)
    if not current_user or not task:
        return redirect(url_for("home"))

    if can_delete_open_task(task, current_user):
        delete_task(task_id)

    return redirect(url_for("home"))


@app.route("/force_delete_task/<task_id>", methods=["POST"])
def force_delete_task_route(task_id):
    current_user = get_current_user()
    if not can_force_delete(current_user):
        return redirect(url_for("home"))

    if get_task(task_id):
        delete_task(task_id)

    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
