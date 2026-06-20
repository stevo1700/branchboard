# Branchboard

A branching-conversation board with built-in contradiction flagging. Start a
thread, reply to any message (infinitely nested), and flag any two messages as
contradicting each other — anyone can then resolve the contradiction with a
verdict and a note. Self-hosted, so you and your friends just visit a URL.

Flask + SQLAlchemy. Uses Postgres in production (Railway) and SQLite locally.

## Run locally

    pip install -r requirements.txt
    python app.py
    # open http://localhost:5000  (uses a local branchboard.db SQLite file)

## Deploy to Railway

1. Push this folder to a GitHub repo.
2. railway.app -> New Project -> Deploy from GitHub repo -> pick the repo.
3. In the project, click New -> Database -> Add PostgreSQL.
4. Open your web service -> Variables. Add a variable DATABASE_URL and set its
   value by referencing the Postgres plugin's connection string
   (Railway: use the "Add Reference" button and pick Postgres -> DATABASE_URL).
5. Railway builds with Nixpacks and starts it via the Procfile (gunicorn app:app).
6. Web service -> Settings -> Networking -> Generate Domain.
7. Share that URL with your friends. Everyone sees the same conversation.

No DATABASE_URL set? The app falls back to SQLite automatically, which is great
for local testing but resets on each Railway redeploy — so set Postgres for real use.

## How it works
- Each person sets a display name (stored in their own browser).
- The board polls every few seconds, so changes from friends appear on their own.
- Edits are per-message and last-write-wins; fine for a small group.
