import pytest
from fastapi.testclient import TestClient
from app import app
from database.database import Base, engine, get_db
from database.models import User

# Use in-memory SQLite for tests
Base.metadata.create_all(bind=engine)

client = TestClient(app)

def test_unauthenticated_redirects():
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

def test_login_success():
    # Make sure admin is initialized
    db = next(get_db())
    from services.auth import ensure_admin_exists
    # We must provide ADMIN_PASSWORD via settings or manually for testing
    from config.settings import settings
    settings.ADMIN_PASSWORD = "testpassword123"
    ensure_admin_exists(db)
    
    response = client.post(
        "/login",
        data={"email": settings.ADMIN_EMAIL, "password": "testpassword123"},
        follow_redirects=False
    )
    assert response.status_code == 303
    assert "session_token" in response.cookies

def test_login_failure():
    response = client.post(
        "/login",
        data={"email": "wrong@example.com", "password": "wrong"},
        follow_redirects=False
    )
    assert response.status_code == 200
    assert b"Invalid email or password" in response.content

def test_cron_scan_unauthorized():
    response = client.post("/api/scan/cron")
    assert response.json()["status"] == "error"
    assert response.json()["message"] == "Unauthorized"

def test_cron_scan_authorized():
    from config.settings import settings
    response = client.post(
        "/api/scan/cron",
        headers={"Authorization": f"Bearer {settings.CRON_SECRET}"}
    )
    assert response.json()["status"] == "success"
    assert "scan_id" in response.json()
