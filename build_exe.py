"""デスクトップ版（.exe）を作る。

  py build_exe.py        → ..\\EVE-desktop\\EVE Tool\\EVE Tool.exe と、配る用の ..\\EVE-desktop\\EVE Tool.zip

事前準備: desktop.env に、デスクトップ版用の EVE のアプリの Client ID を書く（秘密鍵は書かない）。
  EVE Developers のアプリの Callback URL は http://localhost:8080/callback にする。

.exe に入れるのは、プログラム・画面（static）・キャッシュ（アイテム名・静的データなど、個人の情報が入らないもの）だけ。
キャラクターのログイン情報・保存したフィットなどの個人のデータは入れない。
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "EVE-desktop"
NAME = "EVE Tool"
WORK = OUT / "build"
# 一緒に配るファイル（.exe の中では paths.BASE_DIR に置かれ、初回起動時にデータの場所へコピーされる）
CACHES = ["item_catalog.json", "type_cache.json", "sde_data.json", "sde_missions.json", "fitting_cache.json", "wormhole_cache.json",
          "skill_cache.json", "gate_checks.json"]


def client_id():
    path = ROOT / "desktop.env"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "EVE_CLIENT_ID" and value.strip():
            return value.strip()
    return None


def main():
    if not client_id() and "--allow-missing" not in sys.argv:
        sys.exit("desktop.env に EVE_CLIENT_ID がありません（動作確認だけなら --allow-missing を付けてください）。")
    sep = ";"  # Windows の --add-data の区切り
    data = [f"{ROOT / 'static'}{sep}static", f"{ROOT / 'targets.txt'}{sep}."]
    data += [f"{ROOT / f}{sep}." for f in CACHES if (ROOT / f).exists()]
    if (ROOT / "desktop.env").exists():
        data.append(f"{ROOT / 'desktop.env'}{sep}.")
    cmd = [sys.executable, "-m", "PyInstaller", str(ROOT / "desktop.py"), "--name", NAME, "--windowed", "--onedir",
           "--noconfirm", "--clean", "--distpath", str(OUT), "--workpath", str(WORK), "--specpath", str(WORK)]
    for d in data:
        cmd += ["--add-data", d]
    subprocess.run(cmd, check=True, cwd=ROOT)
    # 配る用の zip（フォルダーごと。受け取った人は展開して EVE Tool.exe を起動する）
    archive = shutil.make_archive(str(OUT / NAME), "zip", OUT, NAME)
    shutil.rmtree(WORK, ignore_errors=True)
    print(f"\n作成しました: {OUT / NAME / (NAME + '.exe')}\n配る用: {archive}")


if __name__ == "__main__":
    main()
