"""Results page, rematch, and room retention (SPEC §4 lifecycle)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.config import get_settings
from app.models import Room, RoomStatus
from app.rooms.cleanup import cleanup_rooms
from tests.api.conftest import auth


@pytest.fixture(autouse=True)
def no_reveal_pause(monkeypatch):
    monkeypatch.setattr(get_settings(), "reveal_seconds", 0)


@pytest.fixture
def finished(client, create_room, join_room, submit, snapshot):
    """A finished two-option game: Pizza beats Tacos 1-0. Returns (code, host, guest, snapshot)."""

    def _finished(**room_overrides):
        room = create_room(
            description="Friday",
            settings={"max_participants": 8, "vote_seconds": 45},
            **room_overrides,
        )
        code = room["code"]
        guest = join_room(code, "Sam")
        submit(code, room["token"], "Pizza")
        submit(code, guest["token"], "Tacos")
        assert client.post(f"/rooms/{code}/start", headers=auth(room["token"])).status_code == 200
        snap = snapshot(code, room["token"])
        current = snap["tournament"]["current"]
        m = snap["tournament"]["rounds"][0][0]
        pizza = next(
            c["id"] for c in snap["tournament"]["contenders"] if c["display_text"] == "Pizza"
        )
        assert m["id"] == current["matchup_id"]
        client.post(
            f"/rooms/{code}/votes",
            json={"matchup_id": m["id"], "contender_id": pizza},
            headers=auth(room["token"]),
        )
        assert (
            client.post(
                f"/rooms/{code}/matchups/{m['id']}/close", headers=auth(room["token"])
            ).status_code
            == 200
        )
        return code, room, guest, snapshot(code, room["token"])

    return _finished


class TestResults:
    def test_anyone_with_the_code_can_read_results(self, client, finished):
        code, _, _, snap = finished()

        response = client.get(f"/rooms/{code.lower()}/results")

        assert response.status_code == 200
        results = response.json()
        assert results["code"] == code
        assert results["title"] == "Where should we eat?"
        assert results["description"] == "Friday"
        assert results["finished_at"]
        assert sorted(p["nickname"] for p in results["participants"]) == ["Host", "Sam"]
        tournament = results["tournament"]
        names = {c["id"]: c["display_text"] for c in tournament["contenders"]}
        assert names[tournament["champion_id"]] == "Pizza"
        assert tournament["current"] is None
        assert tournament["rounds"] == snap["tournament"]["rounds"]

    def test_results_hide_tokens_and_private_fields(self, client, finished):
        code, room, _, _ = finished()

        body = client.get(f"/rooms/{code}/results").text

        assert room["token"] not in body
        assert room["host_recovery_token"] not in body
        assert "token" not in body

    def test_no_results_before_the_game_finishes(self, client, create_room):
        room = create_room()

        response = client.get(f"/rooms/{room['code']}/results")
        assert response.status_code == 409
        assert "finish" in response.json()["detail"].lower()

    def test_unknown_room_has_no_results(self, client):
        assert client.get("/rooms/ZZZZZZ/results").status_code == 404

    def test_finished_snapshot_records_finish_time(self, finished):
        _, _, _, snap = finished()

        assert snap["status"] == "finished"
        assert snap["finished_at"]


class TestRematch:
    def test_host_creates_a_rematch_with_the_same_question_and_settings(
        self, client, finished, snapshot
    ):
        code, room, _, _ = finished()

        response = client.post(f"/rooms/{code}/rematch", headers=auth(room["token"]))

        assert response.status_code == 201
        rematch = response.json()
        assert rematch["code"] != code
        assert rematch["nickname"] == "Host"
        assert rematch["token"] and rematch["host_recovery_token"]
        new = snapshot(rematch["code"], rematch["token"])
        assert new["status"] == "lobby"
        assert new["title"] == "Where should we eat?"
        assert new["description"] == "Friday"
        assert new["settings"] == {"max_participants": 8, "max_submissions": 3, "vote_seconds": 45}
        assert new["me"]["is_host"] is True
        assert [p["nickname"] for p in new["participants"]] == ["Host"]

    def test_old_room_points_to_the_rematch(self, client, finished, snapshot):
        code, room, guest, _ = finished()
        rematch = client.post(f"/rooms/{code}/rematch", headers=auth(room["token"])).json()

        assert snapshot(code, guest["token"])["rematch_code"] == rematch["code"]
        assert client.get(f"/rooms/{code}/results").json()["rematch_code"] == rematch["code"]

    def test_players_join_the_rematch_with_their_nickname(self, client, finished, join_room):
        code, room, _, _ = finished()
        rematch = client.post(f"/rooms/{code}/rematch", headers=auth(room["token"])).json()

        assert join_room(rematch["code"], "Sam")["nickname"] == "Sam"

    def test_rematch_is_broadcast(self, client, finished):
        code, room, guest, _ = finished()

        with client.websocket_connect(f"/rooms/{code}/ws?token={guest['token']}") as ws:
            ws.receive_json()
            rematch = client.post(f"/rooms/{code}/rematch", headers=auth(room["token"])).json()
            event = ws.receive_json()

        assert event["type"] == "rematch_created"
        assert event["data"] == {"code": rematch["code"]}

    def test_only_the_host_can_start_a_rematch(self, client, finished):
        code, _, guest, _ = finished()

        assert (
            client.post(f"/rooms/{code}/rematch", headers=auth(guest["token"])).status_code == 403
        )

    def test_rematch_needs_a_finished_game(self, client, create_room):
        room = create_room()

        response = client.post(f"/rooms/{room['code']}/rematch", headers=auth(room["token"]))
        assert response.status_code == 409

    def test_only_one_rematch_per_room(self, client, finished):
        code, room, _, _ = finished()
        first = client.post(f"/rooms/{code}/rematch", headers=auth(room["token"])).json()

        response = client.post(f"/rooms/{code}/rematch", headers=auth(room["token"]))
        assert response.status_code == 409
        assert first["code"] in response.json()["detail"]


class TestRetention:
    def age(self, session, code, **columns):
        session.execute(update(Room).where(Room.code == code).values(**columns))
        session.commit()

    def status(self, session, code):
        session.expire_all()
        room = session.scalar(select(Room).where(Room.code == code))
        return room.status if room else None

    def test_idle_lobby_expires_after_24_hours(self, client, create_room, session):
        idle = create_room()
        active = create_room()
        now = datetime.now(UTC)
        self.age(session, idle["code"], updated_at=now - timedelta(hours=25))
        self.age(session, active["code"], updated_at=now - timedelta(hours=23))

        cleanup_rooms(session, now)

        assert self.status(session, idle["code"]) is RoomStatus.EXPIRED
        assert self.status(session, active["code"]) is RoomStatus.LOBBY

    def test_expired_room_cannot_be_joined(self, client, create_room, session):
        room = create_room()
        self.age(session, room["code"], updated_at=datetime.now(UTC) - timedelta(days=2))
        cleanup_rooms(session, datetime.now(UTC))

        response = client.post(f"/rooms/{room['code']}/join", json={"nickname": "Sam"})
        assert response.status_code == 409

    def test_finished_games_are_deleted_after_30_days(self, finished, session, client):
        old_code, _, _, _ = finished()
        recent_code, _, _, _ = finished()
        now = datetime.now(UTC)
        self.age(session, old_code, finished_at=now - timedelta(days=31))
        self.age(session, recent_code, finished_at=now - timedelta(days=29))

        cleanup_rooms(session, now)

        assert self.status(session, old_code) is None
        assert self.status(session, recent_code) is RoomStatus.FINISHED
        assert client.get(f"/rooms/{old_code}/results").status_code == 404

    def test_expired_lobbies_are_deleted_after_30_days(self, create_room, session):
        room = create_room()
        self.age(
            session,
            room["code"],
            status=RoomStatus.EXPIRED,
            updated_at=datetime.now(UTC) - timedelta(days=31),
        )

        cleanup_rooms(session, datetime.now(UTC))

        assert self.status(session, room["code"]) is None

    def test_running_games_are_never_touched(self, client, create_room, join_room, submit, session):
        room = create_room()
        submit(room["code"], room["token"], "A")
        submit(room["code"], room["token"], "B")
        client.post(f"/rooms/{room['code']}/start", headers=auth(room["token"]))
        self.age(session, room["code"], updated_at=datetime.now(UTC) - timedelta(days=60))

        cleanup_rooms(session, datetime.now(UTC))

        assert self.status(session, room["code"]) is RoomStatus.IN_PROGRESS
