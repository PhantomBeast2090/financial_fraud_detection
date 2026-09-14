"""
tests/test_db_viewer.py — read-only DB browser against an isolated sqlite file.
"""
import sqlite3

import pytest


@pytest.fixture()
def fake_db(tmp_path, monkeypatch):
    import importlib

    dv = importlib.import_module("backend.routers.db_viewer_router")

    path = tmp_path / "viewer.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    conn.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, amount REAL)")
    conn.execute("INSERT INTO users (username) VALUES ('admin'), ('demo')")
    conn.execute("INSERT INTO transactions (amount) VALUES (100.0)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(dv, "_DB_PATH", path)
    return path


def test_tables_lists_counts(seeded_client, user_token, fake_db):
    from tests.conftest import auth_headers

    resp = seeded_client.get("/api/db/tables", headers=auth_headers(user_token))
    assert resp.status_code == 200
    by_name = {r["table"]: r for r in resp.json()}
    assert by_name["users"]["rows"] == 2
    assert by_name["users"]["allowed"] is True


def test_table_rows_paginated(seeded_client, user_token, fake_db):
    from tests.conftest import auth_headers

    resp = seeded_client.get("/api/db/table/users?page=1&page_size=1",
                             headers=auth_headers(user_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["total_pages"] == 2
    assert body["columns"] == ["id", "username"]
    assert len(body["rows"]) == 1


def test_disallowed_table_rejected(seeded_client, user_token, fake_db):
    from tests.conftest import auth_headers

    assert seeded_client.get("/api/db/table/sqlite_master",
                             headers=auth_headers(user_token)).status_code == 403


def test_requires_auth(client, fake_db):
    assert client.get("/api/db/tables").status_code == 401
