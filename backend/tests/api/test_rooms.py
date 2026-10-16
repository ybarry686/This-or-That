"""Room creation, joining, identity, snapshots and settings (SPEC §3, §4)."""

import re

import pytest

from tests.api.conftest import auth

CODE_PATTERN = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{6}$")


class TestCreateRoom:
    def test_returns_code_tokens_and_host_identity(self, create_room, snapshot):
        created = create_room()

        assert CODE_PATTERN.match(created["code"])
        assert created["token"] and created["host_recovery_token"]
        assert created["token"] != created["host_recovery_token"]

        snap = snapshot(created["code"], created["token"])
        assert snap["me"]["id"] == created["participant_id"]
        assert snap["me"]["is_host"] is True
        assert snap["host_participant_id"] == created["participant_id"]

    def test_uses_default_settings(self, create_room, snapshot):
        created = create_room()
        snap = snapshot(created["code"], created["token"])

        assert snap["settings"] == {
            "max_participants": 20,
            "max_submissions": 3,
            "vote_seconds": 30,
        }
        assert snap["status"] == "lobby"
        assert snap["title"] == "Where should we eat?"
        assert snap["description"] == ""

    def test_accepts_custom_settings(self, create_room, snapshot):
        created = create_room(
            description="Friday night",
            settings={"max_participants": 5, "max_submissions": 1, "vote_seconds": 60},
        )
        snap = snapshot(created["code"], created["token"])

        assert snap["description"] == "Friday night"
        assert snap["settings"] == {"max_participants": 5, "max_submissions": 1, "vote_seconds": 60}

    @pytest.mark.parametrize(
        "body",
        [
            {"title": "", "nickname": "Host"},
            {"title": "   ", "nickname": "Host"},
            {"title": "x" * 121, "nickname": "Host"},
            {"title": "Ok", "nickname": ""},
            {"title": "Ok", "nickname": "x" * 21},
            {"title": "Ok", "nickname": "Host", "description": "x" * 501},
            {"title": "Ok", "nickname": "Host", "settings": {"max_participants": 1}},
            {"title": "Ok", "nickname": "Host", "settings": {"max_participants": 51}},
            {"title": "Ok", "nickname": "Host", "settings": {"max_submissions": 0}},
            {"title": "Ok", "nickname": "Host", "settings": {"max_submissions": 11}},
            {"title": "Ok", "nickname": "Host", "settings": {"vote_seconds": 9}},
            {"title": "Ok", "nickname": "Host", "settings": {"vote_seconds": 121}},
        ],
    )
    def test_rejects_invalid_input(self, client, body):
        assert client.post("/rooms", json=body).status_code == 422

    def test_trims_title_and_nickname(self, create_room, snapshot):
        created = create_room(title="  Movies  ", nickname="  Ana  ")
        snap = snapshot(created["code"], created["token"])

        assert snap["title"] == "Movies"
        assert snap["me"]["nickname"] == "Ana"

    def test_codes_are_unique(self, create_room):
        codes = {create_room()["code"] for _ in range(20)}

        assert len(codes) == 20


