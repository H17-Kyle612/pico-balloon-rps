"""ハードウェアに依存しない、色・勝敗・パリィの判定。"""

COLOR_TO_HAND = {"red": "rock", "green": "scissors", "blue": "paper"}


def determine_winner(first_hand, second_hand):
    if (
        first_hand not in COLOR_TO_HAND.values()
        or second_hand not in COLOR_TO_HAND.values()
    ):
        raise ValueError("Both hands must be valid")
    if first_hand == second_hand:
        return 0
    return (
        1
        if (first_hand, second_hand)
        in (("rock", "scissors"), ("scissors", "paper"), ("paper", "rock"))
        else 2
    )


def normalize_potentiometer(raw_value, calibration):
    left_limit, center_value, right_limit = calibration
    if not left_limit < center_value < right_limit:
        raise ValueError("Invalid calibration")
    calibration_span = (
        center_value - left_limit
        if raw_value < center_value
        else right_limit - center_value
    )
    return max(-100, min(100, 100 * (raw_value - center_value) / calibration_span))


def is_parry_successful(current_value, target_value, tolerance=10):
    return abs(current_value - target_value) <= tolerance


def classify_color(rgb_values, minimum_brightness=15, dominance_ratio=1.4):
    """明るさと最大チャンネルの比率で色を判定する。照明が変わる場合は再校正する。"""
    channel_order = sorted(
        range(3), key=lambda channel_index: rgb_values[channel_index], reverse=True
    )
    strongest_channel, second_channel = (
        rgb_values[channel_order[0]],
        rgb_values[channel_order[1]],
    )
    if (
        strongest_channel < minimum_brightness
        or strongest_channel < max(1, second_channel) * dominance_ratio
    ):
        return None
    return ("red", "green", "blue")[channel_order[0]]


def calculate_servo_angle(
    failure_count, start_angle=0, end_angle=180, maximum_failures=3
):
    if maximum_failures <= 0 or not 0 <= start_angle <= end_angle <= 180:
        raise ValueError("Invalid servo range")
    failure_count = max(0, min(maximum_failures, failure_count))
    return start_angle + (end_angle - start_angle) * failure_count / maximum_failures
