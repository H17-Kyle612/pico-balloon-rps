import unittest
from effects import (
    create_hand_led_pixels,
    create_status_led_pixels,
    select_result_melody,
    MELODIES,
    LED_OFF,
)


class EffectsTests(unittest.TestCase):

    def test_own_and_opponent_swap(self):
        state = {"phase": "READY", "live_hands": ["rock", "paper"]}
        for start in (0, 4):
            for player in (1, 2):
                pixels = create_hand_led_pixels(state, player, 8, start)
                own = (28, 0, 0) if player == 1 else (0, 0, 28)
                other = (0, 0, 28) if player == 1 else (28, 0, 0)
                self.assertEqual(pixels[start : start + 4], [own] * 4)
                self.assertEqual(
                    [
                        player_configuration
                        for first_index, player_configuration in enumerate(pixels)
                        if not start <= first_index < start + 4
                    ],
                    [other] * 4,
                )

    def test_f1_count_increases(self):
        counts = []
        for elapsed_ms in (0, 750, 1500, 2250):
            counts.append(
                sum(
                    (
                        player_configuration != LED_OFF
                        for player_configuration in create_hand_led_pixels(
                            {"phase": "COUNTDOWN", "elapsed_ms": elapsed_ms}, 1, 8, 0
                        )
                    )
                )
            )
        self.assertEqual(counts, [2, 4, 6, 8])

    def test_parry_success_rotates_failure_blinks(self):
        game_state = {"phase": "RESULT", "winner": 2, "parried": True}
        self.assertNotEqual(
            create_status_led_pixels(game_state, 1, 8, 0),
            create_status_led_pixels(game_state, 1, 8, 100),
        )
        self.assertEqual(select_result_melody(game_state, 1), "parry_ok")
        game_state["parried"] = False
        self.assertEqual(
            create_status_led_pixels(game_state, 1, 8, 0), [(28, 0, 0)] * 8
        )
        self.assertEqual(create_status_led_pixels(game_state, 1, 8, 300), [LED_OFF] * 8)
        self.assertEqual(select_result_melody(game_state, 1), "parry_fail")

    def test_final_status_and_melodies(self):
        game_state = {"phase": "GAME_OVER", "winner": 1}
        self.assertEqual(select_result_melody(game_state, 1), "champion")
        self.assertEqual(select_result_melody(game_state, 2), "defeat")
        for notes in MELODIES.values():
            self.assertTrue(
                all((duration > 0 and frequency >= 0 for frequency, duration in notes))
            )


if __name__ == "__main__":
    unittest.main()
