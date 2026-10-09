"""データファイルの置き場所。

ふだんはこのフォルダー。クラウドでは永続ディスクを環境変数 EVE_DATA_DIR に指定する
（コンテナを作り直すとアプリのフォルダーは消えるため）。
.exe（PyInstaller）で動くときは、各 PC のユーザーフォルダー（%LOCALAPPDATA%\\EVE Tool）に置く。
.exe を新しいものに置き換えても、データはそのまま残る。
"""

import json
import os
import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)  # .exe で動いている
APP_NAME = "EVE Tool"
# プログラムと一緒に配るファイル（static・targets.txt・キャッシュ）の場所
BASE_DIR = Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parent
_default_data = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME if FROZEN else BASE_DIR
DATA_DIR = Path(os.environ.get("EVE_DATA_DIR") or _default_data)

# 初回起動時、アプリと一緒に持ってきたデータ（キャッシュ・保存したフィットなど）を永続ディスクへ移す
# （.exe には個人のデータは入れず、キャッシュだけを入れる）
SEED_FILES = ["skill_cache.json", "type_cache.json", "item_catalog.json", "targets.json", "groups.json",
              "saved_fits.json", "fitting_cache.json", "structure_names.json", "market_watchlist.json",
              "wormhole_cache.json", "sde_data.json", "pi_layouts.json", "sig_log.json", "nes_offers.json",
              "character_skills.json", "gate_checks.json"]

# 版のあるキャッシュ: 一緒に配ったものの版が新しければ置き換える（.exe の更新で、作り直しを待たずに使えるように）
VERSIONED_FILES = ["sde_data.json"]


def _version(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("version", 0)
    except (OSError, ValueError, AttributeError):
        return 0


if DATA_DIR != BASE_DIR:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in VERSIONED_FILES:
        bundled, local = BASE_DIR / name, DATA_DIR / name
        if bundled.exists() and local.exists() and _version(bundled) > _version(local):
            shutil.copy2(bundled, local)
    for name in SEED_FILES:
        if not (DATA_DIR / name).exists() and (BASE_DIR / name).exists():
            shutil.copy2(BASE_DIR / name, DATA_DIR / name)
    if not (DATA_DIR / "skills").exists() and (BASE_DIR / "skills").is_dir():
        shutil.copytree(BASE_DIR / "skills", DATA_DIR / "skills")
