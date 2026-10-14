import unittest
from unittest.mock import patch
from game import GameController, determine_winner


class TestClock:
    ticks_add = staticmethod(
        lambda current_time_ms, duration_ms: current_time_ms + duration_ms
    )
    ticks_diff = staticmethod(
        lambda first_time_ms, second_time_ms: first_time_ms - second_time_ms
    )


def sample(hand="rock", pot=0):
    return {"hand": hand, "stable": True, "pot": pot}


def remote(controller, current_time_ms, hand="scissors", pot=0):
    return {
        "at": current_time_ms,
        "token": controller.state["token"],
        "sample": sample(hand, pot),
    }


class GameFlowTests(unittest.TestCase):

    def setUp(self):
        clock_patch = patch("game.time", TestClock)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)

    def setup_round(self):
        controller = GameController()
        controller.update(0, sample("rock", 30), remote(controller, 0, pot=-40))
        controller.update(1, sample("rock", 30), remote(controller, 1, pot=-40))
        controller.update(1001, sample("rock", 30), remote(controller, 1001, pot=-40))
        self.assertEqual(controller.state["phase"], "COUNTDOWN")
        controller.update(4001, sample("rock", -90), remote(controller, 4001, pot=90))
        self.assertEqual(controller.state["phase"], "DEFENSE")
        return controller

    def test_frozen_target_and_duplicate_result(self):
        controller = self.setup_round()
        controller.update(7001, sample("rock", -90), remote(controller, 7001, pot=31))
        self.assertEqual(controller.state["phase"], "DEFENSE_SAMPLE")
        controller.update(7010, sample(), remote(controller, 7010, pot=31))
        self.assertTrue(controller.state["defended"])
        self.assertEqual(controller.state["damage"], [0, 0])

    def test_player_one_defends_against_player_two_target(self):
        controller = GameController()
        controller.update(0, sample("rock", -40), remote(controller, 0, "paper", 30))
        controller.update(1, sample("rock", -40), remote(controller, 1, "paper", 30))
        controller.update(
            1001, sample("rock", -40), remote(controller, 1001, "paper", 30)
        )
        controller.update(
            4001, sample("rock", 90), remote(controller, 4001, "paper", -90)
        )
        self.assertEqual(controller.state["winner"], 2)
        controller.update(
            7001, sample("rock", 31), remote(controller, 7001, "paper", -90)
        )
        controller.update(
            7010, sample("rock", -100), remote(controller, 7010, "paper", -90)
        )
        self.assertTrue(controller.state["defended"])
        self.assertEqual(controller.state["damage"], [0, 0])

    def test_all_matchups(self):
        hands = ("rock", "scissors", "paper")
        expected = ((0, 1, 2), (2, 0, 1), (1, 2, 0))
        for first_index, first_hand in enumerate(hands):
            for second_index, second_hand in enumerate(hands):
                self.assertEqual(
                    determine_winner(first_hand, second_hand),
                    expected[first_index][second_index],
                )
        with self.assertRaises(ValueError):
            determine_winner(None, "rock")

    def test_defense_tolerance_boundary(self):
        for current_value, target_value, expected in (
            (-20, -30, True),
            (-19.9, -30, False),
            (90, 100, True),
        ):
            with self.subTest(current_value=current_value, target_value=target_value):
                controller = GameController()
                controller.target_potentiometer_values = (target_value, 0)
                controller.state["winner"] = 1
                controller.change_phase("DEFENSE_SAMPLE", 0, 1000)
                controller.update(1, sample(), remote(controller, 1, pot=current_value))
                self.assertEqual(controller.state["defended"], expected)
                self.assertEqual(controller.state["damage"], [0, 0 if expected else 1])

    def test_damage_once(self):
        controller = self.setup_round()
        controller.update(7001, sample(), remote(controller, 7001, pot=-100))
        controller.update(7010, sample(), remote(controller, 7010, pot=-100))
        self.assertEqual(controller.state["damage"], [0, 1])
        controller.update(7011, sample(), remote(controller, 7011, pot=-100))
        self.assertEqual(controller.state["damage"], [0, 1])

    def test_third_failure_finishes_and_latches(self):
        for loser in (1, 2):
            controller = self.setup_round()
            controller.state["winner"] = 3 - loser
            controller.state["damage"][loser - 1] = 2
            controller.target_potentiometer_values = (30, 30)
            controller.update(
                7001, sample(pot=-100), remote(controller, 7001, pot=-100)
            )
            controller.update(
                7010, sample(pot=-100), remote(controller, 7010, pot=-100)
            )
            self.assertEqual(controller.state["phase"], "GAME_OVER")
            self.assertEqual(controller.state["damage"][loser - 1], 3)
            self.assertEqual(controller.state["loser"], loser)
            controller.update(100000, sample(), None)
            self.assertEqual(controller.state["phase"], "GAME_OVER")
            self.assertEqual(controller.state["damage"][loser - 1], 3)

    def test_stale_packet_and_disconnect(self):
        controller = self.setup_round()
        stale = {
            "at": 7001,
            "token": controller.state["token"],
            "sample": sample(pot=-100),
        }
        controller.update(7001, sample(), stale)
        controller.update(7010, sample(), stale)
        self.assertEqual(controller.state["phase"], "DEFENSE_SAMPLE")
        controller.update(8500, sample(), None)
        self.assertEqual(controller.state["phase"], "WAIT")
        self.assertEqual(controller.state["damage"], [0, 0])


if __name__ == "__main__":
    unittest.main()
