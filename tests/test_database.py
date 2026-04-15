import pytest
import time
import database


def test_add_and_list_github_repo(app):
    database.add_github_repo('mjolnir-armory', 'ericnelson', 'mjolnir-armory')
    repos = database.list_github_repos()
    assert len(repos) == 1
    assert repos[0]['id'] == 'mjolnir-armory'
    assert repos[0]['owner'] == 'ericnelson'
    assert repos[0]['enabled'] == 1


def test_upsert_github_repo_status(app):
    database.add_github_repo('myrepo', 'owner', 'myrepo')
    database.upsert_github_repo_status(
        repo_id='myrepo',
        last_commit_at='2026-04-14T10:00:00',
        last_commit_msg='feat: add thing',
        open_prs=3,
        ci_status='success',
        fetched_at='2026-04-14T10:05:00',
    )
    status = database.get_github_repo_status('myrepo')
    assert status['open_prs'] == 3
    assert status['ci_status'] == 'success'


def test_delete_github_repo(app):
    database.add_github_repo('todelete', 'owner', 'todelete')
    database.delete_github_repo('todelete')
    assert database.list_github_repos() == []


def test_add_and_list_recommendations(app):
    database.add_recommendation('rule', 'critical', 'Gitea offline', 'offline 2h')
    database.add_recommendation('ai', 'info', 'Deploy backlog growing', None)
    recs = database.list_recommendations(include_dismissed=False)
    assert len(recs) == 2
    assert recs[0]['severity'] == 'critical'


def test_dismiss_recommendation(app):
    database.add_recommendation('rule', 'warning', 'High CPU', None)
    recs = database.list_recommendations(include_dismissed=False)
    rec_id = recs[0]['id']
    database.dismiss_recommendation(rec_id)
    active = database.list_recommendations(include_dismissed=False)
    assert len(active) == 0
    all_recs = database.list_recommendations(include_dismissed=True)
    assert len(all_recs) == 1


def test_clear_recommendations_by_source(app):
    database.add_recommendation('rule', 'warning', 'Rule warning', None)
    database.add_recommendation('ai', 'info', 'AI insight', None)
    database.clear_recommendations(source='rule')
    recs = database.list_recommendations(include_dismissed=True)
    assert len(recs) == 1
    assert recs[0]['source'] == 'ai'


def test_prune_old_data(app):
    now = time.time()
    old_ts = now - (8 * 24 * 3600)  # 8 days ago

    # Insert old and recent telemetry rows directly via the DB connection
    with database._db_conn() as conn:
        conn.execute(
            "INSERT INTO telemetry_history (cpu_usage, ram_usage, timestamp) VALUES (?, ?, ?)",
            (50.0, 60.0, old_ts),
        )
        conn.execute(
            "INSERT INTO telemetry_history (cpu_usage, ram_usage, timestamp) VALUES (?, ?, ?)",
            (55.0, 65.0, now),
        )
        conn.commit()

    # Insert 10,005 audit_log rows
    with database._db_conn() as conn:
        for i in range(10005):
            conn.execute(
                "INSERT INTO audit_log (event_type, actor_user_id, target_user_id, ip, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ('test_event', None, None, '127.0.0.1', f'detail {i}', '2026-01-01T00:00:00'),
            )
        conn.commit()

    database.prune_old_data()

    # Old telemetry rows should be gone, recent row should remain
    with database._db_conn() as conn:
        rows = conn.execute("SELECT * FROM telemetry_history").fetchall()
    assert len(rows) == 1
    assert rows[0]['cpu_usage'] == 55.0

    # audit_log should have exactly 10,000 rows
    with database._db_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert count == 10000
