"""ゲーム専用Wi-FiとUDP通信。"""

import json
import network
import socket
import time
from config import (
    COLOR_TO_HAND,
    PLAYERS,
    GAME_SSID,
    GAME_PASSWORD,
    GAME_PORT,
    HOST_ADDRESS,
)

PHASES = (
    "WAIT",
    "READY",
    "COUNTDOWN",
    "DEFENSE",
    "DEFENSE_SAMPLE",
    "RESULT",
    "GAME_OVER",
)


def waiting_state():
    return {
        "session": "connecting",
        "round": 0,
        "token": 0,
        "phase": "WAIT",
        "damage": [0, 0],
    }


def is_valid_input_sample(sample):
    return (
        isinstance(sample, dict)
        and sample.get("color") in (None, "red", "green", "blue")
        and sample.get("hand") == COLOR_TO_HAND.get(sample.get("color"))
        and isinstance(sample.get("pot"), (int, float))
        and -100 <= sample["pot"] <= 100
    )


class GameConnection:
    def __init__(self, player_number, device_id):
        self.player_number = player_number
        self.device_id = device_id
        self.expected_device_id = next(
            identifier for identifier in PLAYERS if identifier != device_id
        )
        self.remote_peer = None
        self.peer_address = None
        self.latest_state = waiting_state()
        self.last_received_at_ms = None
        self.last_sent_at_ms = None
        self.last_diagnostic_at_ms = time.ticks_ms()
        network.WLAN(network.STA_IF).active(False)
        network.WLAN(network.AP_IF).active(False)
        interface_type = network.AP_IF if player_number == 1 else network.STA_IF
        self.wireless_interface = network.WLAN(interface_type)
        if player_number == 1:
            self.wireless_interface.config(essid=GAME_SSID, password=GAME_PASSWORD)
            self.wireless_interface.active(True)
            self.wireless_interface.ifconfig(
                (HOST_ADDRESS, "255.255.255.0", HOST_ADDRESS, HOST_ADDRESS)
            )
        else:
            self.wireless_interface.active(True)
            self.wireless_interface.connect(GAME_SSID, GAME_PASSWORD)
        self.communication_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.communication_socket.bind(("0.0.0.0", GAME_PORT))
        self.communication_socket.setblocking(False)

    def receive(self, current_time_ms, host_state):
        if time.ticks_diff(current_time_ms, self.last_diagnostic_at_ms) >= 3000:
            self.last_diagnostic_at_ms = current_time_ms
            print(
                "LINK",
                self.player_number,
                self.wireless_interface.status(),
                self.wireless_interface.ifconfig(),
                self.peer_address,
            )
            if (
                self.player_number == 2
                and not self.wireless_interface.isconnected()
                and self.wireless_interface.status() < 0
            ):
                self.wireless_interface.disconnect()
                self.wireless_interface.connect(GAME_SSID, GAME_PASSWORD)
        # 受信を最大8件に制限し、センサーや演出の更新を止めない。
        for _ in range(8):
            try:
                received_bytes, sender_address = self.communication_socket.recvfrom(
                    1200
                )
            except OSError as error:
                if error.args[0] in (11, 110):
                    break
                raise
            try:
                message = json.loads(received_bytes)
            except (ValueError, UnicodeError):
                continue
            if (
                not isinstance(message, dict)
                or message.get("uid") != self.expected_device_id
            ):
                continue
            if self.player_number == 1:
                if message.get("type") == "hello":
                    self.peer_address = sender_address
                elif (
                    message.get("type") == "sample"
                    and message.get("session") == host_state["session"]
                    and message.get("token") == host_state["token"]
                    and is_valid_input_sample(message.get("sample"))
                ):
                    self.remote_peer = {
                        "at": current_time_ms,
                        "token": message["token"],
                        "sample": message["sample"],
                    }
                    self.peer_address = sender_address
            elif sender_address[0] == HOST_ADDRESS and message.get("type") == "state":
                state = message.get("state")
                if not isinstance(state, dict) or state.get("phase") not in PHASES:
                    continue
                if (
                    self.latest_state["session"] == state.get("session")
                    and state.get("token", -1) < self.latest_state["token"]
                ):
                    continue
                self.latest_state = state
                self.last_received_at_ms = current_time_ms
        if (
            self.player_number == 2
            and self.latest_state["phase"] != "GAME_OVER"
            and (
                self.last_received_at_ms is None
                or time.ticks_diff(current_time_ms, self.last_received_at_ms) > 1000
            )
        ):
            self.latest_state = waiting_state()

    def send(self, current_time_ms, game_state, local_sample):
        if (
            self.last_sent_at_ms is not None
            and time.ticks_diff(current_time_ms, self.last_sent_at_ms) < 80
        ):
            return
        self.last_sent_at_ms = current_time_ms
        if self.player_number == 1:
            if not self.peer_address:
                return
            message = {"type": "state", "state": game_state}
            destination = self.peer_address
        else:
            if not self.wireless_interface.isconnected():
                return
            message = (
                {"type": "hello"}
                if self.latest_state["session"] == "connecting"
                else {
                    "type": "sample",
                    "session": game_state["session"],
                    "token": game_state["token"],
                    "sample": local_sample,
                }
            )
            destination = (HOST_ADDRESS, GAME_PORT)
        message["uid"] = self.device_id
        try:
            self.communication_socket.sendto(json.dumps(message).encode(), destination)
        except OSError:
            pass

    def close(self):
        self.communication_socket.close()
        self.wireless_interface.active(False)
