import unittest
from hardware import normalize_potentiometer, calculate_servo_angle
from color_sensor import classify_color
from config import PLAYERS


class InputTests(unittest.TestCase):

    def test_three_servo_steps_and_clamp(self):
        self.assertEqual(
            [calculate_servo_angle(failure_count) for failure_count in range(4)],
            [0, 60, 120, 180],
        )
        self.assertEqual(calculate_servo_angle(10), 180)
        self.assertEqual(calculate_servo_angle(-1), 0)

    def test_individual_pot_calibration(self):
        for player_configuration in PLAYERS.values():
            left_limit, center_value, right_limit = player_configuration["pot"]
            for raw_value, value in (
                (left_limit, -100),
                (center_value, 0),
                (right_limit, 100),
                (left_limit - 100, -100),
                (right_limit + 100, 100),
            ):
                self.assertEqual(
                    normalize_potentiometer(
                        raw_value, (left_limit, center_value, right_limit)
                    ),
                    value,
                )

    def test_observed_colors_and_invalid_readings(self):
        self.assertEqual(classify_color((7, 36, 82)), "blue")
        self.assertEqual(classify_color((87, 10, 9)), "red")
        self.assertEqual(classify_color((12, 72, 21)), "green")
        self.assertEqual(classify_color((11, 74, 18)), "green")
        self.assertIsNone(classify_color((0, 0, 0)))
        self.assertIsNone(classify_color((70, 70, 70)))


if __name__ == "__main__":
    unittest.main()
