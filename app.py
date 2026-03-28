from flask import Flask, request, redirect, url_for, render_template_string, session

app = Flask(__name__)
app.secret_key = "change-this-to-a-secret-value"

RANKS = {
    "PVT": 1,
    "PV2": 1,
    "PFC": 1,
    "SPC": 1,
    "SGT": 2,
    "SSG": 3,
    "SFC": 4,
    "1SG": 5,
    "CW1": 6,
    "CW2": 7,
    "2LT": 8,
    "1LT": 9,
    "CPT": 10,
}

SECTIONS = ["Maintenance", "Distro", "HQ"]
CLAIM_ACCESS_OPTIONS = ["All", "Maintenance", "Distro", "HQ"]

users = [
    {
        "name": "Christopher",
        "username": "christopher",
        "password": "Temp123!",
        "rank": "SSG",
        "rank_level": RANKS["SSG"],
        "section": "Distro",
        "points": 0,
    }
]

tasks = [
    {
        "id": 1,
        "title": "Mop hallway",
        "points": 10,
        "section_origin": "HQ",
        "claim_access": "All",
        "created_by": "Christopher",
        "created_by_rank": RANKS["SSG"],
        "claimed_by": None,
        "claimed_by_rank": None,
        "claimed_by_section": None,
        "status": "available",
        "rejection_note": "",
        "last_action": "",
    }
]


def get_user_by_username(username):
    for user in users:
        if user["username"] == username:
            return user
    return None


def get_current_user():
    username = session.get("username")
    if not username:
        return None
    return get_user_by_username(username)


def is_admin(user):
    return user and user["rank_level"] >= 2  # SGT+


def can_claim(task, user):
    if not user:
        return False
    if task["status"] != "available":
        return False
    if task["claim_access"] == "All":
        return True
    return task["claim_access"] == user["section"]


def can_submit(task, user):
    if not user:
        return False
    return task["status"] == "claimed" and task["claimed_by"] == user["name"]


def can_approve(task, approver):
    if not approver or approver["rank_level"] < 2:
        return False
    if task["status"] != "pending_approval":
        return False
    if task["claimed_by"] == approver["name"]:
        return False

    creator_level = task["created_by_rank"]
    claimant_level = task["claimed_by_rank"] or 0
    approver_level = approver["rank_level"]

    # Special rule:
    # If SPC and below completed it, any SGT+ can approve it.
    if claimant_level == 1 and approver_level >= 2:
        return True

    # Otherwise, approver must outrank the creator.
    return approver_level > creator_level


def build_leaderboard():
    return sorted(users, key=lambda x: x["points"], reverse=True)


def build_section_totals():
    totals = {section: 0 for section in SECTIONS}
    for user in users:
        totals[user["section"]] += user["points"]
    return sorted(
        [{"section": k, "points": v} for k, v in totals.items()],
        key=lambda x: x["points"],
        reverse=True,
    )


