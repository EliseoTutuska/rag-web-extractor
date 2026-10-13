import pytest
from starlette.testclient import TestClient
from main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_system_status_api(client):
    response = client.get("/api/system/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "online"
    assert "storage_mode" in data
    assert "mongodb_uri" in data

def test_templates_api(client):
    response = client.get("/api/templates")
    assert response.status_code == 200
    templates = response.json()
    assert isinstance(templates, list)
    assert len(templates) >= 3  # 百科、电商、新闻
    template_ids = [t["id"] for t in templates]
    assert "wiki" in template_ids
    assert "ecommerce" in template_ids
    assert "news" in template_ids

def test_crawl_validation_empty_urls(client):
    response = client.post("/api/crawl", json={"urls": []})
    assert response.status_code == 400

def test_config_update_api(client):
    payload = {
        "llm_model": "gpt-4o-mini",
        "llm_url": "https://api.openai.com/v1/chat/completions"
    }
    response = client.post("/api/system/config", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

def test_storage_data_query(client):
    for tbl in ["tasks", "main_fields", "sub_fields"]:
        response = client.get(f"/api/storage/data?table={tbl}")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
