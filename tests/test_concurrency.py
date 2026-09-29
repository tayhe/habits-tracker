import threading

from backend import database


def test_t14_database_busy_timeout_concurrency(test_db_env):
    """T-14: P1-07 - Concurrent writes should not immediately fail with 'database is locked'."""
    errors = []

    def writer_thread(task_name):
        try:
            for i in range(10):
                with database.get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT OR IGNORE INTO tasks (task_id, subject, name, reward, weekly_min, sort_weight) VALUES (?, ?, ?, ?, ?, ?)",
                        (f"{task_name}_{i}", "英语", f"任务_{i}", 0.1, 1, 0)
                    )
                    conn.commit()
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer_thread, args=("t1",)),
        threading.Thread(target=writer_thread, args=("t2",)),
        threading.Thread(target=writer_thread, args=("t3",)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
