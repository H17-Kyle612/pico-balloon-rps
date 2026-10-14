"""Pico 2台のUSBシリアルログを読み取り専用で表示する。"""

import argparse
import json
from pathlib import Path
from datetime import datetime
import sys
import threading
import time

import serial


def watch_port(player_name, port_name, stop_event):
    serial_connection = serial.Serial(port=None, baudrate=115200, timeout=0.2)
    # Picoへ割り込み文字やコマンドを送らず、受信だけを行う。
    serial_connection.dtr = False
    serial_connection.rts = False
    serial_connection.port = port_name

    try:
        serial_connection.open()
        print("[{}] ログ受信中: {}".format(player_name, port_name), flush=True)
        while not stop_event.is_set():
            received_line = serial_connection.readline()
            if received_line:
                timestamp = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
                decoded_line = received_line.decode("utf-8", errors="replace").rstrip()
                print(
                    "{} [{}] {}".format(timestamp, player_name, decoded_line),
                    flush=True,
                )
    except serial.SerialException as error:
        print("[{}] USB接続エラー: {}".format(player_name, error), file=sys.stderr)
    finally:
        if serial_connection.is_open:
            serial_connection.close()


def main():
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument(
        "ports",
        nargs="*",
        help="監視するUSBポート。省略時は登録済みの1P・2P両方。",
    )
    arguments = argument_parser.parse_args()
    selected_ports = (
        [("Pico", port_name) for port_name in arguments.ports]
        if arguments.ports
        else [
            (str(player["player"]) + "P", player["port"])
            for player in json.loads(
                (
                    Path(__file__).resolve().parent / "devices.json"
                ).read_text()
            )
        ]
    )
    stop_event = threading.Event()
    watchers = [
        threading.Thread(
            target=watch_port,
            args=(player_name, port_name, stop_event),
            daemon=True,
        )
        for player_name, port_name in selected_ports
    ]

    for watcher in watchers:
        watcher.start()
    try:
        while any(watcher.is_alive() for watcher in watchers):
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nログ監視を終了します。", flush=True)
    finally:
        stop_event.set()
        for watcher in watchers:
            watcher.join(timeout=1)


if __name__ == "__main__":
    main()
