import pytest

import uuid
def test_apply_assistant_flow(client):
    # 1. Register a user
    email = f"apply_test_{uuid.uuid4().hex[:6]}@example.com"
    res = client.post("/api/auth/register", json={
        "email": email,
        "password": "password123"
    })
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Extract profile from resume
    resume_text = """John Doe
Software Engineer | Bangalore
Experience:
- SDE at Tech Corp (2020 - 2024). Worked on Python APIs.
Skills: Python, FastAPI, SQL
Education:
- B.Tech in CS (2019)
"""
    res = client.post("/api/profile/from-resume", data={"text": resume_text}, headers=headers)
    assert res.status_code == 200, res.text
    profile_data = res.json()["sections"]
    sections = profile_data.get("sections", []) if isinstance(profile_data, dict) else profile_data
    assert isinstance(sections, list)
    assert len(sections) > 0

    # 3. Save Master Profile
    res = client.put("/api/profile/", json=sections, headers=headers)
    assert res.status_code == 200, res.text

    # 4. Extract JD and Match
    jd_text = """We are looking for a Python Backend Engineer with 3+ years experience.
Required Skills: Python, FastAPI, Docker, CI/CD.
Location: Remote."""
    res = client.post("/api/apply/extract", json={"jd_text": jd_text}, headers=headers)
    assert res.status_code == 200, res.text
    extract_res = res.json()
    assert "skills" in extract_res
    assert "match" in extract_res

    # 5. Save Application Draft
    app_data = {
        "company": "Fake Startup",
        "job_title": "Backend Engineer",
        "job_url": "https://example.com/job/1",
        "jd_text": extract_res["extracted"]["jd_text"],
        "jd_skills": extract_res["skills"],
        "match": extract_res["match"],
        "status": "draft"
    }
    res = client.post("/api/apply/", json=app_data, headers=headers)
    assert res.status_code == 200, res.text
    app_id = res.json()["id"]

    # 6. Generate Docs
    res = client.post("/api/apply/generate", json={
        "application_id": app_id,
        "kinds": ["resume", "cover_letter", "answers"],
        "questions": ["Why do you want to work here?", "How many years of Python experience do you have?"]
    }, headers=headers)
    assert res.status_code == 200, res.text
    docs = res.json()["docs"]
    assert len(docs) == 3

    # 7. Export Document (Resume) as HTML
    res = client.get(f"/api/apply/{app_id}/export?kind=resume&fmt=html", headers=headers)
    assert res.status_code == 200, res.text
    assert "<html" in res.text.lower()
