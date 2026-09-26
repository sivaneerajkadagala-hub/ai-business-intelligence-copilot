import io

import pytest
from app.models.user import UserRole
from app.services.ai import sql_validator
from tests.conftest import auth, create_user

CSV = """date,product,region,quantity,revenue
2024-01-05,Widget A,North,10,500.0
2024-01-06,Widget B,South,5,250.0
2024-01-07,Widget A,North,8,400.0
2024-02-08,Widget C,East,3,99.0
2024-02-09,Widget B,West,7,350.0
"""


@pytest.fixture()
def setup(client):
    create_user("cp@test.dev", "Password1!", UserRole.ANALYST)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "cp@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sales.csv", io.BytesIO(CSV.encode()))},
        data={"name": "CopilotSales"},
        headers=auth(token),
    )
    assert res.status_code == 201, res.json()
    return token, res.json()["data"]


def _ask(client, token, ds_id, question, conv=None):
    payload = {"question": question, "datasetId": ds_id}
    if conv:
        payload["conversationId"] = conv
    return client.post("/api/v1/copilot/chat", json=payload, headers=auth(token))


def test_chat_total_revenue(client, setup):
    token, ds = setup
    res = _ask(client, token, ds["id"], "What is the total revenue?")
    assert res.status_code == 200, res.json()
    d = res.json()["data"]
    assert d["engine"] == "rules"
    msg = d["message"]
    assert "SUM" in msg["sql"].upper()
    assert msg["resultSnapshot"]["rows"][0]["value"] == pytest.approx(1599.0)
    assert msg["content"]


def test_chat_monthly_trend(client, setup):
    token, ds = setup
    res = _ask(client, token, ds["id"], "Show me the monthly revenue trend")
    assert res.status_code == 200, res.json()
    msg = res.json()["data"]["message"]
    assert msg["chartSpec"]["type"] == "line"
    rows = msg["resultSnapshot"]["rows"]
    assert len(rows) == 2  # Jan + Feb 2024
    assert rows[0]["value"] == pytest.approx(1150.0)


def test_chat_ranking_top_region(client, setup):
    token, ds = setup
    res = _ask(client, token, ds["id"], "Top region by revenue")
    assert res.status_code == 200
    rows = res.json()["data"]["message"]["resultSnapshot"]["rows"]
    assert rows[0]["label"] == "North"
    assert rows[0]["value"] == pytest.approx(900.0)


def test_chat_count(client, setup):
    token, ds = setup
    res = _ask(client, token, ds["id"], "How many sales do we have?")
    assert res.status_code == 200
    assert res.json()["data"]["message"]["resultSnapshot"]["rows"][0]["value"] == 5


def test_chat_filter_by_region(client, setup):
    token, ds = setup
    res = _ask(client, token, ds["id"], "Total revenue in North")
    assert res.status_code == 200
    assert res.json()["data"]["message"]["resultSnapshot"]["rows"][0]["value"] == pytest.approx(900.0)


def test_chat_persists_conversation_and_history(client, setup):
    token, ds = setup
    res = _ask(client, token, ds["id"], "Total revenue")
    conv_id = res.json()["data"]["conversationId"]

    conv = client.get(
        f"/api/v1/copilot/conversations/{conv_id}", headers=auth(token)
    ).json()["data"]
    assert len(conv["messages"]) == 2  # user + assistant

    # Queries executed counter reflects real usage.
    summary = client.get("/api/v1/analytics/summary", headers=auth(token)).json()["data"]
    assert summary["queriesExecuted"] == 1


def test_chat_unmapped_question_graceful(client, setup):
    token, ds = setup
    res = _ask(client, token, ds["id"], "what is the meaning of life")
    assert res.status_code == 200
    msg = res.json()["data"]["message"]
    assert msg["sql"] is None
    assert "couldn't" in msg["content"].lower()


def test_conversation_owner_only(client, setup):
    token, ds = setup
    conv_id = _ask(client, token, ds["id"], "Total revenue").json()["data"]["conversationId"]
    create_user("other2@test.dev", "Password1!", UserRole.VIEWER)
    other = client.post(
        "/api/v1/auth/login",
        json={"email": "other2@test.dev", "password": "Password1!"},
    ).json()["data"]["accessToken"]
    res = client.get(f"/api/v1/copilot/conversations/{conv_id}", headers=auth(other))
    assert res.status_code == 404


# ── SQL validator unit tests ───────────────────────────────────

ALLOWED_TABLES = {"data.ds_abc", "ds_abc"}
ALLOWED_COLS = {"date", "region", "revenue", "quantity"}


def test_validator_allows_select():
    sql = sql_validator.validate(
        'SELECT region, SUM(revenue) AS value FROM data.ds_abc GROUP BY region',
        allowed_tables=ALLOWED_TABLES, allowed_columns=ALLOWED_COLS, dialect="postgres",
    )
    assert "LIMIT" in sql.upper()


def test_validator_rejects_dml():
    for sql in [
        "DELETE FROM data.ds_abc",
        "DROP TABLE data.ds_abc",
        "UPDATE data.ds_abc SET revenue = 0",
        "INSERT INTO data.ds_abc VALUES (1,2,3)",
        "SELECT * FROM data.ds_abc; DROP TABLE data.ds_abc",
    ]:
        with pytest.raises(sql_validator.SQLValidationError):
            sql_validator.validate(
                sql, allowed_tables=ALLOWED_TABLES,
                allowed_columns=ALLOWED_COLS, dialect="postgres",
            )


def test_validator_rejects_foreign_table():
    with pytest.raises(sql_validator.SQLValidationError):
        sql_validator.validate(
            "SELECT * FROM users",
            allowed_tables=ALLOWED_TABLES, allowed_columns=ALLOWED_COLS,
            dialect="postgres",
        )


def test_validator_rejects_unknown_column():
    with pytest.raises(sql_validator.SQLValidationError):
        sql_validator.validate(
            "SELECT secret_col FROM data.ds_abc",
            allowed_tables=ALLOWED_TABLES, allowed_columns=ALLOWED_COLS,
            dialect="postgres",
        )


def test_validator_caps_limit():
    sql = sql_validator.validate(
        "SELECT region FROM data.ds_abc LIMIT 999999",
        allowed_tables=ALLOWED_TABLES, allowed_columns=ALLOWED_COLS, dialect="postgres",
    )
    assert "5000" in sql


def test_validator_blocks_sleep():
    with pytest.raises(sql_validator.SQLValidationError):
        sql_validator.validate(
            "SELECT pg_sleep(10) FROM data.ds_abc",
            allowed_tables=ALLOWED_TABLES, allowed_columns=ALLOWED_COLS | {"pg_sleep"},
            dialect="postgres",
        )
