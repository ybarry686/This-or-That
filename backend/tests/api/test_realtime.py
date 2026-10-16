"""WebSocket events, presence, and lobby host hand-off (SPEC §3, §9)."""

import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.realtime.hub import hub
from tests.api.conftest import auth


@pytest.fixture(autouse=True)
def fast_host_grace(monkeypatch):
    monkeypatch.setattr(hub, "host_grace_seconds", 0.2)


@pytest.fixture
def lobby(create_room, join_room):
    room = create_room()
    guest = join_room(room["code"], "Sam")
    return room["code"], room, guest


def connect(client, code, token):
    return client.websocket_connect(f"/rooms/{code}/ws?token={token}")


def wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class TestConnect:
    def test_invalid_token_is_rejected(self, client, lobby):
        code, _, _ = lobby

        with pytest.raises(WebSocketDisconnect) as error, connect(client, code, "bogus") as ws:
            ws.receive_json()
        assert error.value.code == 4401

    def test_unknown_room_is_rejected(self, client):
        with pytest.raises(WebSocketDisconnect) as error, connect(client, "ZZZZZZ", "x") as ws:
            ws.receive_json()
        assert error.value.code == 4404

    def test_welcome_message_carries_current_version(self, client, lobby, snapshot):
        code, room, _ = lobby

        with connect(client, code, room["token"]) as ws:
            welcome = ws.receive_json()
            assert welcome["type"] == "welcome"
            assert welcome["version"] == snapshot(code, room["token"])["version"]

    def test_snapshot_reports_presence(self, client, lobby, snapshot):
        code, room, guest = lobby

        def connected():
            return {
                p["nickname"]: p["connected"] for p in snapshot(code, room["token"])["participants"]
            }

        assert connected() == {"Host": False, "Sam": False}
        with connect(client, code, guest["token"]) as ws:
            ws.receive_json()
            assert connected() == {"Host": False, "Sam": True}
        assert wait_until(lambda: connected() == {"Host": False, "Sam": False})


class TestEvents:
    def test_others_are_told_when_someone_connects_and_disconnects(self, client, lobby):
        code, room, guest = lobby

        with connect(client, code, room["token"]) as host_ws:
            welcome = host_ws.receive_json()
            with connect(client, code, guest["token"]) as guest_ws:
                guest_ws.receive_json()
                joined = host_ws.receive_json()
                assert joined["type"] == "participant_connected"
                assert joined["data"] == {"participant_id": guest["participant_id"]}
                assert joined["version"] > welcome["version"]

            left = host_ws.receive_json()
            assert left["type"] == "participant_disconnected"
            assert left["data"] == {"participant_id": guest["participant_id"]}
            assert left["version"] > joined["version"]

    def test_second_socket_for_same_participant_is_not_a_new_connection(self, client, lobby):
        code, room, guest = lobby

        with connect(client, code, room["token"]) as host_ws:
            host_ws.receive_json()
            with connect(client, code, guest["token"]) as first:
                first.receive_json()
                assert host_ws.receive_json()["type"] == "participant_connected"
                with connect(client, code, guest["token"]) as second:
                    second.receive_json()
                # Closing one of two tabs keeps the participant connected.
            assert host_ws.receive_json()["type"] == "participant_disconnected"

    def test_rest_changes_are_broadcast_with_their_version(
        self, client, lobby, join_room, submit, snapshot
    ):
        code, room, guest = lobby

        with connect(client, code, room["token"]) as ws:
            ws.receive_json()

            join_room(code, "Ana")
            event = ws.receive_json()
            assert event["type"] == "participant_joined"
            assert event["version"] == snapshot(code, room["token"])["version"]

            submit(code, guest["token"], "Secret pizza")
            event = ws.receive_json()
            assert event["type"] == "submissions_changed"
            assert event["data"] == {"option_count": 1}
            assert "Secret pizza" not in str(event)

            client.patch(f"/rooms/{code}", json={"vote_seconds": 45}, headers=auth(room["token"]))
            assert ws.receive_json()["type"] == "settings_changed"

            client.post(
                f"/rooms/{code}/host/transfer",
                json={"participant_id": guest["participant_id"]},
                headers=auth(room["token"]),
            )
            event = ws.receive_json()
            assert event["type"] == "host_changed"
            assert event["data"] == {"host_participant_id": guest["participant_id"]}

    def test_curation_and_deletion_are_broadcast(self, client, lobby, submit):
        code, room, guest = lobby
        created = submit(code, guest["token"], "Pizza")
        submit(code, guest["token"], "Pizza Hut")

        with connect(client, code, room["token"]) as ws:
            ws.receive_json()
            client.post(
                f"/rooms/{code}/contenders/merge",
                json={"source_key": "pizza hut", "target_key": "pizza"},
                headers=auth(room["token"]),
            )
            assert ws.receive_json()["data"] == {"option_count": 1}

            client.delete(
                f"/rooms/{code}/submissions/{created['id']}", headers=auth(guest["token"])
            )
            assert ws.receive_json()["type"] == "submissions_changed"

            client.post(
                f"/rooms/{code}/contenders/remove",
                json={"key": "pizza"},
                headers=auth(room["token"]),
            )
            assert ws.receive_json()["data"] == {"option_count": 0}

    def test_events_only_reach_the_same_room(self, client, lobby, create_room, join_room):
        code, room, _ = lobby
        other = create_room()

        with connect(client, code, room["token"]) as ws:
            ws.receive_json()
            join_room(other["code"], "Elsewhere")
            join_room(code, "Here")

            assert ws.receive_json()["type"] == "participant_joined"


class TestHostHandoff:
    def test_disconnected_host_is_replaced_in_the_lobby(self, client, lobby, join_room, snapshot):
        code, room, guest = lobby
        later = join_room(code, "Later")

        with connect(client, code, later["token"]) as later_ws:
            later_ws.receive_json()
            with connect(client, code, guest["token"]) as guest_ws:
                guest_ws.receive_json()
                with connect(client, code, room["token"]) as host_ws:
                    host_ws.receive_json()

                # Sam joined before Later, so Sam is the longest-present connected participant.
                assert wait_until(
                    lambda: snapshot(code, guest["token"])["me"]["is_host"], timeout=5
                )

    def test_host_who_returns_within_the_grace_period_keeps_the_role(self, client, lobby, snapshot):
        code, room, guest = lobby

        with connect(client, code, guest["token"]) as guest_ws:
            guest_ws.receive_json()
            with connect(client, code, room["token"]) as host_ws:
                host_ws.receive_json()
            with connect(client, code, room["token"]) as host_ws:
                host_ws.receive_json()
                time.sleep(0.5)
                assert snapshot(code, room["token"])["me"]["is_host"] is True

    def test_host_stays_when_nobody_else_is_connected(self, client, lobby, snapshot):
        code, room, _ = lobby

        with connect(client, code, room["token"]) as host_ws:
            host_ws.receive_json()
        time.sleep(0.5)

        assert snapshot(code, room["token"])["me"]["is_host"] is True
