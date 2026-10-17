"""Server-owned deadlines, disconnect-triggered closes, and restart recovery (SPEC §6, §7, §9)."""

import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Matchup
from app.tournament import service as tournament_service
from app.tournament import timers
from tests.api.conftest import auth

WINDOW = 0.3


class PickFirst:
    def choice(self, seq):
        return seq[0]


@pytest.fixture(autouse=True)
def short_windows(monkeypatch):
    """Every voting phase opens immediately and lasts WINDOW seconds."""
    monkeypatch.setattr(get_settings(), "reveal_seconds", 0)
    monkeypatch.setattr(
        tournament_service, "_window", lambda now, seconds: (now, now + timedelta(seconds=WINDOW))
    )
    monkeypatch.setattr(tournament_service, "coin", PickFirst())


@pytest.fixture
def lobby(create_room, join_room, submit):
    def _lobby(options=("Pizza", "Tacos")):
        room = create_room(settings={"max_submissions": 10})
        guest = join_room(room["code"], "Sam")
        for text in options:
            submit(room["code"], room["token"], text)
        return room["code"], room, guest

    return _lobby


@pytest.fixture
def start(client):
    def _start(code, token):
        response = client.post(f"/rooms/{code}/start", headers=auth(token))
        assert response.status_code == 200, response.text

    return _start


@pytest.fixture
def started(lobby, start):
    def _started(options=("Pizza", "Tacos")):
        code, room, guest = lobby(options)
        start(code, room["token"])
        return code, room, guest

    return _started


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def current(snap):
    cur = snap["tournament"]["current"]
    return next(
        m for r in snap["tournament"]["rounds"] for m in r if cur and m["id"] == cur["matchup_id"]
    )


def test_matchup_closes_itself_at_the_deadline(client, started, snapshot):
    code, room, _ = started()
    m = current(snapshot(code, room["token"]))
    client.post(
        f"/rooms/{code}/votes",
        json={"matchup_id": m["id"], "contender_id": m["contender_b_id"]},
        headers=auth(room["token"]),
    )

    assert wait_for(lambda: snapshot(code, room["token"])["status"] == "finished")
    snap = snapshot(code, room["token"])
    assert snap["tournament"]["champion_id"] == m["contender_b_id"]
    assert snap["tournament"]["rounds"][0][0]["outcome"] == "votes"


def test_a_game_nobody_votes_in_still_finishes(started, snapshot):
    code, room, _ = started(("A", "B", "C", "D"))

    assert wait_for(lambda: snapshot(code, room["token"])["status"] == "finished", timeout=10)
    rounds = snapshot(code, room["token"])["tournament"]["rounds"]
    assert all(m["outcome"] == "coin_flip" for r in rounds for m in r)


def test_deadline_events_are_broadcast(client, lobby, start):
    code, room, _ = lobby()

    with client.websocket_connect(f"/rooms/{code}/ws?token={room['token']}") as ws:
        ws.receive_json()
        start(code, room["token"])
        types = []
        while "champion_crowned" not in types:
            types.append(ws.receive_json()["type"])

    assert types[types.index("revote_started") :] == [
        "revote_started",
        "matchup_decided",
        "champion_crowned",
    ]


def test_a_stale_deadline_does_nothing(client, started, snapshot, monkeypatch):
    monkeypatch.setattr(
        tournament_service, "_window", lambda now, seconds: (now, now + timedelta(seconds=60))
    )
    code, room, _ = started(("A", "B", "C", "D"))
    first = current(snapshot(code, room["token"]))
    with SessionLocal() as session:
        matchup = session.get(Matchup, first["id"])
        room_id, ends_at = matchup.room_id, matchup.ends_at

    # The phase moves on (the host closes it), then the old deadline fires late.
    client.post(f"/rooms/{code}/matchups/{first['id']}/close", headers=auth(room["token"]))
    version = snapshot(code, room["token"])["version"]

    assert timers.expire_phase(room_id, first["id"], ends_at) == []
    assert snapshot(code, room["token"])["version"] == version


def test_last_unvoted_player_disconnecting_closes_the_matchup(
    client, started, snapshot, monkeypatch
):
    # Long windows, so only the disconnect can close the matchup.
    monkeypatch.setattr(
        tournament_service, "_window", lambda now, seconds: (now, now + timedelta(seconds=60))
    )
    code, room, guest = started()
    m = current(snapshot(code, room["token"]))

    with client.websocket_connect(f"/rooms/{code}/ws?token={room['token']}") as host_ws:
        host_ws.receive_json()
        with client.websocket_connect(f"/rooms/{code}/ws?token={guest['token']}") as guest_ws:
            guest_ws.receive_json()
            client.post(
                f"/rooms/{code}/votes",
                json={"matchup_id": m["id"], "contender_id": m["contender_a_id"]},
                headers=auth(room["token"]),
            )
            assert snapshot(code, room["token"])["status"] == "in_progress"

        assert wait_for(lambda: snapshot(code, room["token"])["status"] == "finished")


def test_overdue_deadlines_are_recovered_on_startup(started, snapshot, monkeypatch):
    monkeypatch.setattr(
        tournament_service, "_window", lambda now, seconds: (now, now + timedelta(hours=1))
    )
    code, room, _ = started()
    m = current(snapshot(code, room["token"]))
    # Simulate a restart that missed the deadline: the in-memory timer is gone and it has passed.
    from app.realtime.hub import hub

    hub.reset()
    with SessionLocal() as session:
        session.execute(
            update(Matchup)
            .where(Matchup.id == m["id"])
            .values(ends_at=Matchup.starts_at - timedelta(seconds=1))
        )
        session.commit()

    with TestClient(app):
        assert wait_for(
            lambda: snapshot(code, room["token"])["tournament"]["current"]["phase"] == "revote"
        )
