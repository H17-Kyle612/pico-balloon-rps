"""カラーセンサーの設定とゲーム用の色判定。"""

from tcs34725 import TCS34725, convert_sensor_rgb
from rules import classify_color


class ColorSensor:
    """レジスタ操作を隠し、赤・緑・青を返す。"""

    def __init__(self, communication_bus):
        self.sensor = TCS34725(communication_bus)
        self.sensor.integration_time(50)
        self.sensor.gain(16)
        self.sensor.active(True)

    def read_color(self):
        # 新しい測定がないときは手を確定しない。
        if not self.sensor.is_data_ready():
            return None
        return classify_color(convert_sensor_rgb(self.sensor.read_raw()))

    def shutdown(self):
        self.sensor.active(False)
