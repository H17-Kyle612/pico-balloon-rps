import unittest
from unittest.mock import patch
from referee import GameReferee


class TestClock:
    ticks_add = staticmethod(
        lambda current_time_ms, duration_ms: current_time_ms + duration_ms
    )
    ticks_diff = staticmethod(
        lambda first_time_ms, second_time_ms: first_time_ms - second_time_ms
    )


def sample(hand="rock", pot=0):
    return {"hand": hand, "stable": True, "pot": pot}


def remote(referee, current_time_ms, hand="scissors", pot=0):
    return {
        "at": current_time_ms,
        "token": referee.state["token"],
        "sample": sample(hand, pot),
    }


class RefereeTests(unittest.TestCase):

    def setUp(self):
        clock_patch = patch("referee.time", TestClock)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)

    def setup_round(self):
        referee = GameReferee()
        referee.update(0, sample("rock", 30), remote(referee, 0, pot=-40))
        referee.update(1, sample("rock", 30), remote(referee, 1, pot=-40))
        referee.update(1001, sample("rock", 30), remote(referee, 1001, pot=-40))
        self.assertEqual(referee.state["phase"], "COUNTDOWN")
        referee.update(4001, sample("rock", -90), remote(referee, 4001, pot=90))
        self.assertEqual(referee.state["phase"], "PARRY")
        return referee

    def test_frozen_target_and_duplicate_result(self):
        referee = self.setup_round()
        referee.update(7001, sample("rock", -90), remote(referee, 7001, pot=31))
        self.assertEqual(referee.state["phase"], "PARRY_SAMPLE")
        referee.update(7010, sample(), remote(referee, 7010, pot=31))
        self.assertTrue(referee.state["parried"])
        self.assertEqual(referee.state["damage"], [0, 0])

    def test_player_one_parries_against_player_two_target(self):
        referee = GameReferee()
        referee.update(0, sample("rock", -40), remote(referee, 0, "paper", 30))
        referee.update(1, sample("rock", -40), remote(referee, 1, "paper", 30))
        referee.update(1001, sample("rock", -40), remote(referee, 1001, "paper", 30))
        referee.update(4001, sample("rock", 90), remote(referee, 4001, "paper", -90))
        self.assertEqual(referee.state["winner"], 2)
        referee.update(7001, sample("rock", 31), remote(referee, 7001, "paper", -90))
        referee.update(7010, sample("rock", -100), remote(referee, 7010, "paper", -90))
        self.assertTrue(referee.state["parried"])
        self.assertEqual(referee.state["damage"], [0, 0])

    def test_damage_once(self):
        referee = self.setup_round()
        referee.update(7001, sample(), remote(referee, 7001, pot=-100))
        referee.update(7010, sample(), remote(referee, 7010, pot=-100))
        self.assertEqual(referee.state["damage"], [0, 1])
        referee.update(7011, sample(), remote(referee, 7011, pot=-100))
        self.assertEqual(referee.state["damage"], [0, 1])

    def test_third_failure_finishes_and_latches(self):
        for loser in (1, 2):
            referee = self.setup_round()
            referee.state["winner"] = 3 - loser
            referee.state["damage"][loser - 1] = 2
            referee.target_potentiometer_values = (30, 30)
            referee.update(7001, sample(pot=-100), remote(referee, 7001, pot=-100))
            referee.update(7010, sample(pot=-100), remote(referee, 7010, pot=-100))
            self.assertEqual(referee.state["phase"], "GAME_OVER")
            self.assertEqual(referee.state["damage"][loser - 1], 3)
            self.assertEqual(referee.state["loser"], loser)
            referee.update(100000, sample(), None)
            self.assertEqual(referee.state["phase"], "GAME_OVER")
            self.assertEqual(referee.state["damage"][loser - 1], 3)

    def test_stale_packet_and_disconnect(self):
        referee = self.setup_round()
        stale = {
            "at": 7001,
            "token": referee.state["token"],
            "sample": sample(pot=-100),
        }
        referee.update(7001, sample(), stale)
        referee.update(7010, sample(), stale)
        self.assertEqual(referee.state["phase"], "PARRY_SAMPLE")
        referee.update(8500, sample(), None)
        self.assertEqual(referee.state["phase"], "WAIT")
        self.assertEqual(referee.state["damage"], [0, 0])


if __name__ == "__main__":
    unittest.main()
