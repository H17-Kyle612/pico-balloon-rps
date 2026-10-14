"""分割モジュールをバックアップ付きで両Picoへ保存する。"""

import hashlib
import json
from pathlib import Path

SOURCE_DIRECTORY = Path(__file__).resolve().parent.parent
from serial_repl import Pico

DEVICE_FILES = (
    "config.py",
    "effects.py",
    "color_sensor.py",
    "hardware.py",
    "wireless.py",
    "game.py",
    "boot.py",
    "main.py",
)


def backup_file(device, filename, backup_directory):
    exists = (
        device.run("import os; print(" + repr(filename) + " in os.listdir())").strip()
        == "True"
    )
    if not exists:
        return
    destination = backup_directory / filename
    suffix = 1
    while destination.exists():
        destination = backup_directory / (filename + "." + str(suffix))
        suffix += 1
    device.run("_backup_file=open(" + repr(filename) + ",'rb')")
    try:
        with destination.open("wb") as output_file:
            while True:
                response = device.run("print(_backup_file.read(512).hex())").strip()
                if response in ("", "b''"):
                    break
                output_file.write(bytes.fromhex(response))
    finally:
        device.run("_backup_file.close()")


def upload_file(device, filename):
    content = (SOURCE_DIRECTORY / filename).read_bytes()
    temporary_name = "_upload_" + filename
    device.run("_upload_file=open(" + repr(temporary_name) + ",'wb')")
    try:
        for offset in range(0, len(content), 1024):
            chunk = content[offset : offset + 1024].hex()
            device.run(
                "import ubinascii; _upload_file.write(ubinascii.unhexlify("
                + repr(chunk)
                + "))"
            )
    finally:
        device.run("_upload_file.close()")
    response = device.run(
        "import hashlib,gc\ngc.collect()\n_digest=hashlib.sha256()\n_file=open("
        + repr(temporary_name)
        + ",'rb')\nwhile True:\n _chunk=_file.read(512)\n if not _chunk: break\n _digest.update(_chunk)\n_file.close()\nprint(_digest.digest().hex())"
    ).strip()
    if response != hashlib.sha256(content).hexdigest():
        raise RuntimeError("Checksum mismatch: " + filename)
    return temporary_name


def install():
    mapping_path = Path(__file__).resolve().parent / "devices.json"
    for player in json.loads(mapping_path.read_text()):
        device = Pico(player["port"])
        try:
            device_id = device.run(
                "import machine; print(machine.unique_id().hex())"
            ).strip()
            if device_id != player["uid"]:
                raise RuntimeError("Pico identity mismatch")
            backup_directory = SOURCE_DIRECTORY / "backups" / device_id
            backup_directory.mkdir(parents=True, exist_ok=True)
            for filename in DEVICE_FILES:
                backup_file(device, filename, backup_directory)
            # 全ファイルの照合が済んでから有効なファイル名へ切り替える。
            temporary_files = [
                upload_file(device, filename) for filename in DEVICE_FILES
            ]
            for temporary_name, filename in zip(temporary_files, DEVICE_FILES):
                device.run(
                    "os.rename(" + repr(temporary_name) + "," + repr(filename) + ")"
                )
            print(
                "INSTALLED",
                player["player"],
                device_id,
                len(DEVICE_FILES),
                "files",
                flush=True,
            )
        finally:
            device.close()


if __name__ == "__main__":
    install()
