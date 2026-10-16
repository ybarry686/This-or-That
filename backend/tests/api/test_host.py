"""Host transfer and host recovery (SPEC §3)."""

from tests.api.conftest import auth


def test_host_can_transfer_role(client, create_room, join_room, snapshot):
    room = create_room()
    guest = join_room(room["code"], "Sam")

    response = client.post(
        f"/rooms/{room['code']}/host/transfer",
        json={"participant_id": guest["participant_id"]},
        headers=auth(room["token"]),
    )

    assert response.status_code == 200
    assert snapshot(room["code"], guest["token"])["me"]["is_host"] is True
    assert snapshot(room["code"], room["token"])["me"]["is_host"] is False


def test_transfer_requires_host(client, create_room, join_room):
    room = create_room()
    guest = join_room(room["code"], "Sam")

    response = client.post(
        f"/rooms/{room['code']}/host/transfer",
        json={"participant_id": guest["participant_id"]},
        headers=auth(guest["token"]),
    )
    assert response.status_code == 403


def test_transfer_to_unknown_participant_is_404(client, create_room):
    room = create_room()

    response = client.post(
        f"/rooms/{room['code']}/host/transfer",
        json={"participant_id": "nobody"},
        headers=auth(room["token"]),
    )
    assert response.status_code == 404


def test_recovery_issues_a_new_host_token_and_revokes_the_old_one(client, create_room, snapshot):
    room = create_room()

    response = client.post(
        f"/rooms/{room['code']}/host/recover",
        json={"recovery_token": room["host_recovery_token"]},
    )

    assert response.status_code == 200
    recovered = response.json()
    assert recovered["participant_id"] == room["participant_id"]
    assert snapshot(room["code"], recovered["token"])["me"]["is_host"] is True
    assert client.get(f"/rooms/{room['code']}", headers=auth(room["token"])).status_code == 401


def test_recovery_reclaims_host_after_a_transfer(client, create_room, join_room, snapshot):
    room = create_room()
    guest = join_room(room["code"], "Sam")
    client.post(
        f"/rooms/{room['code']}/host/transfer",
        json={"participant_id": guest["participant_id"]},
        headers=auth(room["token"]),
    )

    recovered = client.post(
        f"/rooms/{room['code']}/host/recover",
        json={"recovery_token": room["host_recovery_token"]},
    ).json()

    assert snapshot(room["code"], recovered["token"])["me"]["is_host"] is True
    assert snapshot(room["code"], guest["token"])["me"]["is_host"] is False


def test_wrong_recovery_token_is_rejected(client, create_room):
    room = create_room()

    response = client.post(f"/rooms/{room['code']}/host/recover", json={"recovery_token": "wrong"})
    assert response.status_code == 401
