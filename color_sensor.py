"""TCS34725の設定、測定、色判定をまとめる。"""

import struct
import time

_COMMAND_BIT = 0x80
_ENABLE = 0x00
_INTEGRATION_TIME = 0x01
_GAIN = 0x0F
_SENSOR_ID = 0x12
_STATUS = 0x13
_RED = 0x16
_GREEN = 0x18
_BLUE = 0x1A
_CLEAR = 0x14


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


def convert_sensor_rgb(sensor_data):
    """添付プログラムと同じRGB補正を使用する。"""
    red, green, blue, clear = sensor_data
    if clear == 0:
        return (0, 0, 0)
    return (
        min(255, int((red / clear) ** 2.5 * 255 * 0.7)),
        min(255, int((green / clear) ** 2.0 * 255 * 1.3)),
        min(255, int((blue / clear) ** 1.8 * 255 * 1.5)),
    )


class ColorSensor:
    """ゲームで必要な設定と読み取りだけを提供する。"""

    def __init__(self, communication_bus, address=0x29):
        self.communication_bus = communication_bus
        self.address = address
        sensor_id = self._read_byte(_SENSOR_ID)
        if sensor_id not in (0x44, 0x10, 0x4D):
            raise RuntimeError("Unexpected color sensor ID: " + hex(sensor_id))
        # 元の50ms設定と同じ20周期（48ms）、ゲイン16倍を使用する。
        self._write_byte(_INTEGRATION_TIME, 236)
        self._write_byte(_GAIN, 2)
        enable_value = self._read_byte(_ENABLE)
        self._write_byte(_ENABLE, enable_value | 1)
        time.sleep_ms(3)
        self._write_byte(_ENABLE, enable_value | 3)

    def _read_byte(self, register_address):
        return self.communication_bus.readfrom_mem(
            self.address, register_address | _COMMAND_BIT, 1
        )[0]

    def _write_byte(self, register_address, value):
        self.communication_bus.writeto_mem(
            self.address, register_address | _COMMAND_BIT, bytes((value,))
        )

    def read_color(self):
        # 新しい測定がないときは待たずに戻る。
        if not self._read_byte(_STATUS) & 1:
            return None
        readings = []
        for register_address in (_RED, _GREEN, _BLUE, _CLEAR):
            sensor_bytes = self.communication_bus.readfrom_mem(
                self.address, register_address | _COMMAND_BIT, 2
            )
            readings.append(struct.unpack("<H", sensor_bytes)[0])
        return classify_color(convert_sensor_rgb(readings))

    def shutdown(self):
        self._write_byte(_ENABLE, self._read_byte(_ENABLE) & ~3)
