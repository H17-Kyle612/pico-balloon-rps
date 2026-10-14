"""ゲームのコア。準備、じゃんけん、防御、結果、終了をこのファイルで制御する。"""

import os
import time
import config
from config import COLOR_TO_HAND, DEFENSE_DURATION_MS, DEFENSE_TOLERANCE, MAX_DAMAGE


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


class GameController:
    """1Pで両者の手、目標値、失敗数とラウンドの状態を管理する。"""

    def __init__(self):
        self.state = {
            "session": os.urandom(8).hex(),
            "round": 0,
            "token": 0,
            "phase": "WAIT",
            "damage": [0, 0],
            "elapsed_ms": 0,
        }
        self.phase_deadline_ms = None
        self.target_potentiometer_values = None
        self.final_local_potentiometer_value = None
        self.ready_since_ms = None

    def change_phase(self, phase_name, current_time_ms, duration_ms=None):
        self.state["phase"] = phase_name
        self.state["elapsed_ms"] = 0
        self.state["token"] += 1
        self.phase_deadline_ms = (
            time.ticks_add(current_time_ms, duration_ms)
            if duration_ms is not None
            else None
        )
        self.ready_since_ms = None

    def update(self, current_time_ms, local_sample, remote_peer):
        peer_is_fresh = (
            remote_peer is not None
            and time.ticks_diff(current_time_ms, remote_peer["at"]) < 400
        )
        self.state["live_hands"] = [
            local_sample["hand"],
            remote_peer["sample"]["hand"] if peer_is_fresh else None,
        ]
        duration_ms = {"COUNTDOWN": 3000, "DEFENSE": DEFENSE_DURATION_MS}.get(
            self.state["phase"], 0
        )
        self.state["elapsed_ms"] = (
            max(
                0,
                duration_ms - time.ticks_diff(self.phase_deadline_ms, current_time_ms),
            )
            if self.phase_deadline_ms is not None
            else 0
        )
        peer_matches_phase = (
            peer_is_fresh and remote_peer["token"] == self.state["token"]
        )
        phase_name = self.state["phase"]
        if phase_name == "GAME_OVER":
            return
        if not peer_is_fresh:
            if phase_name != "WAIT":
                self.change_phase("WAIT", current_time_ms)
            return
        if phase_name == "WAIT":
            self.change_phase("READY", current_time_ms)
        elif phase_name == "READY":
            if (
                peer_matches_phase
                and local_sample["stable"]
                and remote_peer["sample"]["stable"]
            ):
                if self.ready_since_ms is None:
                    self.ready_since_ms = current_time_ms
                if time.ticks_diff(current_time_ms, self.ready_since_ms) >= 1000:
                    self.target_potentiometer_values = (
                        local_sample["pot"],
                        remote_peer["sample"]["pot"],
                    )
                    self.state["round"] += 1
                    for state_key in ("winner", "defended", "hands", "error"):
                        self.state.pop(state_key, None)
                    self.change_phase("COUNTDOWN", current_time_ms, 3000)
            else:
                self.ready_since_ms = None
        elif (
            phase_name == "COUNTDOWN"
            and time.ticks_diff(current_time_ms, self.phase_deadline_ms) >= 0
        ):
            if (
                not peer_matches_phase
                or not local_sample["stable"]
                or (not remote_peer["sample"]["stable"])
            ):
                self.change_phase("READY", current_time_ms)
                return
            detected_hands = (local_sample["hand"], remote_peer["sample"]["hand"])
            self.state["hands"] = detected_hands
            self.state["winner"] = determine_winner(*detected_hands)
            if not self.state["winner"]:
                self.state["defended"] = False
                self.change_phase("RESULT", current_time_ms, 2500)
            else:
                self.change_phase("DEFENSE", current_time_ms, DEFENSE_DURATION_MS)
        elif (
            phase_name == "DEFENSE"
            and time.ticks_diff(current_time_ms, self.phase_deadline_ms) >= 0
        ):
            self.final_local_potentiometer_value = local_sample["pot"]
            self.change_phase("DEFENSE_SAMPLE", current_time_ms, 1000)
        elif phase_name == "DEFENSE_SAMPLE":
            if peer_matches_phase:
                winner_number = self.state["winner"]
                loser_number = 3 - winner_number
                normalized_value = (
                    self.final_local_potentiometer_value
                    if loser_number == 1
                    else remote_peer["sample"]["pot"]
                )
                target_value = self.target_potentiometer_values[winner_number - 1]
                # 防御成功ならサーボを進めず、失敗したときだけ失敗数を増やす。
                defense_succeeded = (
                    abs(normalized_value - target_value) <= DEFENSE_TOLERANCE
                )
                self.state["defended"] = defense_succeeded
                self.state["error"] = round(abs(normalized_value - target_value), 1)
                if not defense_succeeded:
                    self.state["damage"][loser_number - 1] += 1
                if self.state["damage"][loser_number - 1] >= MAX_DAMAGE:
                    self.state["loser"] = loser_number
                    self.change_phase("GAME_OVER", current_time_ms)
                else:
                    self.change_phase("RESULT", current_time_ms, 2500)
            elif time.ticks_diff(current_time_ms, self.phase_deadline_ms) >= 0:
                self.change_phase("WAIT", current_time_ms)
        elif (
            phase_name == "RESULT"
            and time.ticks_diff(current_time_ms, self.phase_deadline_ms) >= 0
        ):
            self.change_phase("READY", current_time_ms)


def run_game(maximum_runtime_seconds=None, servo_enabled=None):
    # ハードウェア依存のコードは実機起動時に読み込む。
    import machine
    from hardware import GameHardware
    from wireless import GameConnection

    device_id = machine.unique_id().hex()
    player_settings = config.PLAYERS.get(device_id)
    if player_settings is None:
        raise RuntimeError("Unregistered Pico " + device_id)
    player_number = player_settings["player"]
    hardware = None
    connection = None
    started_at_ms = time.ticks_ms()
    try:
        connection = GameConnection(player_number, device_id)
        hardware = GameHardware(
            config.SERVO_ENABLED if servo_enabled is None else servo_enabled
        )
        controller = GameController() if player_number == 1 else None
        while (
            maximum_runtime_seconds is None
            or time.ticks_diff(time.ticks_ms(), started_at_ms)
            < maximum_runtime_seconds * 1000
        ):
            current_time_ms = time.ticks_ms()
            local_sample = hardware.read_inputs(current_time_ms, player_settings["pot"])
            connection.receive(
                current_time_ms, controller.state if controller else None
            )
            if controller:
                controller.update(current_time_ms, local_sample, connection.remote_peer)
                game_state = controller.state
            else:
                game_state = connection.latest_state
            hardware.update_outputs(game_state, current_time_ms, player_number)
            connection.send(current_time_ms, game_state, local_sample)
            time.sleep_ms(20)
    finally:
        if hardware:
            hardware.shutdown()
        if connection:
            connection.close()


if __name__ == "__main__":
    run_game()
