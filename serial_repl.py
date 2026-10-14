"""Picoへの保存に使用するUSBシリアルREPL。接続時に実行を停止する。"""
import time
import serial


class Pico:
    def __init__(self, port):
        self.connection = serial.Serial(port, 115200, timeout=0.2, write_timeout=5)
        try:
            self.connection.write(b'\r\x03\x03\x02')
            time.sleep(0.3)
            self.connection.reset_input_buffer()
            self.connection.write(b'\x01')
            response = self.read_until(b'>', 5)
            if b'raw REPL' not in response:
                raise RuntimeError(repr(response))
        except Exception:
            self.connection.close()
            raise

    def read_until(self, marker, timeout):
        deadline = time.monotonic() + timeout
        received_bytes = b''
        while time.monotonic() < deadline:
            received_bytes += self.connection.read(1)
            if received_bytes.endswith(marker):
                return received_bytes
        raise TimeoutError(repr(received_bytes))

    def run(self, code, timeout=20):
        encoded_code = code.encode()
        for offset in range(0, len(encoded_code), 128):
            self.connection.write(encoded_code[offset:offset + 128])
            time.sleep(0.01)
        self.connection.write(b'\x04')
        if self.connection.read(2) != b'OK':
            raise RuntimeError('No raw REPL acknowledgement')
        output = self.read_until(b'\x04', timeout)[:-1]
        error = self.read_until(b'\x04', timeout)[:-1]
        self.read_until(b'>', timeout)
        if error:
            raise RuntimeError(error.decode())
        return output.decode()

    def close(self):
        try:
            self.connection.write(b'\x02')
        finally:
            self.connection.close()
