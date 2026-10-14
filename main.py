# 単独起動。ゲーム開始時にサーボを0度へ移動する。
import time
import game

# USBから起動を中断できるよう、開始前に待機する。
time.sleep(5)
game.run_game()
