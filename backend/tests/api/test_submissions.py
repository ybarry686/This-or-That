"""Lobby submissions, visibility, duplicate merging and host curation (SPEC §5)."""

import pytest

from tests.api.conftest import auth


@pytest.fixture
def lobby(create_room, join_room):
    room = create_room()
    guest = join_room(room["code"], "Sam")
    return room["code"], room, guest


class TestSubmit:
    def test_submission_is_returned_and_listed_as_mine(self, lobby, submit, snapshot):
        code, _, guest = lobby

        created = submit(code, guest["token"], "  Pizza  ")

        assert created["text"] == "Pizza"
        mine = snapshot(code, guest["token"])["my_submissions"]
        assert mine == [{"id": created["id"], "text": "Pizza"}]

    @pytest.mark.parametrize("text", ["", "   ", "!!!", "x" * 81])
    def test_invalid_text_is_rejected(self, lobby, submit, text):
        code, _, guest = lobby

        submit(code, guest["token"], text, expected_status=422)

    def test_per_participant_limit_is_enforced(self, lobby, submit):
        code, _, guest = lobby
        for text in ["A", "B", "C"]:
            submit(code, guest["token"], text)

        error = submit(code, guest["token"], "D", expected_status=409)
        assert "3" in error["detail"]

    def test_limit_counts_duplicates_too(self, lobby, submit):
        code, _, guest = lobby
        for _ in range(3):
            submit(code, guest["token"], "Pizza")

        submit(code, guest["token"], "Tacos", expected_status=409)

    def test_requires_auth(self, client, lobby):
        code, _, _ = lobby

        assert client.post(f"/rooms/{code}/submissions", json={"text": "x"}).status_code == 401

    def test_unique_option_cap_is_64(self, client, create_room, join_room, submit):
        room = create_room(settings={"max_participants": 50, "max_submissions": 10})
        code = room["code"]
        tokens = [room["token"]] + [join_room(code, f"P{i}")["token"] for i in range(6)]
        options = iter(range(64))
        for token in tokens:
            for _ in range(10):
                n = next(options, None)
                if n is None:
                    break
                submit(code, token, f"Option {n}")

        error = submit(code, tokens[-1], "One too many", expected_status=409)
        assert "64" in error["detail"]
        # A duplicate of an existing option does not add a contender, so it is still allowed.
        submit(code, tokens[-1], "option 1")


class TestVisibility:
    def test_guests_see_only_their_own_submissions_and_the_option_count(
        self, lobby, submit, snapshot
    ):
        code, room, guest = lobby
        submit(code, room["token"], "Pizza")
        submit(code, guest["token"], "Tacos")
        submit(code, guest["token"], "pizza!")

        snap = snapshot(code, guest["token"])
        assert snap["option_count"] == 2
        assert [s["text"] for s in snap["my_submissions"]] == ["Tacos", "pizza!"]
        assert snap["contenders"] is None

    def test_host_sees_all_contenders_with_attribution(self, lobby, submit, snapshot):
        code, room, guest = lobby
        submit(code, room["token"], "Pizza")
        submit(code, guest["token"], "Tacos")
        submit(code, guest["token"], "pizza!")

        contenders = snapshot(code, room["token"])["contenders"]
        assert [c["display_text"] for c in contenders] == ["Pizza", "Tacos"]
        pizza = contenders[0]
        assert pizza["key"] == "pizza"
        assert [s["participant_id"] for s in pizza["submissions"]] == [
            room["participant_id"],
            guest["participant_id"],
        ]


class TestDeleteOwnSubmission:
    def test_participant_can_delete_own_submission(self, client, lobby, submit, snapshot):
        code, _, guest = lobby
        created = submit(code, guest["token"], "Pizza")

        response = client.delete(
            f"/rooms/{code}/submissions/{created['id']}", headers=auth(guest["token"])
        )

        assert response.status_code == 204
        assert snapshot(code, guest["token"])["my_submissions"] == []

    def test_cannot_delete_someone_elses_submission(self, client, lobby, submit):
        code, room, guest = lobby
        created = submit(code, room["token"], "Pizza")

        response = client.delete(
            f"/rooms/{code}/submissions/{created['id']}", headers=auth(guest["token"])
        )
        assert response.status_code == 404

    def test_deleting_frees_up_the_limit(self, client, lobby, submit):
        code, _, guest = lobby
        ids = [submit(code, guest["token"], t)["id"] for t in ["A", "B", "C"]]
        client.delete(f"/rooms/{code}/submissions/{ids[0]}", headers=auth(guest["token"]))

        submit(code, guest["token"], "D")


