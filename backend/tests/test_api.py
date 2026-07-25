"""Integration tests via FastAPI TestClient (sqlite, no external services)."""
import uuid


def _email():
    return f"t{uuid.uuid4().hex[:10]}@gmail.com"


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_register_login_me(client):
    em = _email()
    r = client.post("/api/auth/register", json={"email": em, "password": "testpass123"})
    assert r.status_code == 201
    tok = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["email"] == em


def test_roadmap_resolve_grounded(client):
    r = client.post("/api/roadmap/resolve", json={"goal_text": "data analyst"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "grounded" and body["role_id"] == "data_analyst"


def test_roadmap_build_grounded(client):
    r = client.post("/api/roadmap/", json={"target_role_id": "reporting_analyst", "skills": ["excel"]})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "Reporting Analyst" and body["phases"]


def test_intake_analyze_produces_directions(client):
    r = client.post("/api/intake/analyze",
                    json={"answers": {"interests": ["design_arts"], "field": "Design / Creative", "level": "student"}})
    assert r.status_code == 200
    body = r.json()
    assert body["field"] == "Design / Creative" and body["directions"]


def test_learning_complete_updates_journey(client):
    tok = client.post("/api/auth/register",
                      json={"email": _email(), "password": "testpass123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    iid = client.post("/api/learning/", headers=h,
                      json={"title": "Power BI", "skill_ids": ["power_bi"]}).json()["id"]
    assert client.patch(f"/api/learning/{iid}", headers=h, json={"status": "completed"}).status_code == 200
    j = client.get("/api/learning/journey", headers=h).json()
    assert j["completed_total"] == 1
    assert any(a["skill_id"] == "power_bi" for a in j["acquired"])
    assert j["streak_weeks"] >= 1


def test_digest_requires_token(client):
    # DIGEST_TOKEN is unset in tests → endpoint is disabled (503), never open.
    assert client.post("/api/internal/digest/run").status_code in (403, 503)
