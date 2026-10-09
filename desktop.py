"""デスクトップ版（.exe）の起動: サーバーを裏で動かし、専用のウィンドウで開く。ウィンドウを閉じると終わる。

  py desktop.py       → .exe にする前の動作確認
  .exe の作り方は build_exe.py

データ（キャラクターのログイン情報・保存したフィットなど）は %LOCALAPPDATA%\\EVE Tool に置く（paths.py）。
.exe を新しいものに置き換えても、データはそのまま残る。
"""

import ctypes
import os
import sys
import threading
import time
import urllib.request

from i18n import tr
from paths import APP_NAME, DATA_DIR

LOG_FILE = DATA_DIR / "eve-tool.log"
WAIT_SECONDS = 60  # サーバーが応答するまで待つ時間


def message_box(text, title=APP_NAME):
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)  # 0x10 = エラーのアイコン


def responding(url):
    try:
        with urllib.request.urlopen(url + "api/sde/status", timeout=2) as res:
            return res.status == 200
    except OSError:
        return False


def main():
    # ウィンドウだけのアプリには画面の出力先が無いので、ログのファイルに書く
    if sys.stdout is None or getattr(sys, "frozen", False):
        log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - 終わるまで開いたまま
        sys.stdout = sys.stderr = log
    print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} 起動 ---")

    import webview  # noqa: PLC0415 - ログの出力先を決めてから読み込む

    import app  # noqa: PLC0415

    problem = app.prepare()
    if problem:
        message_box(tr("起動できませんでした。\n\n{0}", problem))
        return
    if app.port_in_use(app.PORT):
        if not responding(app.APP_URL):
            message_box(tr("ポート {0} がほかのアプリで使われているため、起動できません。\n（EVE ツールを py app.py で動かしている場合は、そちらを止めてください）", app.PORT))
            return
        # すでに起動している EVE ツールがあれば、そのウィンドウをもう 1 つ開く
    else:
        def run():
            try:
                app.serve_forever()
            except OSError as e:
                print(f"サーバーを起動できませんでした: {e}")
        threading.Thread(target=run, daemon=True).start()
        deadline = time.time() + WAIT_SECONDS
        while not responding(app.APP_URL):
            if time.time() > deadline:
                message_box(tr("起動に時間がかかりすぎています。ログを確認してください:\n{0}", LOG_FILE))
                return
            time.sleep(0.3)

    print(f"起動しました: {app.APP_URL}")
    webview.create_window("EVE ツール", app.APP_URL, width=1400, height=900, min_size=(400, 500))
    # ページの設定（選んだキャラクターなど）を次回も残すため、ブラウザーの保存領域をデータの場所に置く
    webview.start(private_mode=False, storage_path=str(DATA_DIR / "webview"))
    os._exit(0)  # ウィンドウを閉じたら、裏のサーバーごと終わる


if __name__ == "__main__":
    main()