class TestHostCuration:
    def test_host_can_merge_two_contenders(self, client, lobby, submit, snapshot):
        code, room, guest = lobby
        submit(code, room["token"], "Pizza")
        submit(code, guest["token"], "Pizza Hut")

        response = client.post(
            f"/rooms/{code}/contenders/merge",
            json={"source_key": "pizza hut", "target_key": "pizza"},
            headers=auth(room["token"]),
        )

        assert response.status_code == 200
        [contender] = snapshot(code, room["token"])["contenders"]
        assert contender["display_text"] == "Pizza"
        assert len(contender["submissions"]) == 2

    def test_new_duplicate_of_merged_option_joins_the_merged_contender(
        self, client, lobby, submit, snapshot
    ):
        code, room, guest = lobby
        submit(code, room["token"], "Pizza")
        submit(code, guest["token"], "Pizza Hut")
        client.post(
            f"/rooms/{code}/contenders/merge",
            json={"source_key": "pizza hut", "target_key": "pizza"},
            headers=auth(room["token"]),
        )

        submit(code, guest["token"], "pizza hut!")

        assert snapshot(code, room["token"])["option_count"] == 1

    def test_merge_with_unknown_key_is_404(self, client, lobby, submit):
        code, room, _ = lobby
        submit(code, room["token"], "Pizza")

        response = client.post(
            f"/rooms/{code}/contenders/merge",
            json={"source_key": "nope", "target_key": "pizza"},
            headers=auth(room["token"]),
        )
        assert response.status_code == 404

    def test_merge_into_itself_is_rejected(self, client, lobby, submit):
        code, room, _ = lobby
        submit(code, room["token"], "Pizza")

        response = client.post(
            f"/rooms/{code}/contenders/merge",
            json={"source_key": "pizza", "target_key": "pizza"},
            headers=auth(room["token"]),
        )
        assert response.status_code == 422

    def test_host_can_remove_a_contender(self, client, lobby, submit, snapshot):
        code, room, guest = lobby
        submit(code, guest["token"], "Pizza")
        submit(code, guest["token"], "pizza")
        submit(code, guest["token"], "Tacos")

        response = client.post(
            f"/rooms/{code}/contenders/remove", json={"key": "pizza"}, headers=auth(room["token"])
        )

        assert response.status_code == 200
        snap = snapshot(code, guest["token"])
        assert snap["option_count"] == 1
        assert [s["text"] for s in snap["my_submissions"]] == ["Tacos"]

    @pytest.mark.parametrize("action", ["merge", "remove"])
    def test_guests_cannot_curate(self, client, lobby, submit, action):
        code, room, guest = lobby
        submit(code, room["token"], "Pizza")
        submit(code, room["token"], "Tacos")
        body = (
            {"source_key": "tacos", "target_key": "pizza"}
            if action == "merge"
            else {"key": "pizza"}
        )

        response = client.post(
            f"/rooms/{code}/contenders/{action}", json=body, headers=auth(guest["token"])
        )
        assert response.status_code == 403


class TestVersion:
    def test_submissions_bump_the_version(self, lobby, submit, snapshot):
        code, room, _ = lobby
        before = snapshot(code, room["token"])["version"]

        submit(code, room["token"], "Pizza")

        assert snapshot(code, room["token"])["version"] > before


class TestConcurrency:
    def test_parallel_submissions_cannot_exceed_the_limit(self, lobby):
        from concurrent.futures import ThreadPoolExecutor

        from fastapi.testclient import TestClient

        from app.main import app

        code, _, guest = lobby

        def attempt(n: int) -> int:
            with TestClient(app) as c:
                return c.post(
                    f"/rooms/{code}/submissions",
                    json={"text": f"Option {n}"},
                    headers=auth(guest["token"]),
                ).status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(attempt, range(8)))

        assert statuses.count(201) == 3
        assert statuses.count(409) == 5