HTML = """
<!doctype html>
<html>
<head>
    <title>Duty Tracker</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 30px;
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
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #ddd;
        }

        .login-box, .panel-form {
            margin-bottom: 20px;
            padding: 12px;
            border: 1px solid #ccc;
            width: 380px;
            background: #f9f9f9;
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

        .pending {
            color: darkred;
            font-weight: bold;
        }

        .claimed {
            color: #a56700;
            font-weight: bold;
        }

        .awaiting {
            color: #0b57d0;
            font-weight: bold;
        }

        .done {
            color: green;
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
            grid-template-columns: repeat(2, minmax(280px, 1fr));
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
    </style>
</head>
<body>
    {% if not current_user %}
        <h1>Duty Tracker Login</h1>
        <form class="login-box" method="POST" action="/login">
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
                    Logged in as <strong>{{ current_user.name }}</strong>
                    | {{ current_user.rank }}
                    | {{ current_user.section }}
                    | Points: <strong>{{ current_user.points }}</strong>
                </div>
            </div>
            <div>
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
                        <th>Rank</th>
                        <th>Section</th>
                        <th>Points</th>
                    </tr>
                    {% for user in leaderboard %}
                    <tr>
                        <td>{{ user.name }}</td>
                        <td>{{ user.rank }}</td>
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

        {% if is_admin %}
        <h2>Admin Panel</h2>
        <div class="grid-2">
            <form class="panel-form" method="POST" action="/add_user">
                <h3>Create User</h3>
                <input type="text" name="name" placeholder="Full name" required>
                <input type="text" name="username" placeholder="Username" required>
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

            <form class="panel-form" method="POST" action="/add_task">
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
        </div>
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
                    {% if can_claim_map[task.id] %}
                    <form method="POST" action="/claim_task/{{ task.id }}">
                        <button type="submit">Claim</button>
                    </form>
                    {% else %}
                    <span class="note">Not eligible</span>
                    {% endif %}
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
                    {% if task.status == "claimed" %}
                    <form method="POST" action="/submit_task/{{ task.id }}">
                        <button type="submit">Mark Done</button>
                    </form>
                    {% else %}
                    <span class="note">Waiting</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p class="empty-note">You have no claimed tasks right now.</p>
        {% endif %}

        {% if is_admin %}
        <h2>Approval Queue</h2>
        {% if pending_tasks %}
        <table>
            <tr>
                <th>Task</th>
                <th>Points</th>
                <th>Created By</th>
                <th>Claimed By</th>
                <th>Claimed By Section</th>
                <th>Approval</th>
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

        <h2>Completed History</h2>
        {% if completed_tasks %}
        <table>
            <tr>
                <th>Task</th>
                <th>Points</th>
                <th>Origin</th>
                <th>Completed By</th>
                <th>Completed By Section</th>
                <th>Status</th>
            </tr>
            {% for task in completed_tasks %}
            <tr>
                <td>{{ task.title }}</td>
                <td>{{ task.points }}</td>
                <td>{{ task.section_origin }}</td>
                <td>{{ task.claimed_by }}</td>
                <td>{{ task.claimed_by_section }}</td>
                <td><span class="done">Completed</span></td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p class="empty-note">No completed tasks yet.</p>
        {% endif %}
    {% endif %}
</body>
</html>
"""


