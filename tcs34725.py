"""TCS34725のI2C通信だけを扱うドライバー。

赤・緑・青と明るさの生値を読み取る。ゲームの手判定はここでは行わない。
"""

from micropython import const
import time
import ustruct

_COMMAND_BIT = const(128)
_REGISTER_ENABLE = const(0)
_REGISTER_ATIME = const(1)
_REGISTER_CONTROL = const(15)
_REGISTER_SENSORID = const(18)
_REGISTER_STATUS = const(19)
_REGISTER_CDATA = const(20)
_REGISTER_RDATA = const(22)
_REGISTER_GDATA = const(24)
_REGISTER_BDATA = const(26)
_ENABLE_AEN = const(2)
_ENABLE_PON = const(1)
_GAINS = (1, 4, 16, 60)


class TCS34725:

    def __init__(self, i2c, address=41):
        self.i2c = i2c
        self.address = address
        self._active = False
        self.integration_time(2.4)
        sensor_id = self.sensor_id()
        if sensor_id not in (68, 16, 77):
            raise RuntimeError("wrong sensor id 0x{:x}".format(sensor_id))

    def _register8(self, register_address, setting_value=None):
        register_address |= _COMMAND_BIT
        if setting_value is None:
            return self.i2c.readfrom_mem(self.address, register_address, 1)[0]
        sensor_data = ustruct.pack("<B", setting_value)
        self.i2c.writeto_mem(self.address, register_address, sensor_data)

    def _register16(self, register_address):
        sensor_data = self.i2c.readfrom_mem(
            self.address, register_address | _COMMAND_BIT, 2
        )
        return ustruct.unpack("<H", sensor_data)[0]

    def active(self, setting_value=None):
        if setting_value is None:
            return self._active
        setting_value = bool(setting_value)
        if self._active == setting_value:
            return
        self._active = setting_value
        enable = self._register8(_REGISTER_ENABLE)
        if setting_value:
            self._register8(_REGISTER_ENABLE, enable | _ENABLE_PON)
            time.sleep_ms(3)
            self._register8(_REGISTER_ENABLE, enable | _ENABLE_PON | _ENABLE_AEN)
        else:
            self._register8(_REGISTER_ENABLE, enable & ~(_ENABLE_PON | _ENABLE_AEN))

    def sensor_id(self):
        return self._register8(_REGISTER_SENSORID)

    def integration_time(self, setting_value=None):
        if setting_value is None:
            return self._integration_time
        setting_value = min(614.4, max(2.4, setting_value))
        integration_cycles = int(setting_value / 2.4)
        self._integration_time = integration_cycles * 2.4
        return self._register8(_REGISTER_ATIME, 256 - integration_cycles)

    def gain(self, setting_value):
        if setting_value is None:
            return _GAINS[self._register8(_REGISTER_CONTROL)]
        if setting_value not in _GAINS:
            raise ValueError("gain must be 1, 4, 16 or 60")
        return self._register8(_REGISTER_CONTROL, _GAINS.index(setting_value))

    def is_data_ready(self):
        return bool(self._register8(_REGISTER_STATUS) & 1)

    def read_raw(self):
        previously_active = self.active()
        self.active(True)
        while not self.is_data_ready():
            time.sleep_ms(int(self._integration_time + 0.9))
        sensor_data = tuple(
            (
                self._register16(register_address)
                for register_address in (
                    _REGISTER_RDATA,
                    _REGISTER_GDATA,
                    _REGISTER_BDATA,
                    _REGISTER_CDATA,
                )
            )
        )
        self.active(previously_active)
        return sensor_data


def convert_sensor_rgb(sensor_data):
    """添付プログラムと同じ補正で、生値を0〜255のRGBに変換する。"""
    red, green, blue, clear = sensor_data
    if clear == 0:
        return (0, 0, 0)
    red = pow(red / clear, 2.5) * 255
    green = pow(green / clear, 2.0) * 255
    blue = pow(blue / clear, 1.8) * 255
    red = red * 0.7
    green = green * 1.3
    blue = blue * 1.5
    return (min(255, int(red)), min(255, int(green)), min(255, int(blue)))
