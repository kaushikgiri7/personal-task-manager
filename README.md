# Personal Task Manager

A local student task manager built with Streamlit and SQLite. It supports
separate user accounts, task categories, priorities, due dates, status tracking,
filters, sorting, and dashboard summaries.

## Run locally

```powershell
python -m pip install -r requirements.txt
python -m streamlit run ai.py
```

The SQLite database (`task_manager.db`) is created beside `ai.py` the first
time the app runs and persists tasks across restarts. No external service or
internet connection is needed after Streamlit is installed.

The demo account is **admin / admin123**. Use **Create account** to make a
separate account; each account can only view and manage its own tasks.

## Run tests

```powershell
python -m pytest -q
```