@app.route("/", methods=["GET"])
def home():
    current_user = get_current_user()

    if not current_user:
        return render_template_string(
            HTML,
            current_user=None,
            login_error=session.pop("login_error", None),
        )

    leaderboard = build_leaderboard()
    section_totals = build_section_totals()

    available_tasks = [t for t in tasks if t["status"] == "available"]
    my_tasks = [
        t for t in tasks
        if t["claimed_by"] == current_user["name"] and t["status"] in ["claimed", "pending_approval"]
    ]
    pending_tasks = [t for t in tasks if t["status"] == "pending_approval"]
    completed_history = [t for t in tasks if t["status"] == "completed"]

    can_claim_map = {task["id"]: can_claim(task, current_user) for task in available_tasks}
    can_approve_map = {task["id"]: can_approve(task, current_user) for task in pending_tasks}

    return render_template_string(
        HTML,
        current_user=current_user,
        is_admin=is_admin(current_user),
        leaderboard=leaderboard,
        section_totals=section_totals,
        sections=SECTIONS,
        rank_names=list(RANKS.keys()),
        claim_access_options=CLAIM_ACCESS_OPTIONS,
        available_tasks=available_tasks,
        my_tasks=my_tasks,
        pending_tasks=pending_tasks,
        completed_tasks=completed_history,
        can_claim_map=can_claim_map,
        can_approve_map=can_approve_map,
        login_error=None,
    )


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"].strip()
    password = request.form["password"]

    user = get_user_by_username(username)
    if user and user["password"] == password:
        session["username"] = user["username"]
        return redirect(url_for("home"))

    session["login_error"] = "Invalid username or password."
    return redirect(url_for("home"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/add_user", methods=["POST"])
def add_user():
    current_user = get_current_user()
    if not is_admin(current_user):
        return redirect(url_for("home"))

    name = request.form["name"].strip()
    username = request.form["username"].strip()
    password = request.form["password"]
    rank = request.form["rank"]
    section = request.form["section"]

    if (
        name
        and username
        and rank in RANKS
        and section in SECTIONS
        and not any(u["username"].lower() == username.lower() for u in users)
    ):
        users.append({
            "name": name,
            "username": username,
            "password": password,
            "rank": rank,
            "rank_level": RANKS[rank],
            "section": section,
            "points": 0,
        })

    return redirect(url_for("home"))


@app.route("/add_task", methods=["POST"])
def add_task():
    current_user = get_current_user()
    if not is_admin(current_user):
        return redirect(url_for("home"))

    title = request.form["title"].strip()
    points = int(request.form["points"])
    section_origin = request.form["section_origin"]
    claim_access = request.form["claim_access"]

    if not title or section_origin not in SECTIONS or claim_access not in CLAIM_ACCESS_OPTIONS:
        return redirect(url_for("home"))

    new_id = max((task["id"] for task in tasks), default=0) + 1

    tasks.append({
        "id": new_id,
        "title": title,
        "points": points,
        "section_origin": section_origin,
        "claim_access": claim_access,
        "created_by": current_user["name"],
        "created_by_rank": current_user["rank_level"],
        "claimed_by": None,
        "claimed_by_rank": None,
        "claimed_by_section": None,
        "status": "available",
        "rejection_note": "",
        "last_action": "Created",
    })

    return redirect(url_for("home"))


@app.route("/claim_task/<int:task_id>", methods=["POST"])
def claim_task(task_id):
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for("home"))

    for task in tasks:
        if task["id"] == task_id and can_claim(task, current_user):
            task["claimed_by"] = current_user["name"]
            task["claimed_by_rank"] = current_user["rank_level"]
            task["claimed_by_section"] = current_user["section"]
            task["status"] = "claimed"
            task["rejection_note"] = ""
            task["last_action"] = "Claimed"
            break

    return redirect(url_for("home"))


@app.route("/submit_task/<int:task_id>", methods=["POST"])
def submit_task(task_id):
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for("home"))

    for task in tasks:
        if task["id"] == task_id and can_submit(task, current_user):
            task["status"] = "pending_approval"
            task["last_action"] = "Submitted for approval"
            break

    return redirect(url_for("home"))


@app.route("/approve_task/<int:task_id>", methods=["POST"])
def approve_task(task_id):
    current_user = get_current_user()
    if not is_admin(current_user):
        return redirect(url_for("home"))

    for task in tasks:
        if task["id"] == task_id and can_approve(task, current_user):
            for user in users:
                if user["name"] == task["claimed_by"]:
                    user["points"] += task["points"]
                    break

            task["status"] = "completed"
            task["rejection_note"] = ""
            task["last_action"] = f"Approved by {current_user['name']}"
            break

    return redirect(url_for("home"))


@app.route("/reject_task/<int:task_id>", methods=["POST"])
def reject_task(task_id):
    current_user = get_current_user()
    if not is_admin(current_user):
        return redirect(url_for("home"))

    rejection_action = request.form["rejection_action"]
    rejection_note = request.form.get("rejection_note", "").strip()

    for task in tasks:
        if task["id"] == task_id and can_approve(task, current_user):
            task["rejection_note"] = rejection_note

            if rejection_action == "return":
                task["status"] = "claimed"
                task["last_action"] = f"Returned to claimant by {current_user['name']}"
            elif rejection_action == "reopen":
                task["status"] = "available"
                task["claimed_by"] = None
                task["claimed_by_rank"] = None
                task["claimed_by_section"] = None
                task["last_action"] = f"Reopened by {current_user['name']}"
            break

    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
