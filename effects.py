"""LEDパターンと通知音。ゲーム進行はgame.pyが担当する。"""

from config import DEFENSE_DURATION_MS

HAND_COLORS = {"rock": (28, 0, 0), "scissors": (0, 28, 0), "paper": (0, 0, 28)}
LED_OFF = (0, 0, 0)
NOTE_FREQUENCIES = {
    "-": 0,
    "C4": 262,
    "E4": 330,
    "G4": 392,
    "A4": 440,
    "B4": 494,
    "C5": 523,
    "D5": 587,
    "E5": 659,
    "G5": 784,
    "C6": 1047,
}


def compile_melody(note_events):
    return tuple(
        (NOTE_FREQUENCIES[note_name], duration_ms)
        for note_name, duration_ms in note_events
    )


MELODIES = {
    "count_0": compile_melody((("C4", 140),)),
    "count_1": compile_melody((("E4", 140),)),
    "count_2": compile_melody((("G4", 140),)),
    "count_3": compile_melody((("C5", 180),)),
    "go": compile_melody((("G5", 70), ("-", 20), ("C6", 140))),
    "defense_window": compile_melody((("E5", 100), ("-", 40), ("G5", 100))),
    # ブドウ成立音をイメージした擬似音。短いドを6回鳴らす。
    "defense_ok": compile_melody((("C5", 70), ("-", 35)) * 6),
    "defense_fail": compile_melody(
        (("G4", 180), ("-", 30), ("E4", 180), ("-", 30), ("C4", 320))
    ),
    "win": compile_melody(
        (
            ("C5", 110),
            ("-", 25),
            ("E5", 110),
            ("-", 25),
            ("G5", 150),
            ("-", 25),
            ("C6", 320),
        )
    ),
    "draw": compile_melody((("D5", 150), ("-", 70), ("D5", 150))),
    "champion": compile_melody(
        (
            ("C5", 110),
            ("-", 20),
            ("E5", 110),
            ("-", 20),
            ("G5", 110),
            ("-", 20),
            ("C6", 220),
            ("-", 50),
            ("G5", 110),
            ("-", 20),
            ("C6", 420),
        )
    ),
    "defeat": compile_melody(
        (
            ("C5", 180),
            ("-", 30),
            ("B4", 180),
            ("-", 30),
            ("A4", 180),
            ("-", 30),
            ("G4", 300),
            ("-", 40),
            ("C4", 450),
        )
    ),
}


def rainbow_color(position):
    position %= 1536
    color_sector, channel_offset = divmod(position, 256)
    colors = (
        (255, channel_offset, 0),
        (255 - channel_offset, 255, 0),
        (0, 255, channel_offset),
        (0, 255 - channel_offset, 255),
        (channel_offset, 0, 255),
        (255, 0, 255 - channel_offset),
    )
    return tuple((channel_value // 10 for channel_value in colors[color_sector]))


def create_hand_led_pixels(game_state, player_number, led_count, own_led_start):
    if game_state["phase"] == "COUNTDOWN":
        countdown_stage = min(3, max(0, game_state.get("elapsed_ms", 0) // 750))
        return [
            (25, 0, 0) if led_index < (countdown_stage + 1) * 2 else LED_OFF
            for led_index in range(led_count)
        ]
    displayed_hands = (
        game_state.get("hands")
        if game_state["phase"] in ("DEFENSE", "DEFENSE_SAMPLE", "RESULT", "GAME_OVER")
        else game_state.get("live_hands")
    )
    displayed_hands = displayed_hands or (None, None)
    own_hand_color = HAND_COLORS.get(displayed_hands[player_number - 1], LED_OFF)
    opponent_hand_color = HAND_COLORS.get(displayed_hands[2 - player_number], LED_OFF)
    return [
        (
            own_hand_color
            if own_led_start <= led_index < own_led_start + led_count // 2
            else opponent_hand_color
        )
        for led_index in range(led_count)
    ]


def create_status_led_pixels(game_state, player_number, led_count, elapsed_ms):
    phase_name = game_state["phase"]
    winner_number = game_state.get("winner", 0)
    if phase_name in ("RESULT", "GAME_OVER"):
        if (
            phase_name == "RESULT"
            and game_state.get("defended")
            and player_number == winner_number
        ):
            return [
                rainbow_color(led_index * 1536 // led_count + elapsed_ms * 2)
                for led_index in range(led_count)
            ]
        if winner_number and player_number != winner_number:
            return [(28, 0, 0) if elapsed_ms % 500 < 250 else LED_OFF] * led_count
        if winner_number == player_number:
            if elapsed_ms < 160:
                return [(28, 28, 28)] * led_count
            if phase_name == "GAME_OVER":
                return [(25, 18, 0)] * led_count
            highlighted_led = elapsed_ms // 120 % led_count
            return [
                (22, 0, 28) if led_index == highlighted_led else (8, 0, 12)
                for led_index in range(led_count)
            ]
        return [(12, 12, 12)] * led_count
    if phase_name in ("DEFENSE", "DEFENSE_SAMPLE"):
        remaining_ms = (
            max(0, DEFENSE_DURATION_MS - game_state.get("elapsed_ms", 0))
            if phase_name == "DEFENSE"
            else 0
        )
        lit_led_count = (
            remaining_ms * led_count + DEFENSE_DURATION_MS - 1
        ) // DEFENSE_DURATION_MS
        return [
            (25, 10, 0) if led_index < lit_led_count else LED_OFF
            for led_index in range(led_count)
        ]
    color = (5, 2, 0) if phase_name == "WAIT" else LED_OFF
    return [color] * led_count


def select_result_melody(game_state, player_number):
    if game_state["phase"] == "GAME_OVER":
        return "champion" if game_state["winner"] == player_number else "defeat"
    winner_number = game_state.get("winner", 0)
    if not winner_number:
        return "draw"
    if player_number == winner_number:
        return "defense_ok" if game_state.get("defended") else "win"
    return "defense_fail"
