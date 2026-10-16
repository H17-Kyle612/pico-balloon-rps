"""色センサーの読み取りと停止を、模擬I2Cで確認する。"""

import unittest
from unittest.mock import patch
from color_sensor import ColorSensor


class SensorBus:
    def __init__(self, red=0, green=0, blue=0, clear=0):
        self.registers = {
            0x00: 0x10,
            0x12: 0x4D,
            0x13: 1,
            0x16: red,
            0x18: green,
            0x1A: blue,
            0x14: clear,
        }

    def readfrom_mem(self, address, register_address, size):
        return self.registers.get(register_address & 0x7F, 0).to_bytes(size, "little")

    def writeto_mem(self, address, register_address, data):
        self.registers[register_address & 0x7F] = int.from_bytes(data, "little")


class ColorSensorTests(unittest.TestCase):
    def setUp(self):
        sleep_patch = patch("color_sensor.time.sleep_ms", create=True)
        sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def test_reads_each_color_and_preserves_enable_flags_on_shutdown(self):
        for readings, expected in (
            ((1000, 10, 10, 1000), "red"),
            ((10, 1000, 10, 1000), "green"),
            ((10, 10, 1000, 1000), "blue"),
        ):
            with self.subTest(color=expected):
                bus = SensorBus(*readings)
                sensor = ColorSensor(bus)
                self.assertEqual(sensor.read_color(), expected)
                sensor.shutdown()
                self.assertEqual(bus.registers[0x00], 0x10)

    def test_no_measurement_or_darkness_is_not_a_hand(self):
        bus = SensorBus()
        sensor = ColorSensor(bus)
        self.assertIsNone(sensor.read_color())
        bus.registers[0x13] = 0
        self.assertIsNone(sensor.read_color())

    def test_last_sample_is_kept_only_until_next_measurement(self):
        bus = SensorBus(1000, 10, 10, 1000)
        sensor = ColorSensor(bus)
        self.assertEqual(sensor.read_color(), "red")
        bus.registers[0x13] = 0
        self.assertEqual(sensor.read_color(), "red")
        bus.registers[0x13] = 1
        bus.registers[0x16], bus.registers[0x18] = 10, 1000
        self.assertEqual(sensor.read_color(), "green")
        bus.registers[0x14] = 0
        self.assertIsNone(sensor.read_color())

    def test_wrong_device_is_rejected(self):
        bus = SensorBus()
        bus.registers[0x12] = 0
        with self.assertRaises(RuntimeError):
            ColorSensor(bus)


if __name__ == "__main__":
    unittest.main()
