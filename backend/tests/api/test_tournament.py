"""Starting the tournament, voting, closing matchups, ties, and the champion (SPEC §6-§8)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.config import get_settings
from app.main import app
from app.models import Matchup, Vote
from app.tournament import service as tournament_service
from tests.api.conftest import auth


@pytest.fixture(autouse=True)
def no_reveal_pause(monkeypatch):
    monkeypatch.setattr(get_settings(), "reveal_seconds", 0)


class PickIndex:
    """Coin-flip stub: always picks the option at `index`."""

    def __init__(self, index: int):
        self.index = index

    def choice(self, seq):
        return seq[self.index]


@pytest.fixture
def coin(monkeypatch):
    def _set(index: int):
        monkeypatch.setattr(tournament_service, "coin", PickIndex(index))

    return _set


@pytest.fixture
def game(create_room, join_room, submit):
    """A lobby with a host, one guest, and the given options (submitted by the host)."""

    def _game(options=("Pizza", "Tacos"), max_submissions=10):
        room = create_room(settings={"max_submissions": max_submissions})
        guest = join_room(room["code"], "Sam")
        for text in options:
            submit(room["code"], room["token"], text)
        return room["code"], room, guest

    return _game


@pytest.fixture
def start(client):
    def _start(code, token, expected_status=200):
        response = client.post(f"/rooms/{code}/start", headers=auth(token))
        assert response.status_code == expected_status, response.text
        return response.json()

    return _start


@pytest.fixture
def vote(client):
    def _vote(code, token, matchup_id, contender_id, expected_status=200):
        response = client.post(
            f"/rooms/{code}/votes",
            json={"matchup_id": matchup_id, "contender_id": contender_id},
            headers=auth(token),
        )
        assert response.status_code == expected_status, response.text
        return response.json()

    return _vote


@pytest.fixture
def close(client):
    def _close(code, token, matchup_id, expected_status=200):
        response = client.post(f"/rooms/{code}/matchups/{matchup_id}/close", headers=auth(token))
        assert response.status_code == expected_status, response.text
        return response.json()

    return _close


def current_matchup(snap):
    current = snap["tournament"]["current"]
    for matchups in snap["tournament"]["rounds"]:
        for m in matchups:
            if m["id"] == current["matchup_id"]:
                return m
    raise AssertionError("current matchup not found in rounds")


def names(snap):
    return {c["id"]: c["display_text"] for c in snap["tournament"]["contenders"]}


class TestStart:
    def test_host_starts_and_everyone_sees_the_bracket(self, game, start, snapshot):
        code, room, guest = game(("Pizza", "Tacos", "Sushi", "Ramen"))

        start(code, room["token"])

        snap = snapshot(code, guest["token"])
        assert snap["status"] == "in_progress"
        assert sorted(names(snap).values()) == ["Pizza", "Ramen", "Sushi", "Tacos"]
        assert [len(r) for r in snap["tournament"]["rounds"]] == [2, 1]
        assert snap["tournament"]["champion_id"] is None
        assert snap["server_time"]

        current = snap["tournament"]["current"]
        matchup = current_matchup(snap)
        assert (matchup["round"], matchup["index"]) == (0, 0)
        assert matchup["status"] == "voting"
        assert current["phase"] == "vote"
        starts = datetime.fromisoformat(current["starts_at"])
        ends = datetime.fromisoformat(current["ends_at"])
        assert ends - starts == timedelta(seconds=30)

    def test_duplicates_become_one_contender_with_all_submitters(
        self, game, submit, start, snapshot
    ):
        code, room, guest = game(("Pizza", "Tacos"))
        submit(code, guest["token"], "pizza!")

        start(code, room["token"])

        contenders = snapshot(code, guest["token"])["tournament"]["contenders"]
        pizza = next(c for c in contenders if c["display_text"] == "Pizza")
        assert set(pizza["submitter_ids"]) == {room["participant_id"], guest["participant_id"]}
        assert len(contenders) == 2

    def test_odd_field_gets_a_decided_bye(self, game, start, snapshot):
        code, room, _ = game(("A", "B", "C"))

        start(code, room["token"])

        first_round = snapshot(code, room["token"])["tournament"]["rounds"][0]
        [bye] = [m for m in first_round if m["is_bye"]]
        assert bye["status"] == "decided"
        assert bye["outcome"] == "bye"
        assert bye["winner_id"] == bye["contender_a_id"]

    def test_only_the_host_can_start(self, game, start):
        code, _, guest = game()

        start(code, guest["token"], expected_status=403)

    def test_needs_at_least_two_options(self, game, start):
        code, room, _ = game(("Pizza",))

        error = start(code, room["token"], expected_status=409)
        assert "2" in error["detail"]

    def test_cannot_start_twice(self, game, start):
        code, room, _ = game()
        start(code, room["token"])

        start(code, room["token"], expected_status=409)

    def test_lobby_actions_are_locked_after_start(self, client, game, start, submit):
        code, room, guest = game()
        start(code, room["token"])

        submit(code, guest["token"], "Late idea", expected_status=409)
        response = client.patch(
            f"/rooms/{code}", json={"vote_seconds": 60}, headers=auth(room["token"])
        )
        assert response.status_code == 409

    def test_late_joiners_can_still_join(self, game, start, join_room):
        code, room, _ = game()
        start(code, room["token"])

        assert join_room(code, "Latecomer")["nickname"] == "Latecomer"


class TestVoting:
    def test_vote_is_recorded_without_revealing_the_tally(self, game, start, vote, snapshot):
        code, room, guest = game()
        start(code, room["token"])
        matchup = current_matchup(snapshot(code, guest["token"]))

        vote(code, guest["token"], matchup["id"], matchup["contender_a_id"])

        guest_view = snapshot(code, guest["token"])
        current = guest_view["tournament"]["current"]
        assert current["my_vote"] == matchup["contender_a_id"]
        assert current["voted_participant_ids"] == [guest["participant_id"]]
        assert current["eligible_count"] == 2
        assert (current_matchup(guest_view)["votes_a"], current_matchup(guest_view)["votes_b"]) == (
            0,
            0,
        )
        assert snapshot(code, room["token"])["tournament"]["current"]["my_vote"] is None

    def test_changing_a_vote_replaces_it(self, game, start, vote, snapshot, session):
        code, room, guest = game()
        start(code, room["token"])
        matchup = current_matchup(snapshot(code, guest["token"]))

        vote(code, guest["token"], matchup["id"], matchup["contender_a_id"])
        vote(code, guest["token"], matchup["id"], matchup["contender_b_id"])

        current = snapshot(code, guest["token"])["tournament"]["current"]
        assert current["my_vote"] == matchup["contender_b_id"]
        assert current["voted_participant_ids"] == [guest["participant_id"]]
        assert len(session.scalars(select(Vote)).all()) == 1

    def test_vote_must_target_the_open_matchup(self, game, start, vote, snapshot):
        code, room, guest = game(("A", "B", "C", "D"))
        start(code, room["token"])
        snap = snapshot(code, guest["token"])
        other = snap["tournament"]["rounds"][0][1]

        vote(code, guest["token"], other["id"], other["contender_a_id"], expected_status=409)

    def test_vote_must_be_for_a_contender_in_the_matchup(self, game, start, vote, snapshot):
        code, room, guest = game(("A", "B", "C", "D"))
        start(code, room["token"])
        snap = snapshot(code, guest["token"])
        matchup = current_matchup(snap)
        outsider = snap["tournament"]["rounds"][0][1]["contender_a_id"]

        vote(code, guest["token"], matchup["id"], outsider, expected_status=422)

    def test_cannot_vote_before_the_tournament_starts(self, game, vote):
        code, _, guest = game()

        vote(code, guest["token"], "nope", "nope", expected_status=409)

    def test_cannot_vote_after_the_deadline(self, game, start, vote, snapshot, session):
        code, room, guest = game()
        start(code, room["token"])
        matchup = current_matchup(snapshot(code, guest["token"]))
        session.execute(
            update(Matchup)
            .where(Matchup.id == matchup["id"])
            .values(ends_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()

        error = vote(
            code, guest["token"], matchup["id"], matchup["contender_a_id"], expected_status=409
        )
        assert "closed" in error["detail"].lower()

    def test_cannot_vote_before_the_window_opens(self, game, start, vote, snapshot, monkeypatch):
        monkeypatch.setattr(get_settings(), "reveal_seconds", 60)
        code, room, guest = game()
        start(code, room["token"])
        matchup = current_matchup(snapshot(code, guest["token"]))

        error = vote(
            code, guest["token"], matchup["id"], matchup["contender_a_id"], expected_status=409
        )
        assert "not started" in error["detail"].lower()

    def test_late_joiner_waits_for_the_next_matchup(
        self, game, start, vote, close, join_room, snapshot
    ):
        code, room, _ = game(("A", "B", "C", "D"))
        start(code, room["token"])
        late = join_room(code, "Late")
        first = current_matchup(snapshot(code, late["token"]))

        assert snapshot(code, late["token"])["tournament"]["current"]["can_vote"] is False
        vote(code, late["token"], first["id"], first["contender_a_id"], expected_status=403)

        vote(code, room["token"], first["id"], first["contender_a_id"])
        close(code, room["token"], first["id"])
        second = current_matchup(snapshot(code, late["token"]))
        assert snapshot(code, late["token"])["tournament"]["current"]["can_vote"] is True
        vote(code, late["token"], second["id"], second["contender_a_id"])


class TestClosing:
    def test_host_close_decides_the_winner_and_opens_the_next_matchup(
        self, game, start, vote, close, snapshot
    ):
        code, room, guest = game(("A", "B", "C", "D"))
        start(code, room["token"])
        first = current_matchup(snapshot(code, room["token"]))
        vote(code, room["token"], first["id"], first["contender_b_id"])
        vote(code, guest["token"], first["id"], first["contender_b_id"])

        close(code, room["token"], first["id"])

        snap = snapshot(code, guest["token"])
        decided = snap["tournament"]["rounds"][0][0]
        assert decided["status"] == "decided"
        assert decided["outcome"] == "votes"
        assert decided["winner_id"] == first["contender_b_id"]
        assert (decided["votes_a"], decided["votes_b"]) == (0, 2)
        assert snap["tournament"]["rounds"][1][0]["contender_a_id"] == first["contender_b_id"]
        assert current_matchup(snap)["index"] == 1

    def test_only_the_host_can_close(self, game, start, close, snapshot):
        code, room, guest = game()
        start(code, room["token"])
        matchup = current_matchup(snapshot(code, guest["token"]))

        close(code, guest["token"], matchup["id"], expected_status=403)

    def test_closing_an_already_decided_matchup_is_rejected(
        self, game, start, vote, close, snapshot
    ):
        code, room, _ = game(("A", "B", "C", "D"))
        start(code, room["token"])
        first = current_matchup(snapshot(code, room["token"]))
        vote(code, room["token"], first["id"], first["contender_a_id"])
        close(code, room["token"], first["id"])

        close(code, room["token"], first["id"], expected_status=409)

        snap = snapshot(code, room["token"])
        assert current_matchup(snap)["index"] == 1
        assert snap["tournament"]["rounds"][1][0]["contender_b_id"] is None

    def test_tie_triggers_a_revote(self, game, start, vote, close, snapshot):
        code, room, guest = game()
        start(code, room["token"])
        m = current_matchup(snapshot(code, room["token"]))
        vote(code, room["token"], m["id"], m["contender_a_id"])
        vote(code, guest["token"], m["id"], m["contender_b_id"])

        close(code, room["token"], m["id"])

        snap = snapshot(code, guest["token"])
        current = snap["tournament"]["current"]
        assert current["matchup_id"] == m["id"]
        assert current["phase"] == "revote"
        assert current["my_vote"] is None
        assert current["voted_participant_ids"] == []
        assert current_matchup(snap)["status"] == "revote"
        assert (current_matchup(snap)["votes_a"], current_matchup(snap)["votes_b"]) == (1, 1)
        ends = datetime.fromisoformat(current["ends_at"])
        starts = datetime.fromisoformat(current["starts_at"])
        assert ends - starts == timedelta(seconds=15)

    def test_revote_majority_wins(self, game, start, vote, close, snapshot):
        code, room, guest = game()
        start(code, room["token"])
        m = current_matchup(snapshot(code, room["token"]))
        vote(code, room["token"], m["id"], m["contender_a_id"])
        vote(code, guest["token"], m["id"], m["contender_b_id"])
        close(code, room["token"], m["id"])

        vote(code, room["token"], m["id"], m["contender_b_id"])
        close(code, room["token"], m["id"])

        snap = snapshot(code, room["token"])
        decided = snap["tournament"]["rounds"][0][0]
        assert decided["winner_id"] == m["contender_b_id"]
        assert decided["outcome"] == "votes"
        assert (decided["votes_a"], decided["votes_b"]) == (0, 1)

    def test_tied_revote_is_settled_by_coin_flip(self, game, start, vote, close, snapshot, coin):
        coin(1)
        code, room, guest = game()
        start(code, room["token"])
        m = current_matchup(snapshot(code, room["token"]))
        for _ in range(2):
            vote(code, room["token"], m["id"], m["contender_a_id"])
            vote(code, guest["token"], m["id"], m["contender_b_id"])
            close(code, room["token"], m["id"])

        decided = snapshot(code, room["token"])["tournament"]["rounds"][0][0]
        assert decided["outcome"] == "coin_flip"
        assert decided["winner_id"] == m["contender_b_id"]

    def test_no_votes_at_all_still_resolves(self, game, start, close, snapshot, coin):
        coin(0)
        code, room, _ = game()
        start(code, room["token"])
        m = current_matchup(snapshot(code, room["token"]))

        close(code, room["token"], m["id"])
        close(code, room["token"], m["id"])

        snap = snapshot(code, room["token"])
        assert snap["status"] == "finished"
        assert snap["tournament"]["champion_id"] == m["contender_a_id"]


class TestChampion:
    @pytest.mark.parametrize("count", [2, 3, 5, 8])
    def test_playing_every_matchup_crowns_a_champion(
        self, count, game, start, vote, close, snapshot
    ):
        options = [f"Option {i}" for i in range(count)]
        code, room, guest = game(options)
        start(code, room["token"])

        played = 0
        while (snap := snapshot(code, room["token"]))["status"] == "in_progress":
            m = current_matchup(snap)
            vote(code, room["token"], m["id"], m["contender_a_id"])
            close(code, room["token"], m["id"])
            played += 1

        assert played == count - 1
        assert snap["status"] == "finished"
        final = snap["tournament"]["rounds"][-1][0]
        assert snap["tournament"]["champion_id"] == final["winner_id"]
        assert snap["tournament"]["current"] is None
        assert all(m["status"] == "decided" for r in snap["tournament"]["rounds"] for m in r)

    def test_finished_room_rejects_votes_and_joins(
        self, client, game, start, vote, close, snapshot
    ):
        code, room, guest = game()
        start(code, room["token"])
        m = current_matchup(snapshot(code, room["token"]))
        vote(code, room["token"], m["id"], m["contender_a_id"])
        close(code, room["token"], m["id"])

        vote(code, guest["token"], m["id"], m["contender_a_id"], expected_status=409)
        assert client.post(f"/rooms/{code}/join", json={"nickname": "X"}).status_code == 409


class TestRealtime:
    def connect(self, client, code, token):
        return client.websocket_connect(f"/rooms/{code}/ws?token={token}")

    def test_everyone_voting_closes_the_matchup_early(self, client, game, start, vote, snapshot):
        code, room, guest = game()
        start(code, room["token"])
        m = current_matchup(snapshot(code, room["token"]))

        with self.connect(client, code, room["token"]) as host_ws:
            host_ws.receive_json()
            with self.connect(client, code, guest["token"]) as guest_ws:
                guest_ws.receive_json()
                vote(code, room["token"], m["id"], m["contender_a_id"])
                assert snapshot(code, room["token"])["status"] == "in_progress"

                vote(code, guest["token"], m["id"], m["contender_a_id"])
                assert snapshot(code, room["token"])["status"] == "finished"

    def test_tournament_events_are_broadcast(self, client, game, start, vote, snapshot):
        code, room, _ = game()

        with self.connect(client, code, room["token"]) as ws:
            ws.receive_json()
            start(code, room["token"])
            started = [ws.receive_json(), ws.receive_json()]
            assert [e["type"] for e in started] == ["tournament_started", "matchup_opened"]

            # The host is the only connected voter, so their vote closes the matchup.
            m = current_matchup(snapshot(code, room["token"]))
            vote(code, room["token"], m["id"], m["contender_b_id"])
            cast = ws.receive_json()
            assert cast["type"] == "vote_cast"
            assert cast["data"] == {"matchup_id": m["id"], "voted_count": 1}
            assert m["contender_b_id"] not in str(cast)

            decided = ws.receive_json()
            assert decided["type"] == "matchup_decided"
            assert decided["data"]["winner_id"] == m["contender_b_id"]
            assert decided["data"]["votes"] == {m["contender_a_id"]: 0, m["contender_b_id"]: 1}
            crowned = ws.receive_json()
            assert crowned["type"] == "champion_crowned"
            assert crowned["data"] == {"contender_id": m["contender_b_id"]}
            assert crowned["version"] >= decided["version"] > cast["version"]


class TestConcurrency:
    def test_parallel_closes_resolve_the_matchup_once(self, game, start, vote, snapshot):
        code, room, _ = game(("A", "B", "C", "D"))
        start(code, room["token"])
        m = current_matchup(snapshot(code, room["token"]))
        vote(code, room["token"], m["id"], m["contender_a_id"])

        def attempt(_):
            with TestClient(app) as c:
                return c.post(
                    f"/rooms/{code}/matchups/{m['id']}/close", headers=auth(room["token"])
                ).status_code

        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(attempt, range(6)))

        assert statuses.count(200) == 1
        assert statuses.count(409) == 5
        snap = snapshot(code, room["token"])
        assert current_matchup(snap)["index"] == 1
        assert snap["tournament"]["rounds"][1][0]["contender_b_id"] is None

    def test_parallel_votes_store_a_single_vote(self, game, start, snapshot, session):
        code, room, guest = game()
        start(code, room["token"])
        m = current_matchup(snapshot(code, guest["token"]))

        def attempt(n):
            choice = m["contender_a_id"] if n % 2 else m["contender_b_id"]
            with TestClient(app) as c:
                return c.post(
                    f"/rooms/{code}/votes",
                    json={"matchup_id": m["id"], "contender_id": choice},
                    headers=auth(guest["token"]),
                ).status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(attempt, range(8)))

        assert statuses == [200] * 8
        assert len(session.scalars(select(Vote)).all()) == 1
