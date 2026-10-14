"""入力、ゲーム進行、通信、出力を順番に実行する。"""

import machine
import time
import config
from hardware import GameHardware
from referee import GameReferee
from wireless import GameConnection


def run_game(maximum_runtime_seconds=None, servo_enabled=None):
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
        referee = GameReferee() if player_number == 1 else None
        while (
            maximum_runtime_seconds is None
            or time.ticks_diff(time.ticks_ms(), started_at_ms)
            < maximum_runtime_seconds * 1000
        ):
            current_time_ms = time.ticks_ms()
            local_sample = hardware.read_inputs(current_time_ms, player_settings["pot"])
            connection.receive(current_time_ms, referee.state if referee else None)
            if referee:
                referee.update(current_time_ms, local_sample, connection.remote_peer)
                game_state = referee.display_state(
                    current_time_ms, local_sample, connection.remote_peer
                )
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
