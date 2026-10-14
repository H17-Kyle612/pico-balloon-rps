"""1Pが管理する勝敗判定とラウンドの状態遷移。"""

import os
import time
from config import PARRY_MS, PARRY_TOLERANCE, MAX_DAMAGE
from rules import determine_winner, is_parry_successful


class GameReferee:

    def __init__(self):
        self.state = {
            "session": os.urandom(8).hex(),
            "round": 0,
            "token": 0,
            "phase": "WAIT",
            "damage": [0, 0],
        }
        self.phase_deadline_ms = None
        self.target_potentiometer_values = None
        self.final_local_potentiometer_value = None
        self.ready_since_ms = None

    def change_phase(self, phase_name, current_time_ms, duration_ms=None):
        self.state["phase"] = phase_name
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
                    for state_key in ("winner", "parried", "hands", "error"):
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
                self.state["parried"] = False
                self.change_phase("RESULT", current_time_ms, 2500)
            else:
                self.change_phase("PARRY", current_time_ms, PARRY_MS)
        elif (
            phase_name == "PARRY"
            and time.ticks_diff(current_time_ms, self.phase_deadline_ms) >= 0
        ):
            self.final_local_potentiometer_value = local_sample["pot"]
            self.change_phase("PARRY_SAMPLE", current_time_ms, 1000)
        elif phase_name == "PARRY_SAMPLE":
            if peer_matches_phase:
                winner_number = self.state["winner"]
                loser_number = 3 - winner_number
                normalized_value = (
                    self.final_local_potentiometer_value
                    if loser_number == 1
                    else remote_peer["sample"]["pot"]
                )
                target_value = self.target_potentiometer_values[winner_number - 1]
                parry_succeeded = is_parry_successful(
                    normalized_value, target_value, PARRY_TOLERANCE
                )
                self.state["parried"] = parry_succeeded
                self.state["error"] = round(abs(normalized_value - target_value), 1)
                if not parry_succeeded:
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

    def display_state(self, current_time_ms, local_sample, remote_peer):
        peer_is_fresh = (
            remote_peer is not None
            and time.ticks_diff(current_time_ms, remote_peer["at"]) < 400
        )
        self.state["live_hands"] = [
            local_sample["hand"],
            remote_peer["sample"]["hand"] if peer_is_fresh else None,
        ]
        duration_ms = {"COUNTDOWN": 3000, "PARRY": PARRY_MS}.get(self.state["phase"], 0)
        self.state["elapsed_ms"] = (
            max(
                0,
                duration_ms - time.ticks_diff(self.phase_deadline_ms, current_time_ms),
            )
            if self.phase_deadline_ms is not None
            else 0
        )
        return self.state
