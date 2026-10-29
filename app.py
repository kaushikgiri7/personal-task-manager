from contextlib import closing
from datetime import date, timedelta
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
from typing import Any

import streamlit as st


DATABASE_PATH = Path(__file__).with_name("task_manager.db")
PRIORITIES = ("High", "Medium", "Low")
STATUSES = ("Pending", "In Progress", "Completed")
CATEGORIES = ("Assignment", "Exam", "Project", "Personal", "Other")
PASSWORD_ITERATIONS = 310_000
PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def connect_db(database_path: str | Path = DATABASE_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )


def init_db(database_path: str | Path = DATABASE_PATH) -> None:
    with closing(connect_db(database_path)) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        salt = os.urandom(16)
        connection.execute(
            """
            INSERT OR IGNORE INTO users (username, password_salt, password_hash)
            VALUES (?, ?, ?)
            """,
            ("admin", salt, _password_hash("admin123", salt)),
        )


def create_user(
    username: str, password: str, database_path: str | Path = DATABASE_PATH
) -> int:
    username = username.strip()
    if not username or len(username) > 50:
        raise ValueError("Username must be between 1 and 50 characters.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    salt = os.urandom(16)
    with closing(connect_db(database_path)) as connection, connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (username, password_salt, password_hash)
                VALUES (?, ?, ?)
                """,
                (username, salt, _password_hash(password, salt)),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("That username is already in use.") from error
        return int(cursor.lastrowid)


def authenticate(
    username: str, password: str, database_path: str | Path = DATABASE_PATH
) -> int | None:
    with closing(connect_db(database_path)) as connection:
        user = connection.execute(
            "SELECT id, password_salt, password_hash FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    if user is None:
        return None
    if not hmac.compare_digest(
        _password_hash(password, user["password_salt"]), user["password_hash"]
    ):
        return None
    return int(user["id"])


def _validate_task(
    name: str, category: str, priority: str, due_date: str | date, status: str
) -> tuple[str, str, str, str, str]:
    name = name.strip()
    if not name or len(name) > 160:
        raise ValueError("Task name must be between 1 and 160 characters.")
    if category not in CATEGORIES:
        raise ValueError("Choose a valid category.")
    if priority not in PRIORITIES:
        raise ValueError("Choose a valid priority.")
    if status not in STATUSES:
        raise ValueError("Choose a valid status.")
    try:
        parsed_date = date.fromisoformat(due_date) if isinstance(due_date, str) else due_date
    except ValueError as error:
        raise ValueError("Enter a valid due date.") from error
    if not isinstance(parsed_date, date):
        raise ValueError("Enter a valid due date.")
    return name, category, priority, parsed_date.isoformat(), status


def add_task(
    user_id: int,
    name: str,
    category: str,
    priority: str,
    due_date: str | date,
    status: str,
    database_path: str | Path = DATABASE_PATH,
) -> int:
    values = _validate_task(name, category, priority, due_date, status)
    with closing(connect_db(database_path)) as connection, connection:
        cursor = connection.execute(
            """
            INSERT INTO tasks (user_id, name, category, priority, due_date, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, *values),
        )
        return int(cursor.lastrowid)


def update_task(
    user_id: int,
    task_id: int,
    name: str,
    category: str,
    priority: str,
    due_date: str | date,
    status: str,
    database_path: str | Path = DATABASE_PATH,
) -> bool:
    values = _validate_task(name, category, priority, due_date, status)
    with closing(connect_db(database_path)) as connection, connection:
        cursor = connection.execute(
            """
            UPDATE tasks
            SET name = ?, category = ?, priority = ?, due_date = ?, status = ?
            WHERE id = ? AND user_id = ?
            """,
            (*values, task_id, user_id),
        )
        return cursor.rowcount == 1


def delete_task(
    user_id: int, task_id: int, database_path: str | Path = DATABASE_PATH
) -> bool:
    with closing(connect_db(database_path)) as connection, connection:
        cursor = connection.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        return cursor.rowcount == 1


