from flask import Flask, request, redirect, url_for, render_template_string

app = Flask(__name__)

users = [
    {"name": "Christopher", "points": 0},
]

tasks = [
    {
        "id": 1,
        "title": "Mop hallway",
        "points": 10,
        "assigned_to": "Christopher",
        "completed": False,
    }
]

completed_tasks = []

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

        h1, h2 {
            margin-bottom: 10px;
        }

        h2 {
            margin-top: 30px;
        }

        form {
            margin-bottom: 20px;
            padding: 12px;
            border: 1px solid #ccc;
            width: 350px;
            background: #f9f9f9;
        }

        input, select, button {
            margin: 5px 0;
            padding: 8px;
            width: 100%;
            box-sizing: border-box;
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
            vertical-align: middle;
        }

        th {
            background: #f2f2f2;
        }

        .pending {
            color: darkred;
            font-weight: bold;
        }

        .done {
            color: green;
            font-weight: bold;
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
            min-width: 100px;
        }
    </style>
</head>
<body>
    <h1>Duty Tracker</h1>

    <h2>Leaderboard</h2>
    <table>
        <tr>
            <th>Name</th>
            <th>Points</th>
        </tr>
        {% for user in leaderboard %}
        <tr>
            <td>{{ user.name }}</td>
            <td>{{ user.points }}</td>
        </tr>
        {% endfor %}
    </table>

    <h2>Add User</h2>
    <form method="POST" action="/add_user">
        <input type="text" name="name" placeholder="User name" required>
        <button type="submit">Add User</button>
    </form>

    <h2>Add Task</h2>
    <form method="POST" action="/add_task">
        <input type="text" name="title" placeholder="Task title" required>
        <input type="number" name="points" placeholder="Points" min="1" required>
        <select name="assigned_to" required>
            {% for user in users %}
                <option value="{{ user.name }}">{{ user.name }}</option>
            {% endfor %}
        </select>
        <button type="submit">Add Task</button>
    </form>

    <h2>Active Tasks</h2>
    {% if tasks %}
    <table>
        <tr>
            <th>Task</th>
            <th>Points</th>
            <th>Assigned To</th>
            <th>Status</th>
            <th>Action</th>
        </tr>
        {% for task in tasks %}
        <tr>
            <td>{{ task.title }}</td>
            <td>{{ task.points }}</td>
            <td>{{ task.assigned_to }}</td>
            <td><span class="pending">Pending</span></td>
            <td>
                <form method="POST" action="/complete_task/{{ task.id }}">
                    <button type="submit">Complete</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
    {% else %}
    <p class="empty-note">No active tasks right now.</p>
    {% endif %}

    <h2>Completed Tasks</h2>
    {% if completed_tasks %}
    <table>
        <tr>
            <th>Task</th>
            <th>Points</th>
            <th>Assigned To</th>
            <th>Status</th>
        </tr>
        {% for task in completed_tasks %}
        <tr>
            <td>{{ task.title }}</td>
            <td>{{ task.points }}</td>
            <td>{{ task.assigned_to }}</td>
            <td><span class="done">Completed</span></td>
        </tr>
        {% endfor %}
    </table>
    {% else %}
    <p class="empty-note">No completed tasks yet.</p>
    {% endif %}
</body>
</html>
"""


@app.route("/")
def home():
    leaderboard = sorted(users, key=lambda x: x["points"], reverse=True)
    return render_template_string(
        HTML,
        users=users,
        tasks=tasks,
        completed_tasks=completed_tasks,
        leaderboard=leaderboard,
    )


@app.route("/add_user", methods=["POST"])
def add_user():
    name = request.form["name"].strip()

    if name and not any(user["name"].lower() == name.lower() for user in users):
        users.append({
            "name": name,
            "points": 0,
        })

    return redirect(url_for("home"))


@app.route("/add_task", methods=["POST"])
def add_task():
    title = request.form["title"].strip()
    points = int(request.form["points"])
    assigned_to = request.form["assigned_to"]

    new_id = max((task["id"] for task in tasks), default=0) + 1

    tasks.append({
        "id": new_id,
        "title": title,
        "points": points,
        "assigned_to": assigned_to,
        "completed": False,
    })

    return redirect(url_for("home"))


@app.route("/complete_task/<int:task_id>", methods=["POST"])
def complete_task(task_id):
    for i, task in enumerate(tasks):
        if task["id"] == task_id:
            for user in users:
                if user["name"] == task["assigned_to"]:
                    user["points"] += task["points"]
                    break

            completed_task = task.copy()
            completed_task["completed"] = True
            completed_tasks.append(completed_task)

            tasks.pop(i)
            break

    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
