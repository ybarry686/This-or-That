import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(clean_db):
    with TestClient(app) as c:
        yield c


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def create_room(client):
    def _create(**overrides):
        body = {"title": "Where should we eat?", "nickname": "Host"} | overrides
        response = client.post("/rooms", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return _create


@pytest.fixture
def join_room(client):
    def _join(code: str, nickname: str = "Guest"):
        response = client.post(f"/rooms/{code}/join", json={"nickname": nickname})
        assert response.status_code == 201, response.text
        return response.json()

    return _join


@pytest.fixture
def snapshot(client):
    def _snapshot(code: str, token: str):
        response = client.get(f"/rooms/{code}", headers=auth(token))
        assert response.status_code == 200, response.text
        return response.json()

    return _snapshot


@pytest.fixture
def submit(client):
    def _submit(code: str, token: str, text: str, expected_status: int = 201):
        response = client.post(
            f"/rooms/{code}/submissions", json={"text": text}, headers=auth(token)
        )
        assert response.status_code == expected_status, response.text
        return response.json()

    return _submit