def get_tasks(
    user_id: int,
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    sort_by: str = "due_date",
    database_path: str | Path = DATABASE_PATH,
) -> list[dict[str, Any]]:
    sort_columns = {
        "due_date": "due_date",
        "priority": "priority",
        "category": "category",
        "status": "status",
        "name": "name COLLATE NOCASE",
    }
    if sort_by not in sort_columns:
        raise ValueError("Choose a valid sort order.")

    conditions = ["user_id = ?"]
    parameters: list[Any] = [user_id]
    for column, value, allowed in (
        ("status", status, STATUSES),
        ("priority", priority, PRIORITIES),
        ("category", category, CATEGORIES),
    ):
        if value is not None:
            if value not in allowed:
                raise ValueError(f"Choose a valid {column}.")
            conditions.append(f"{column} = ?")
            parameters.append(value)
    with closing(connect_db(database_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT id, name, category, priority, due_date, status, created_at
            FROM tasks
            WHERE {" AND ".join(conditions)}
            ORDER BY {sort_columns[sort_by]}, name COLLATE NOCASE
            """,
            parameters,
        ).fetchall()
    tasks = [dict(row) for row in rows]
    if sort_by == "priority":
        tasks.sort(key=lambda task: (PRIORITY_ORDER[task["priority"]], task["name"].casefold()))
    return tasks


def _show_login() -> None:
    st.title("Personal Task Manager")
    login_tab, register_tab = st.tabs(["Log in", "Create account"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            user_id = authenticate(username, password)
            if user_id is None:
                st.error("Incorrect username or password.")
            else:
                st.session_state["user_id"] = user_id
                st.session_state["username"] = username.strip()
                st.rerun()
        st.caption("Demo login: admin / admin123")

    with register_tab:
        with st.form("register_form"):
            new_username = st.text_input("Choose a username")
            new_password = st.text_input("Choose a password", type="password")
            confirm_password = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account")
        if submitted:
            if new_password != confirm_password:
                st.error("The passwords do not match.")
            else:
                try:
                    user_id = create_user(new_username, new_password)
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.session_state["user_id"] = user_id
                    st.session_state["username"] = new_username.strip()
                    st.rerun()


def _dashboard(user_id: int) -> None:
    tasks = get_tasks(user_id)
    today = date.today()
    pending_count = sum(task["status"] == "Pending" for task in tasks)
    in_progress_count = sum(task["status"] == "In Progress" for task in tasks)
    completed_count = sum(task["status"] == "Completed" for task in tasks)
    overdue_tasks = [
        task for task in tasks
        if task["status"] != "Completed" and date.fromisoformat(task["due_date"]) < today
    ]
    upcoming_tasks = [
        task for task in tasks
        if task["status"] != "Completed"
        and today <= date.fromisoformat(task["due_date"]) <= today + timedelta(days=7)
    ]

    st.title("Dashboard")
    metric_columns = st.columns(5)
    for column, label, value in zip(
        metric_columns,
        ("Total tasks", "Pending", "In progress", "Completed", "Overdue"),
        (len(tasks), pending_count, in_progress_count, completed_count, len(overdue_tasks)),
    ):
        column.metric(label, value)

    st.subheader("Tasks by status")
    st.bar_chart(
        {"Status": list(STATUSES), "Tasks": [pending_count, in_progress_count, completed_count]},
        x="Status",
        y="Tasks",
    )
    st.subheader("Upcoming deadlines (next 7 days)")
    if upcoming_tasks:
        st.dataframe(upcoming_tasks, hide_index=True, use_container_width=True)
    else:
        st.info("No upcoming deadlines in the next 7 days.")
    if overdue_tasks:
        st.subheader("Overdue tasks")
        st.dataframe(overdue_tasks, hide_index=True, use_container_width=True)


def _add_task_page(user_id: int) -> None:
    st.title("Add Task")
    with st.form("add_task_form"):
        name = st.text_input("Task name")
        category = st.selectbox("Category", CATEGORIES)
        priority = st.select_slider("Priority", options=PRIORITIES, value="Medium")
        due_date = st.date_input("Due date", value=date.today())
        status = st.selectbox("Status", STATUSES)
        submitted = st.form_submit_button("Add task", type="primary")

    if submitted:
        try:
            add_task(user_id, name, category, priority, due_date, status)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Task added.")


def _view_tasks_page(user_id: int) -> None:
    st.title("View Tasks")
    filter_columns = st.columns(4)
    with filter_columns[0]:
        status_filter = st.selectbox("Status", ("All", *STATUSES))
    with filter_columns[1]:
        priority_filter = st.selectbox("Priority", ("All", *PRIORITIES))
    with filter_columns[2]:
        category_filter = st.selectbox("Category", ("All", *CATEGORIES))
    with filter_columns[3]:
        sort_by = st.selectbox(
            "Sort by", ("due_date", "priority", "category", "status", "name"),
            format_func=lambda value: value.replace("_", " ").title(),
        )

    tasks = get_tasks(
        user_id,
        status=None if status_filter == "All" else status_filter,
        priority=None if priority_filter == "All" else priority_filter,
        category=None if category_filter == "All" else category_filter,
        sort_by=sort_by,
    )
    if not tasks:
        st.info("No tasks match these filters.")
        return

    today = date.today()
    display_tasks = []
    for task in tasks:
        display_task = {key: value for key, value in task.items() if key != "id"}
        if task["status"] != "Completed" and date.fromisoformat(task["due_date"]) < today:
            display_task["status"] = f"Overdue - {task['status']}"
        display_tasks.append(display_task)
    st.dataframe(display_tasks, hide_index=True, use_container_width=True)

    task_options = {f"{task['name']} (#{task['id']})": task for task in tasks}
    selected_label = st.selectbox("Choose a task to manage", tuple(task_options))
    selected = task_options[selected_label]
    edit_tab, complete_tab, delete_tab = st.tabs(["Edit task", "Mark complete", "Delete task"])

    with edit_tab:
        with st.form(f"edit_task_{selected['id']}"):
            name = st.text_input("Task name", value=selected["name"])
            category = st.selectbox(
                "Category", CATEGORIES, index=CATEGORIES.index(selected["category"]),
                key=f"edit_category_{selected['id']}",
            )
            priority = st.selectbox(
                "Priority", PRIORITIES, index=PRIORITIES.index(selected["priority"]),
                key=f"edit_priority_{selected['id']}",
            )
            due_date = st.date_input(
                "Due date", value=date.fromisoformat(selected["due_date"]),
                key=f"edit_due_date_{selected['id']}",
            )
            status = st.selectbox(
                "Status", STATUSES, index=STATUSES.index(selected["status"]),
                key=f"edit_status_{selected['id']}",
            )
            submitted = st.form_submit_button("Save changes")
        if submitted:
            try:
                update_task(
                    user_id, selected["id"], name, category, priority, due_date, status
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("Task updated.")
                st.rerun()

    with complete_tab:
        if selected["status"] == "Completed":
            st.info("This task is already complete.")
        elif st.button("Mark as complete", key=f"complete_{selected['id']}"):
            update_task(
                user_id,
                selected["id"],
                selected["name"],
                selected["category"],
                selected["priority"],
                selected["due_date"],
                "Completed",
            )
            st.success("Task marked complete.")
            st.rerun()

    with delete_tab:
        if st.button("Delete this task", key=f"delete_{selected['id']}", type="primary"):
            delete_task(user_id, selected["id"])
            st.success("Task deleted.")
            st.rerun()


def run_app() -> None:
    st.set_page_config(page_title="Personal Task Manager", page_icon="✅", layout="wide")
    init_db()
    if "user_id" not in st.session_state:
        _show_login()
        return

    with st.sidebar:
        st.write(f"Signed in as **{st.session_state['username']}**")
        section = st.radio("Navigate", ("Dashboard", "Add Task", "View Tasks"))
        if st.button("Log out"):
            del st.session_state["user_id"]
            del st.session_state["username"]
            st.rerun()

    user_id = int(st.session_state["user_id"])
    if section == "Dashboard":
        _dashboard(user_id)
    elif section == "Add Task":
        _add_task_page(user_id)
    else:
        _view_tasks_page(user_id)


if __name__ == "__main__":
    run_app()