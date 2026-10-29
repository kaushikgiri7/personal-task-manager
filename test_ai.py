from datetime import date, timedelta

import pytest

from ai import add_task, authenticate, create_user, delete_task, get_tasks, init_db, update_task


@pytest.fixture
def database(tmp_path):
    database_path = tmp_path / "tasks.db"
    init_db(database_path)
    return database_path


def test_demo_login_and_user_registration(database):
    assert authenticate("admin", "admin123", database) == 1
    assert authenticate("admin", "wrong-password", database) is None

    user_id = create_user("student", "password123", database)
    assert user_id != 1
    assert authenticate("student", "password123", database) == user_id


def test_tasks_are_isolated_by_user_and_can_be_updated_and_deleted(database):
    first_user = authenticate("admin", "admin123", database)
    second_user = create_user("student", "password123", database)
    task_id = add_task(
        first_user, "Study", "Exam", "High", date.today(), "Pending", database
    )

    assert len(get_tasks(first_user, database_path=database)) == 1
    assert get_tasks(second_user, database_path=database) == []
    assert not update_task(
        second_user, task_id, "Changed", "Exam", "High", date.today(), "Pending", database
    )
    assert not delete_task(second_user, task_id, database)
    assert update_task(
        first_user, task_id, "Review", "Exam", "High", date.today(),
        "Completed", database,
    )
    assert get_tasks(first_user, status="Completed", database_path=database)[0]["name"] == "Review"
    assert delete_task(first_user, task_id, database)
    assert get_tasks(first_user, database_path=database) == []


def test_task_validation_rejects_invalid_values(database):
    user_id = authenticate("admin", "admin123", database)
    with pytest.raises(ValueError, match="Task name"):
        add_task(user_id, " ", "Exam", "High", date.today(), "Pending", database)
    with pytest.raises(ValueError, match="priority"):
        add_task(user_id, "Study", "Exam", "Urgent", date.today(), "Pending", database)
    with pytest.raises(ValueError, match="due date"):
        add_task(user_id, "Study", "Exam", "High", "not-a-date", "Pending", database)


def test_task_filters_and_sorting(database):
    user_id = authenticate("admin", "admin123", database)
    add_task(user_id, "Later", "Project", "Low", date.today() + timedelta(days=2), "Pending", database)
    add_task(user_id, "Soon", "Exam", "High", date.today(), "In Progress", database)
    add_task(user_id, "Medium", "Exam", "Medium", date.today(), "Pending", database)

    filtered = get_tasks(
        user_id, status="Pending", category="Exam", database_path=database
    )
    assert [task["name"] for task in filtered] == ["Medium"]
    by_priority = get_tasks(user_id, sort_by="priority", database_path=database)
    assert [task["priority"] for task in by_priority] == ["High", "Medium", "Low"]
