from datetime import timedelta

from backend import clock, database, repo


def test_repo_active_tasks_and_completion_counts(parent_client):
    """Verify repo queries work directly and correctly."""
    with database.get_db() as conn:
        tasks = repo.get_active_tasks(conn)
        assert len(tasks) > 0

        mon = clock.today() - timedelta(days=clock.today().weekday())
        week_end = mon + timedelta(days=7)
        task_ids = [t["task_id"] for t in tasks]

        # Initial counts should be empty or zero
        counts = repo.get_completion_counts(conn, mon.isoformat(), week_end.isoformat(), task_ids)
        assert isinstance(counts, dict)


def test_records_week_query_efficiency(parent_client):
    """Verify /records/week executes in a single connection with only 3 queries (no N+1)."""
    mon = clock.today() - timedelta(days=clock.today().weekday())

    queries = []
    orig_get_connection = database.get_connection

    def traced_get_connection():
        conn = orig_get_connection()
        conn.set_trace_callback(lambda sql: queries.append(sql.strip()))
        return conn

    # Count connections and queries during the request
    connection_count = 0

    def counting_get_connection():
        nonlocal connection_count
        connection_count += 1
        return traced_get_connection()

    database.get_connection = counting_get_connection
    try:
        resp = parent_client.get(f"/api/v1/records/week?date={mon.isoformat()}")
        assert resp.status_code == 200

        # Filter out PRAGMA / transaction overhead
        substantive_queries = [
            q for q in queries
            if not q.startswith("PRAGMA")
            and not q.startswith("COMMIT")
            and not q.startswith("BEGIN")
            and "sessions" not in q  # auth session validation
        ]

        # Exactly 3 queries for /records/week: active tasks + daily records map + completion counts
        # (Plus 1 auth session query)
        assert connection_count <= 2  # 1 for auth, 1 for /records/week handler
        assert len(substantive_queries) == 3
    finally:
        database.get_connection = orig_get_connection
