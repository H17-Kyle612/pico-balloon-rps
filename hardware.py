"""センサー、LED、音、サーボの操作をまとめる。"""

import machine
import neopixel
import time
from config import (
    SOUND_PIN,
    SOUND_DUTY,
    LED_PIN,
    LED_COUNT,
    RING_PIN,
    RING_COUNT,
    OWN_LED_START,
    SERVO_PIN,
    ADC_PIN,
    I2C_SCL_PIN,
    I2C_SDA_PIN,
    SERVO_ENABLED,
    SERVO_START_DEG,
    SERVO_END_DEG,
    MAX_DAMAGE,
)
from rules import COLOR_TO_HAND, normalize_potentiometer, calculate_servo_angle
from effects import (
    MELODIES,
    LED_OFF,
    create_hand_led_pixels,
    create_status_led_pixels,
    select_result_melody,
)
from color_sensor import ColorSensor


def servo_duty_for_angle(angle_degrees):
    # 資料の0〜180度に対応するPWM値へ変換する。
    return int(1638 + angle_degrees / 180 * 6226)


class GameHardware:
    """各部品の入出力を管理し、ゲームの通信処理から分離する。"""

    def __init__(self, servo_enabled=SERVO_ENABLED):
        self.hand_leds = neopixel.NeoPixel(machine.Pin(LED_PIN), LED_COUNT)
        self.status_leds = neopixel.NeoPixel(machine.Pin(RING_PIN), RING_COUNT)
        self.sound_output = machine.PWM(machine.Pin(SOUND_PIN), freq=440, duty_u16=0)
        self.potentiometer_input = machine.ADC(ADC_PIN)
        self.color_sensor = ColorSensor(
            machine.I2C(1, scl=machine.Pin(I2C_SCL_PIN), sda=machine.Pin(I2C_SDA_PIN))
        )
        self.next_note_at_ms = None
        self.pending_notes = []
        self.phase_started_at_ms = time.ticks_ms()
        self.last_frame_at_ms = None
        self.countdown_stage = -1
        self.start_flash_ends_at_ms = None
        self.last_event = None
        self.last_detected_color = None
        self.color_stable_since_ms = time.ticks_ms()
        self.potentiometer_samples = []
        self.servo_output = None
        self.applied_failures = 0
        if servo_enabled:
            self.servo_output = machine.PWM(machine.Pin(SERVO_PIN), freq=50, duty_u16=0)
            self.servo_output.duty_u16(servo_duty_for_angle(SERVO_START_DEG))

    def read_inputs(self, current_time_ms, calibration):
        color = self.color_sensor.read_color()
        if color != self.last_detected_color:
            self.last_detected_color = color
            self.color_stable_since_ms = current_time_ms
        self.potentiometer_samples.append(self.potentiometer_input.read_u16() >> 4)
        if len(self.potentiometer_samples) > 5:
            self.potentiometer_samples.pop(0)
        normalized_value = normalize_potentiometer(
            sum(self.potentiometer_samples) / len(self.potentiometer_samples),
            calibration,
        )
        return {
            "color": color,
            "hand": COLOR_TO_HAND.get(color),
            "stable": color is not None
            and time.ticks_diff(current_time_ms, self.color_stable_since_ms) >= 600,
            "pot": round(normalized_value, 1),
        }

    def play_melody(self, melody_name, current_time_ms):
        self.pending_notes = list(MELODIES[melody_name])
        self.next_note_at_ms = current_time_ms
        self.sound_output.duty_u16(0)

    def update_audio(self, current_time_ms):
        if (
            self.next_note_at_ms is not None
            and time.ticks_diff(current_time_ms, self.next_note_at_ms) >= 0
        ):
            if self.pending_notes:
                frequency_hz, duration_ms = self.pending_notes.pop(0)
                self.sound_output.duty_u16(0)
                if frequency_hz:
                    self.sound_output.freq(frequency_hz)
                    self.sound_output.duty_u16(SOUND_DUTY)
                self.next_note_at_ms = time.ticks_add(current_time_ms, duration_ms)
            else:
                self.sound_output.duty_u16(0)
                self.next_note_at_ms = None

    def play_phase_melody(self, game_state, current_time_ms, player_number):
        if game_state["phase"] == "PARRY":
            self.play_melody("parry_window", current_time_ms)
        elif game_state["phase"] in ("RESULT", "GAME_OVER"):
            self.play_melody(
                select_result_melody(game_state, player_number), current_time_ms
            )

    def update_outputs(self, game_state, current_time_ms, player_number):
        current_event = (
            game_state["session"],
            game_state["round"],
            game_state["phase"],
        )
        phase_name = game_state["phase"]
        if current_event != self.last_event:
            previous_phase = self.last_event[2] if self.last_event else None
            self.last_event = current_event
            self.phase_started_at_ms = current_time_ms
            self.countdown_stage = -1
            self.pending_notes = []
            self.next_note_at_ms = None
            self.sound_output.duty_u16(0)
            if previous_phase == "COUNTDOWN" and phase_name in (
                "PARRY",
                "RESULT",
                "GAME_OVER",
            ):
                self.start_flash_ends_at_ms = time.ticks_add(current_time_ms, 250)
                self.play_melody("go", current_time_ms)
            else:
                self.play_phase_melody(game_state, current_time_ms, player_number)
            print("GAME", player_number, game_state)
        if phase_name == "COUNTDOWN":
            countdown_stage = min(3, max(0, game_state.get("elapsed_ms", 0) // 750))
            if countdown_stage != self.countdown_stage:
                self.countdown_stage = countdown_stage
                self.play_melody("count_" + str(countdown_stage), current_time_ms)
        # 累積失敗数を使い、同じ通信が再送されてもサーボを余分に進めない。
        failure_count = min(
            MAX_DAMAGE,
            max(
                self.applied_failures,
                game_state.get("damage", [0, 0])[player_number - 1],
            ),
        )
        if self.servo_output is not None and failure_count > self.applied_failures:
            target_angle = calculate_servo_angle(
                failure_count, SERVO_START_DEG, SERVO_END_DEG, MAX_DAMAGE
            )
            self.servo_output.duty_u16(servo_duty_for_angle(target_angle))
            print("SERVO", player_number, target_angle)
        self.applied_failures = failure_count
        if (
            self.last_frame_at_ms is None
            or time.ticks_diff(current_time_ms, self.last_frame_at_ms) >= 40
        ):
            self.last_frame_at_ms = current_time_ms
            hand_pixels = create_hand_led_pixels(
                game_state, player_number, LED_COUNT, OWN_LED_START
            )
            if (
                self.start_flash_ends_at_ms is not None
                and time.ticks_diff(current_time_ms, self.start_flash_ends_at_ms) < 0
            ):
                hand_pixels = [LED_OFF] * LED_COUNT
            elif self.start_flash_ends_at_ms is not None:
                self.start_flash_ends_at_ms = None
                self.play_phase_melody(game_state, current_time_ms, player_number)
            for led_index, pixel_color in enumerate(hand_pixels):
                self.hand_leds[led_index] = pixel_color
            self.hand_leds.write()
            for led_index, pixel_color in enumerate(
                create_status_led_pixels(
                    game_state,
                    player_number,
                    RING_COUNT,
                    time.ticks_diff(current_time_ms, self.phase_started_at_ms),
                )
            ):
                self.status_leds[led_index] = pixel_color
            self.status_leds.write()
        self.update_audio(current_time_ms)

    def shutdown(self):
        if self.servo_output is not None:
            self.servo_output.deinit()
            machine.Pin(SERVO_PIN, machine.Pin.OUT, value=0)
        self.sound_output.duty_u16(0)
        self.sound_output.deinit()
        machine.Pin(SOUND_PIN, machine.Pin.OUT, value=0)
        self.hand_leds.fill((0, 0, 0))
        self.hand_leds.write()
        self.status_leds.fill((0, 0, 0))
        self.status_leds.write()
        self.color_sensor.shutdown()