class TestJoin:
    def test_join_returns_a_new_participant(self, create_room, join_room, snapshot):
        room = create_room()
        joined = join_room(room["code"], "Sam")

        snap = snapshot(room["code"], joined["token"])
        assert snap["me"]["id"] == joined["participant_id"]
        assert snap["me"]["nickname"] == "Sam"
        assert snap["me"]["is_host"] is False
        assert [p["nickname"] for p in snap["participants"]] == ["Host", "Sam"]

    def test_code_is_case_insensitive(self, create_room, join_room):
        room = create_room()

        assert join_room(room["code"].lower(), "Sam")["code"] == room["code"]

    def test_unknown_room_is_404(self, client):
        assert client.post("/rooms/ZZZZZZ/join", json={"nickname": "Sam"}).status_code == 404

    def test_nickname_clash_is_auto_suffixed(self, create_room, join_room):
        room = create_room(nickname="Sam")

        assert join_room(room["code"], "Sam")["nickname"] == "Sam 2"
        assert join_room(room["code"], "sam")["nickname"] == "sam 3"

    def test_suffixed_nickname_stays_within_20_chars(self, create_room, join_room):
        long_name = "A" * 20
        room = create_room(nickname=long_name)

        nickname = join_room(room["code"], long_name)["nickname"]
        assert len(nickname) <= 20
        assert nickname.endswith(" 2")

    def test_participants_get_different_avatars(self, create_room, join_room, snapshot):
        room = create_room()
        for name in ["A", "B", "C"]:
            join_room(room["code"], name)

        avatars = [p["avatar"] for p in snapshot(room["code"], room["token"])["participants"]]
        assert len(set(avatars)) == 4

    def test_full_room_rejects_join(self, client, create_room, join_room):
        room = create_room(settings={"max_participants": 2})
        join_room(room["code"], "Sam")

        response = client.post(f"/rooms/{room['code']}/join", json={"nickname": "Late"})
        assert response.status_code == 409
        assert "full" in response.json()["detail"].lower()


class TestIdentity:
    def test_snapshot_requires_a_token(self, client, create_room):
        room = create_room()

        assert client.get(f"/rooms/{room['code']}").status_code == 401
        assert client.get(f"/rooms/{room['code']}", headers=auth("bogus")).status_code == 401

    def test_token_from_another_room_is_rejected(self, client, create_room):
        room_a = create_room()
        room_b = create_room()

        response = client.get(f"/rooms/{room_a['code']}", headers=auth(room_b["token"]))
        assert response.status_code == 401

    def test_reconnecting_with_token_keeps_identity(self, create_room, join_room, snapshot):
        room = create_room()
        joined = join_room(room["code"], "Sam")

        first = snapshot(room["code"], joined["token"])["me"]
        second = snapshot(room["code"], joined["token"])["me"]
        assert first == second


class TestSettings:
    def test_host_can_update_settings_and_title(self, client, create_room, snapshot):
        room = create_room()

        response = client.patch(
            f"/rooms/{room['code']}",
            json={"title": "Movies?", "max_submissions": 5, "vote_seconds": 45},
            headers=auth(room["token"]),
        )

        assert response.status_code == 200
        snap = snapshot(room["code"], room["token"])
        assert snap["title"] == "Movies?"
        assert snap["settings"]["max_submissions"] == 5
        assert snap["settings"]["vote_seconds"] == 45

    def test_non_host_cannot_update_settings(self, client, create_room, join_room):
        room = create_room()
        guest = join_room(room["code"], "Sam")

        response = client.patch(
            f"/rooms/{room['code']}", json={"vote_seconds": 45}, headers=auth(guest["token"])
        )
        assert response.status_code == 403

    def test_settings_are_validated(self, client, create_room):
        room = create_room()

        response = client.patch(
            f"/rooms/{room['code']}", json={"vote_seconds": 500}, headers=auth(room["token"])
        )
        assert response.status_code == 422

    def test_cannot_lower_participant_limit_below_current_count(
        self, client, create_room, join_room
    ):
        room = create_room()
        join_room(room["code"], "A")
        join_room(room["code"], "B")

        response = client.patch(
            f"/rooms/{room['code']}", json={"max_participants": 2}, headers=auth(room["token"])
        )
        assert response.status_code == 409


class TestVersion:
    def test_every_change_bumps_the_room_version(self, client, create_room, join_room, snapshot):
        room = create_room()
        v0 = snapshot(room["code"], room["token"])["version"]

        join_room(room["code"], "Sam")
        v1 = snapshot(room["code"], room["token"])["version"]
        client.patch(f"/rooms/{room['code']}", json={"title": "New"}, headers=auth(room["token"]))
        v2 = snapshot(room["code"], room["token"])["version"]

        assert v0 < v1 < v2

    def test_reads_do_not_bump_the_version(self, create_room, snapshot):
        room = create_room()
        first = snapshot(room["code"], room["token"])["version"]

        assert snapshot(room["code"], room["token"])["version"] == first
