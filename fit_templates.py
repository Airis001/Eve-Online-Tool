"""おすすめフィットの候補（定番の例）。

各フィットは validate_templates.py で、名前・スロット数・装着できるか・PG / CPU・キャリブレーションを検証してある。
role: drone（ドローン艦）/ missile（ミサイル艦）/ hauler（輸送）/ mining_ore（採掘: 鉱石）/ mining_gas（採掘: ガス）/ mining_ice（採掘: 氷）/
      turret（タレット艦）/ bomber（ステルスボマー）/ exploration（探査）/ salvage（サルベージ）/
      drone_mining（ドローン採掘）/ special_hauler（特殊輸送）
tier: 同じ役割の中での格（大きいほど上位。採掘・輸送の並び順に使う）
"""

ROLES = {
    "drone": "ドローン艦",
    "missile": "ミサイル艦",
    "turret": "タレット艦",
    "bomber": "ステルスボマー",
    "hauler": "輸送",
    "special_hauler": "特殊輸送",
    "mining_ore": "採掘（鉱石）",
    "mining_gas": "採掘（ガス）",
    "mining_ice": "採掘（氷）",
    "drone_mining": "ドローン採掘",
    "exploration": "探査",
    "salvage": "サルベージ",
    # PvP 向け
    "tackle": "タックル",
    "brawler": "ブローラー（近距離）",
    "kiter": "カイト（遠距離）",
    "logistics": "ロジ（遠隔回復）",
}

# 役割ごとの用途（PvE・PvP のページで分ける。None は戦闘以外＝おすすめフィットのページだけ）
PURPOSE = {
    "drone": "pve", "missile": "pve", "turret": "pve",
    "bomber": "pvp", "tackle": "pvp", "brawler": "pvp", "kiter": "pvp", "logistics": "pvp",
}

TEMPLATES = [
    # ---------- ドローン艦 ----------
    {"role": "drone", "tier": 1, "eft": """[Tristan, 定番 Tristan ドローン]
Drone Damage Amplifier II
Small Armor Repairer II
Damage Control II

1MN Afterburner II
Omnidirectional Tracking Link I
Drone Navigation Computer I

[Empty High slot]
[Empty High slot]
[Empty High slot]

Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I


Hobgoblin II x5
Warrior II x3
"""},
    {"role": "drone", "tier": 2, "eft": """[Algos, 定番 Algos ドローン]
Drone Damage Amplifier II
Drone Damage Amplifier II
Small Armor Repairer II

1MN Afterburner II
Omnidirectional Tracking Link I
Drone Navigation Computer I

[Empty High slot]

Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I


Hobgoblin II x5
Warrior II x5
"""},
    {"role": "drone", "tier": 3, "eft": """[Vexor, 定番 Vexor ドローン]
Drone Damage Amplifier II
Drone Damage Amplifier II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

10MN Afterburner II
Omnidirectional Tracking Link II
Cap Recharger II

[Empty High slot]

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I


Hammerhead II x5
Hobgoblin II x5
"""},
    {"role": "drone", "tier": 4, "eft": """[Vexor Navy Issue, 定番 Vexor Navy Issue ドローン]
Drone Damage Amplifier II
Drone Damage Amplifier II
Drone Damage Amplifier II
Medium Armor Repairer II
Damage Control II

10MN Afterburner II
Omnidirectional Tracking Link II
Cap Recharger II
Drone Navigation Computer II

[Empty High slot]

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I


Hammerhead II x5
Hobgoblin II x5
Ogre II x2
"""},
    {"role": "drone", "tier": 5, "eft": """[Myrmidon, 定番 Myrmidon ドローン]
Drone Damage Amplifier II
Drone Damage Amplifier II
Medium Armor Repairer II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

10MN Afterburner II
Omnidirectional Tracking Link II
Cap Recharger II
Cap Recharger II

[Empty High slot]

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Nanobot Accelerator I


Ogre II x5
Hammerhead II x5
Hobgoblin II x5
"""},
    {"role": "drone", "tier": 6, "eft": """[Ishtar, 定番 Ishtar ドローン]
Drone Damage Amplifier II
Drone Damage Amplifier II
Drone Damage Amplifier II
Damage Control II

10MN Afterburner II
Large Shield Extender II
Multispectrum Shield Hardener II
Omnidirectional Tracking Link II

[Empty High slot]

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Ogre II x5
Hammerhead II x5
Hobgoblin II x5
"""},
    {"role": "drone", "tier": 7, "eft": """[Gila, 定番 Gila ドローン＋ミサイル]
Drone Damage Amplifier II
Drone Damage Amplifier II
Damage Control II

10MN Afterburner II
Large Shield Extender II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II

Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Hammerhead II x2
Scourge Light Missile x2000
"""},
    {"role": "drone", "tier": 8, "eft": """[Dominix, 定番 Dominix ドローン]
Drone Damage Amplifier II
Drone Damage Amplifier II
Drone Damage Amplifier II
Large Armor Repairer II
Large Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

Omnidirectional Tracking Link II
Omnidirectional Tracking Link II
Cap Recharger II
Cap Recharger II
100MN Afterburner II

[Empty High slot]

Large Auxiliary Nano Pump I
Large Auxiliary Nano Pump I
Large Nanobot Accelerator I


Ogre II x5
Hammerhead II x5
Hobgoblin II x5
"""},

    # ---------- ミサイル艦 ----------
    {"role": "missile", "tier": 1, "eft": """[Kestrel, 定番 Kestrel ミサイル]
Ballistic Control System II
Ballistic Control System II

1MN Afterburner II
Medium F-S9 Regolith Compact Shield Extender

Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile

Small Core Defense Field Extender I
Small Core Defense Field Extender I
Small Core Defense Field Extender I


Scourge Light Missile x1000
"""},
    {"role": "missile", "tier": 2, "eft": """[Corax, 定番 Corax ミサイル]
Ballistic Control System II
Ballistic Control System II

1MN Afterburner II
Medium F-S9 Regolith Compact Shield Extender

Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile

Small Core Defense Field Extender I
Small Core Defense Field Extender I
Small Core Defense Field Extender I


Scourge Light Missile x1500
"""},
    {"role": "missile", "tier": 3, "eft": """[Caracal, 定番 Caracal ミサイル]
Ballistic Control System II
Ballistic Control System II
Damage Control II

10MN Afterburner II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II

Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Scourge Light Missile x2000
"""},
    {"role": "missile", "tier": 4, "eft": """[Drake, 定番 Drake ミサイル]
Ballistic Control System II
Ballistic Control System II
Ballistic Control System II
Damage Control II

10MN Afterburner II
Large Shield Extender II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II

Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Hobgoblin II x5
Scourge Heavy Missile x2000
"""},
    {"role": "missile", "tier": 5, "eft": """[Cerberus, 定番 Cerberus ミサイル]
Ballistic Control System II
Ballistic Control System II
Ballistic Control System II
Damage Control II

10MN Afterburner II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II
Missile Guidance Computer II

Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Scourge Heavy Missile x2000
"""},
    {"role": "missile", "tier": 6, "eft": """[Raven, 定番 Raven ミサイル]
Ballistic Control System II
Ballistic Control System II
Ballistic Control System II
Damage Control II

100MN Afterburner II
Large Shield Extender II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II
Missile Guidance Computer II

Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile

Large Core Defense Field Extender I
Large Core Defense Field Extender I
Large Core Defense Field Extender I


Hobgoblin II x5
Scourge Cruise Missile x2000
"""},

    # ---------- 輸送 ----------
    {"role": "hauler", "tier": 1, "eft": """[Badger, 定番 Badger 輸送]
Expanded Cargohold II
Expanded Cargohold II
Expanded Cargohold II

10MN Afterburner II
Medium Shield Extender II

[Empty High slot]

Medium Cargohold Optimization I
Medium Cargohold Optimization I
Medium Cargohold Optimization I
"""},
    {"role": "hauler", "tier": 1, "eft": """[Iteron Mark V, 定番 Iteron Mark V 輸送]
Expanded Cargohold II
Expanded Cargohold II
Expanded Cargohold II
Expanded Cargohold II
Expanded Cargohold II

10MN Afterburner II
Medium Shield Extender II

[Empty High slot]

Medium Cargohold Optimization I
Medium Cargohold Optimization I
Medium Cargohold Optimization I
"""},
    {"role": "hauler", "tier": 1, "eft": """[Mammoth, 定番 Mammoth 輸送]
Expanded Cargohold II
Expanded Cargohold II
Expanded Cargohold II
Expanded Cargohold II

10MN Afterburner II
Medium Shield Extender II

[Empty High slot]

Medium Cargohold Optimization I
Medium Cargohold Optimization I
Medium Cargohold Optimization I
"""},
    {"role": "hauler", "tier": 1, "eft": """[Bestower, 定番 Bestower 輸送]
Expanded Cargohold II
Expanded Cargohold II
Expanded Cargohold II
Expanded Cargohold II

10MN Afterburner II
Medium Shield Extender II

[Empty High slot]

Medium Cargohold Optimization I
Medium Cargohold Optimization I
Medium Cargohold Optimization I
"""},
    {"role": "hauler", "tier": 2, "eft": """[Crane, 定番 Crane 輸送（ブロッケードランナー）]
Expanded Cargohold II
Inertial Stabilizers II

10MN Afterburner II
Medium Shield Extender II
Multispectrum Shield Hardener II

Covert Ops Cloaking Device II

Medium Cargohold Optimization I
Medium Cargohold Optimization I
"""},
    {"role": "hauler", "tier": 3, "eft": """[Bustard, 定番 Bustard 輸送（ディープスペーストランスポート）]
Expanded Cargohold II
Expanded Cargohold II
Damage Control II

10MN Afterburner II
Medium Shield Extender II
Medium Shield Extender II
Multispectrum Shield Hardener II

[Empty High slot]

Medium Cargohold Optimization I
Medium Cargohold Optimization I
"""},

    # ---------- 採掘（鉱石） ----------
    {"role": "mining_ore", "tier": 1, "eft": """[Venture, 定番 Venture 鉱石]
Mining Laser Upgrade I

1MN Afterburner II
Small Shield Extender II

Miner II
Miner II
"""},
    {"role": "mining_ore", "tier": 2, "eft": """[Procurer, 定番 Procurer 鉱石]
Mining Laser Upgrade II
Damage Control II

Medium Shield Extender II
Medium Shield Extender II
Multispectrum Shield Hardener II

Strip Miner I
"""},
    {"role": "mining_ore", "tier": 3, "eft": """[Retriever, 定番 Retriever 鉱石]
Mining Laser Upgrade II
Mining Laser Upgrade II

Medium Shield Extender II
Multispectrum Shield Hardener II

Strip Miner I
Strip Miner I
"""},
    {"role": "mining_ore", "tier": 3, "eft": """[Covetor, 定番 Covetor 鉱石]
Mining Laser Upgrade II
Damage Control II

Medium Shield Extender II
Multispectrum Shield Hardener II

Strip Miner I
Strip Miner I
"""},
    {"role": "mining_ore", "tier": 4, "eft": """[Skiff, 定番 Skiff 鉱石]
Mining Laser Upgrade II
Damage Control II

Medium Shield Extender II
Medium Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II

Modulated Strip Miner II, Simple Asteroid Mining Crystal Type A II
"""},
    {"role": "mining_ore", "tier": 4, "eft": """[Mackinaw, 定番 Mackinaw 鉱石]
Mining Laser Upgrade II
Mining Laser Upgrade II

Medium Shield Extender II
Multispectrum Shield Hardener II

Modulated Strip Miner II, Simple Asteroid Mining Crystal Type A II
Modulated Strip Miner II, Simple Asteroid Mining Crystal Type A II
"""},
    {"role": "mining_ore", "tier": 5, "eft": """[Hulk, 定番 Hulk 鉱石]
Mining Laser Upgrade II
Mining Laser Upgrade II
Mining Laser Upgrade II

Medium Shield Extender II
Multispectrum Shield Hardener II

Modulated Strip Miner II, Simple Asteroid Mining Crystal Type A II
Modulated Strip Miner II, Simple Asteroid Mining Crystal Type A II
"""},

    # ---------- 採掘（ガス） ----------
    {"role": "mining_gas", "tier": 1, "eft": """[Venture, 定番 Venture ガス]
Inertial Stabilizers II

1MN Afterburner II
Small Shield Extender II

Gas Cloud Scoop II
Gas Cloud Scoop II
"""},
    {"role": "mining_gas", "tier": 2, "eft": """[Prospect, 定番 Prospect ガス]
Inertial Stabilizers II
Damage Control II

5MN Microwarpdrive II
Medium Shield Extender II

Gas Cloud Scoop II
Gas Cloud Scoop II
Covert Ops Cloaking Device II
"""},
    {"role": "mining_gas", "tier": 3, "eft": """[Retriever, 定番 Retriever ガス]
Damage Control II

Medium Shield Extender II
Multispectrum Shield Hardener II

Gas Cloud Harvester I
Gas Cloud Harvester I
"""},
    {"role": "mining_gas", "tier": 4, "eft": """[Hulk, 定番 Hulk ガス]
Damage Control II

Medium Shield Extender II
Multispectrum Shield Hardener II

Gas Cloud Harvester II
Gas Cloud Harvester II
"""},

    # ---------- MWD 版（アフターバーナーの代わりにマイクロワープドライブ） ----------
    # PG が足りない艦は、Compact 版の MWD や小さいシールドエクステンダーに替えてある。
    # T1 輸送艦（Iteron Mark V・Mammoth・Bestower）は PG が足りず 50MN MWD を積めないため作っていない。
    {"role": "drone", "tier": 1, "eft": """[Tristan, 定番 Tristan ドローン（MWD）]
Drone Damage Amplifier II
Small Armor Repairer II
Damage Control II

5MN Microwarpdrive II
Omnidirectional Tracking Link I
Drone Navigation Computer I

[Empty High slot]
[Empty High slot]
[Empty High slot]

Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I


Hobgoblin II x5
Warrior II x3
"""},
    {"role": "drone", "tier": 2, "eft": """[Algos, 定番 Algos ドローン（MWD）]
Drone Damage Amplifier II
Drone Damage Amplifier II
Small Armor Repairer II

5MN Microwarpdrive II
Omnidirectional Tracking Link I
Drone Navigation Computer I

[Empty High slot]

Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I


Hobgoblin II x5
Warrior II x5
"""},
    {"role": "drone", "tier": 3, "eft": """[Vexor, 定番 Vexor ドローン（MWD）]
Drone Damage Amplifier II
Drone Damage Amplifier II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

50MN Microwarpdrive II
Omnidirectional Tracking Link II
Cap Recharger II

[Empty High slot]

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I


Hammerhead II x5
Hobgoblin II x5
"""},
    {"role": "drone", "tier": 4, "eft": """[Vexor Navy Issue, 定番 Vexor Navy Issue ドローン（MWD）]
Drone Damage Amplifier II
Drone Damage Amplifier II
Drone Damage Amplifier II
Medium Armor Repairer II
Damage Control II

50MN Microwarpdrive II
Omnidirectional Tracking Link II
Cap Recharger II
Drone Navigation Computer II

[Empty High slot]

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I


Hammerhead II x5
Hobgoblin II x5
Ogre II x2
"""},
    {"role": "drone", "tier": 5, "eft": """[Myrmidon, 定番 Myrmidon ドローン（MWD）]
Drone Damage Amplifier II
Drone Damage Amplifier II
Medium Armor Repairer II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

50MN Microwarpdrive II
Omnidirectional Tracking Link II
Cap Recharger II
Cap Recharger II

[Empty High slot]

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Nanobot Accelerator I


Ogre II x5
Hammerhead II x5
Hobgoblin II x5
"""},
    {"role": "drone", "tier": 6, "eft": """[Ishtar, 定番 Ishtar ドローン（MWD）]
Drone Damage Amplifier II
Drone Damage Amplifier II
Drone Damage Amplifier II
Damage Control II

50MN Microwarpdrive II
Large Shield Extender II
Multispectrum Shield Hardener II
Omnidirectional Tracking Link II

[Empty High slot]

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Ogre II x5
Hammerhead II x5
Hobgoblin II x5
"""},
    {"role": "drone", "tier": 7, "eft": """[Gila, 定番 Gila ドローン＋ミサイル（MWD）]
Drone Damage Amplifier II
Drone Damage Amplifier II
Damage Control II

50MN Microwarpdrive II
Large Shield Extender II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II

Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Hammerhead II x2
Scourge Light Missile x2000
"""},
    {"role": "drone", "tier": 8, "eft": """[Dominix, 定番 Dominix ドローン（MWD）]
Drone Damage Amplifier II
Drone Damage Amplifier II
Drone Damage Amplifier II
Large Armor Repairer II
Large Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

Omnidirectional Tracking Link II
Omnidirectional Tracking Link II
Cap Recharger II
Cap Recharger II
500MN Microwarpdrive II

[Empty High slot]

Large Auxiliary Nano Pump I
Large Auxiliary Nano Pump I
Large Nanobot Accelerator I


Ogre II x5
Hammerhead II x5
Hobgoblin II x5
"""},
    {"role": "missile", "tier": 1, "eft": """[Kestrel, 定番 Kestrel ミサイル（MWD）]
Ballistic Control System II
Ballistic Control System II

5MN Y-T8 Compact Microwarpdrive
Small Shield Extender II

Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile

Small Core Defense Field Extender I
Small Core Defense Field Extender I
Small Core Defense Field Extender I


Scourge Light Missile x1000
"""},
    {"role": "missile", "tier": 2, "eft": """[Corax, 定番 Corax ミサイル（MWD）]
Ballistic Control System II
Ballistic Control System II

5MN Y-T8 Compact Microwarpdrive
Small Shield Extender II

Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile
Arbalest Compact Light Missile Launcher, Scourge Light Missile

Small Core Defense Field Extender I
Small Core Defense Field Extender I
Small Core Defense Field Extender I


Scourge Light Missile x1500
"""},
    {"role": "missile", "tier": 3, "eft": """[Caracal, 定番 Caracal ミサイル（MWD）]
Ballistic Control System II
Ballistic Control System II
Damage Control II

50MN Microwarpdrive II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II

Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Scourge Light Missile x2000
"""},
    {"role": "missile", "tier": 4, "eft": """[Drake, 定番 Drake ミサイル（MWD）]
Ballistic Control System II
Ballistic Control System II
Ballistic Control System II
Damage Control II

50MN Y-T8 Compact Microwarpdrive
Large Shield Extender II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II

Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Hobgoblin II x5
Scourge Heavy Missile x2000
"""},
    {"role": "missile", "tier": 5, "eft": """[Cerberus, 定番 Cerberus ミサイル（MWD）]
Ballistic Control System II
Ballistic Control System II
Ballistic Control System II
Damage Control II

50MN Microwarpdrive II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II
Missile Guidance Computer II

Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile
Heavy Missile Launcher II, Scourge Heavy Missile

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Scourge Heavy Missile x2000
"""},
    {"role": "missile", "tier": 6, "eft": """[Raven, 定番 Raven ミサイル（MWD）]
Ballistic Control System II
Ballistic Control System II
Ballistic Control System II
Damage Control II

500MN Microwarpdrive II
Large Shield Extender II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II
Missile Guidance Computer II

Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile
Cruise Missile Launcher II, Scourge Cruise Missile

Large Core Defense Field Extender I
Large Core Defense Field Extender I
Large Core Defense Field Extender I


Hobgoblin II x5
Scourge Cruise Missile x2000
"""},
    {"role": "hauler", "tier": 1, "eft": """[Badger, 定番 Badger 輸送（MWD）]
Expanded Cargohold II
Expanded Cargohold II
Expanded Cargohold II

50MN Microwarpdrive II
Medium Shield Extender II

[Empty High slot]

Medium Cargohold Optimization I
Medium Cargohold Optimization I
Medium Cargohold Optimization I
"""},
    {"role": "hauler", "tier": 2, "eft": """[Crane, 定番 Crane 輸送（ブロッケードランナー）（MWD）]
Expanded Cargohold II
Inertial Stabilizers II

50MN Y-T8 Compact Microwarpdrive
Small Shield Extender II
Multispectrum Shield Hardener II

Covert Ops Cloaking Device II

Medium Cargohold Optimization I
Medium Cargohold Optimization I
"""},
    {"role": "hauler", "tier": 3, "eft": """[Bustard, 定番 Bustard 輸送（ディープスペーストランスポート）（MWD）]
Expanded Cargohold II
Expanded Cargohold II
Damage Control II

50MN Microwarpdrive II
Medium Shield Extender II
Medium Shield Extender II
Multispectrum Shield Hardener II

[Empty High slot]

Medium Cargohold Optimization I
Medium Cargohold Optimization I
"""},
    {"role": "mining_ore", "tier": 1, "eft": """[Venture, 定番 Venture 鉱石（MWD）]
Mining Laser Upgrade I

5MN Microwarpdrive II
Small Shield Extender II

Miner II
Miner II
"""},
    {"role": "mining_gas", "tier": 1, "eft": """[Venture, 定番 Venture ガス（MWD）]
Inertial Stabilizers II

5MN Microwarpdrive II
Small Shield Extender II

Gas Cloud Scoop II
Gas Cloud Scoop II
"""},

    # ---------- 採掘（氷） ----------
    {"role": "mining_ice", "tier": 1, "eft": """[Endurance, 定番 Endurance 氷]
Ice Harvester Upgrade II
Damage Control II

1MN Afterburner II
Medium Shield Extender II

Ice Mining Laser II
"""},
    {"role": "mining_ice", "tier": 2, "eft": """[Procurer, 定番 Procurer 氷]
Ice Harvester Upgrade II
Damage Control II

Medium Shield Extender II
Medium Shield Extender II
Multispectrum Shield Hardener II

Ice Harvester II
"""},
    {"role": "mining_ice", "tier": 3, "eft": """[Retriever, 定番 Retriever 氷]
Ice Harvester Upgrade II
Damage Control II

Medium Shield Extender II
Multispectrum Shield Hardener II

Ice Harvester II
Ice Harvester II
"""},
    {"role": "mining_ice", "tier": 3, "eft": """[Covetor, 定番 Covetor 氷]
Ice Harvester Upgrade II
Damage Control II

Medium Shield Extender II
Multispectrum Shield Hardener II

Ice Harvester II
Ice Harvester II
"""},
    {"role": "mining_ice", "tier": 4, "eft": """[Skiff, 定番 Skiff 氷]
Ice Harvester Upgrade II
Damage Control II

Medium Shield Extender II
Medium Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II

Ice Harvester II
"""},
    {"role": "mining_ice", "tier": 4, "eft": """[Mackinaw, 定番 Mackinaw 氷]
Ice Harvester Upgrade II
Ice Harvester Upgrade II

Medium Shield Extender II
Multispectrum Shield Hardener II

Ice Harvester II
Ice Harvester II
"""},
    {"role": "mining_ice", "tier": 5, "eft": """[Hulk, 定番 Hulk 氷]
Ice Harvester Upgrade II
Ice Harvester Upgrade II
Ice Harvester Upgrade II

Medium Shield Extender II
Multispectrum Shield Hardener II

Ice Harvester II
Ice Harvester II
"""},

    # ---------- タレット艦 ----------
    {"role": "turret", "tier": 1, "eft": """[Incursus, 定番 Incursus タレット]
Magnetic Field Stabilizer II
Small Armor Repairer II
Damage Control II

1MN Afterburner II
Cap Recharger II

Light Neutron Blaster II, Antimatter Charge S
Light Neutron Blaster II, Antimatter Charge S
Light Neutron Blaster II, Antimatter Charge S

Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I


Antimatter Charge S x1000
"""},
    {"role": "turret", "tier": 1, "eft": """[Rifter, 定番 Rifter タレット]
Gyrostabilizer II
Small Armor Repairer II
Damage Control II

1MN Afterburner II
Cap Recharger II

200mm AutoCannon II, EMP S
200mm AutoCannon II, EMP S
200mm AutoCannon II, EMP S

Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I


EMP S x1000
"""},
    {"role": "turret", "tier": 1, "eft": """[Punisher, 定番 Punisher タレット]
Heat Sink II
Small Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

1MN Afterburner II
Cap Recharger II

Small Focused Pulse Laser II, Multifrequency S
Small Focused Pulse Laser II, Multifrequency S

Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
"""},
    {"role": "turret", "tier": 2, "eft": """[Catalyst, 定番 Catalyst タレット]
Magnetic Field Stabilizer II
Magnetic Field Stabilizer II
Damage Control II

1MN Afterburner II
Small Shield Extender II

Light Electron Blaster II, Antimatter Charge S
Light Electron Blaster II, Antimatter Charge S
Light Electron Blaster II, Antimatter Charge S
Light Electron Blaster II, Antimatter Charge S
Light Electron Blaster II, Antimatter Charge S
Light Electron Blaster II, Antimatter Charge S
Light Electron Blaster II, Antimatter Charge S

Small Core Defense Field Extender I
Small Core Defense Field Extender I
Small Core Defense Field Extender I


Antimatter Charge S x2000
"""},
    {"role": "turret", "tier": 3, "eft": """[Thorax, 定番 Thorax タレット]
Magnetic Field Stabilizer II
Magnetic Field Stabilizer II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

10MN Afterburner II
Cap Recharger II
Cap Recharger II

Heavy Ion Blaster II, Antimatter Charge M
Heavy Ion Blaster II, Antimatter Charge M
Heavy Ion Blaster II, Antimatter Charge M
Heavy Ion Blaster II, Antimatter Charge M
Heavy Ion Blaster II, Antimatter Charge M

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I


Hobgoblin II x5
Antimatter Charge M x1000
"""},
    {"role": "turret", "tier": 3, "eft": """[Rupture, 定番 Rupture タレット]
Gyrostabilizer II
Gyrostabilizer II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

10MN Afterburner II
Cap Recharger II
Cap Recharger II

425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I


Warrior II x5
EMP M x1000
"""},
    {"role": "turret", "tier": 3, "eft": """[Omen, 定番 Omen タレット]
Heat Sink II
Heat Sink II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

10MN Afterburner II
Cap Recharger II
Cap Recharger II

Focused Medium Pulse Laser II, Multifrequency M
Focused Medium Pulse Laser II, Multifrequency M
Focused Medium Pulse Laser II, Multifrequency M
Focused Medium Pulse Laser II, Multifrequency M
Focused Medium Pulse Laser II, Multifrequency M

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
"""},
    {"role": "turret", "tier": 4, "eft": """[Brutix, 定番 Brutix タレット]
Magnetic Field Stabilizer II
Magnetic Field Stabilizer II
Magnetic Field Stabilizer II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

10MN Afterburner II
Cap Recharger II
Cap Recharger II
Cap Recharger II

Heavy Ion Blaster II, Antimatter Charge M
Heavy Ion Blaster II, Antimatter Charge M
Heavy Ion Blaster II, Antimatter Charge M
Heavy Ion Blaster II, Antimatter Charge M
Heavy Ion Blaster II, Antimatter Charge M
Heavy Ion Blaster II, Antimatter Charge M

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Nanobot Accelerator I


Hobgoblin II x5
Antimatter Charge M x2000
"""},
    {"role": "turret", "tier": 4, "eft": """[Hurricane, 定番 Hurricane タレット]
Gyrostabilizer II
Gyrostabilizer II
Gyrostabilizer II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

10MN Afterburner II
Cap Recharger II
Cap Recharger II
Cap Recharger II

425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I


Warrior II x5
EMP M x2000
"""},
    {"role": "turret", "tier": 4, "eft": """[Harbinger, 定番 Harbinger タレット]
Heat Sink II
Heat Sink II
Heat Sink II
Medium Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II

10MN Afterburner II
Cap Recharger II
Cap Recharger II

Focused Medium Pulse Laser II, Multifrequency M
Focused Medium Pulse Laser II, Multifrequency M
Focused Medium Pulse Laser II, Multifrequency M
Focused Medium Pulse Laser II, Multifrequency M
Focused Medium Pulse Laser II, Multifrequency M
Focused Medium Pulse Laser II, Multifrequency M

Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I
Medium Auxiliary Nano Pump I


Acolyte II x5
"""},
    {"role": "turret", "tier": 5, "eft": """[Megathron, 定番 Megathron タレット]
Magnetic Field Stabilizer II
Magnetic Field Stabilizer II
Magnetic Field Stabilizer II
Large Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II
Multispectrum Energized Membrane II

100MN Afterburner II
Cap Recharger II
Cap Recharger II
Cap Recharger II

Neutron Blaster Cannon II, Antimatter Charge L
Neutron Blaster Cannon II, Antimatter Charge L
Neutron Blaster Cannon II, Antimatter Charge L
Neutron Blaster Cannon II, Antimatter Charge L
Neutron Blaster Cannon II, Antimatter Charge L
Neutron Blaster Cannon II, Antimatter Charge L
Neutron Blaster Cannon II, Antimatter Charge L

Large Auxiliary Nano Pump I
Large Auxiliary Nano Pump I
Large Auxiliary Nano Pump I


Hammerhead II x5
Antimatter Charge L x2000
"""},
    {"role": "turret", "tier": 5, "eft": """[Maelstrom, 定番 Maelstrom タレット]
Gyrostabilizer II
Gyrostabilizer II
Gyrostabilizer II
Damage Control II
Power Diagnostic System II

100MN Afterburner II
Large Shield Extender II
Large Shield Extender II
Multispectrum Shield Hardener II
Multispectrum Shield Hardener II
Cap Recharger II

800mm Repeating Cannon II, EMP L
800mm Repeating Cannon II, EMP L
800mm Repeating Cannon II, EMP L
800mm Repeating Cannon II, EMP L
800mm Repeating Cannon II, EMP L
800mm Repeating Cannon II, EMP L

Large Core Defense Field Extender I
Large Core Defense Field Extender I
Large Core Defense Field Extender I


EMP L x2000
"""},
    {"role": "turret", "tier": 5, "eft": """[Apocalypse, 定番 Apocalypse タレット]
Heat Sink II
Heat Sink II
Heat Sink II
Large Armor Repairer II
Damage Control II
Multispectrum Energized Membrane II
Multispectrum Energized Membrane II

100MN Afterburner II
Cap Recharger II
Cap Recharger II
Cap Recharger II

Mega Pulse Laser II, Multifrequency L
Mega Pulse Laser II, Multifrequency L
Mega Pulse Laser II, Multifrequency L
Mega Pulse Laser II, Multifrequency L
Mega Pulse Laser II, Multifrequency L
Mega Pulse Laser II, Multifrequency L
Mega Pulse Laser II, Multifrequency L
Mega Pulse Laser II, Multifrequency L

Large Auxiliary Nano Pump I
Large Auxiliary Nano Pump I
Large Auxiliary Nano Pump I
"""},

    # ---------- ステルスボマー ----------
    {"role": "bomber", "tier": 1, "eft": """[Manticore, 定番 Manticore ボマー]
Ballistic Control System II
Ballistic Control System II

5MN Microwarpdrive II
Target Painter II
Sensor Booster II

Torpedo Launcher II, Scourge Torpedo
Torpedo Launcher II, Scourge Torpedo
Torpedo Launcher II, Scourge Torpedo
Covert Ops Cloaking Device II


Scourge Torpedo x300
"""},
    {"role": "bomber", "tier": 1, "eft": """[Purifier, 定番 Purifier ボマー]
Ballistic Control System II
Ballistic Control System II

5MN Microwarpdrive II
Target Painter II
Sensor Booster II

Torpedo Launcher II, Mjolnir Torpedo
Torpedo Launcher II, Mjolnir Torpedo
Torpedo Launcher II, Mjolnir Torpedo
Covert Ops Cloaking Device II


Mjolnir Torpedo x300
"""},
    {"role": "bomber", "tier": 1, "eft": """[Nemesis, 定番 Nemesis ボマー]
Ballistic Control System II
Ballistic Control System II

5MN Microwarpdrive II
Target Painter II
Sensor Booster II

Torpedo Launcher II, Inferno Torpedo
Torpedo Launcher II, Inferno Torpedo
Torpedo Launcher II, Inferno Torpedo
Covert Ops Cloaking Device II


Inferno Torpedo x300
"""},
    {"role": "bomber", "tier": 1, "eft": """[Hound, 定番 Hound ボマー]
Ballistic Control System II
Ballistic Control System II

5MN Microwarpdrive II
Target Painter II
Sensor Booster II

Torpedo Launcher II, Nova Torpedo
Torpedo Launcher II, Nova Torpedo
Torpedo Launcher II, Nova Torpedo
Covert Ops Cloaking Device II


Nova Torpedo x300
"""},

    # ---------- 探査 ----------
    {"role": "exploration", "tier": 1, "eft": """[Heron, 定番 Heron 探査]
Inertial Stabilizers II

1MN Afterburner II
Data Analyzer II
Relic Analyzer II
Cap Recharger II

Core Probe Launcher II
Prototype Cloaking Device I

Small Memetic Algorithm Bank I
Small Emission Scope Sharpener I
"""},
    {"role": "exploration", "tier": 1, "eft": """[Imicus, 定番 Imicus 探査]
Inertial Stabilizers II

1MN Afterburner II
Data Analyzer II
Relic Analyzer II
Cap Recharger II

Core Probe Launcher II
Prototype Cloaking Device I

Small Memetic Algorithm Bank I
Small Emission Scope Sharpener I
"""},
    {"role": "exploration", "tier": 1, "eft": """[Magnate, 定番 Magnate 探査]
Inertial Stabilizers II

1MN Afterburner II
Data Analyzer II
Relic Analyzer II

Core Probe Launcher II
Prototype Cloaking Device I

Small Memetic Algorithm Bank I
Small Emission Scope Sharpener I
"""},
    {"role": "exploration", "tier": 1, "eft": """[Probe, 定番 Probe 探査]
Inertial Stabilizers II

1MN Afterburner II
Data Analyzer II
Relic Analyzer II
Cap Recharger II

Core Probe Launcher II
Prototype Cloaking Device I

Small Memetic Algorithm Bank I
Small Emission Scope Sharpener I
"""},
    {"role": "exploration", "tier": 2, "eft": """[Buzzard, 定番 Buzzard 探査]
Inertial Stabilizers II

1MN Afterburner II
Data Analyzer II
Relic Analyzer II
Cap Recharger II

Core Probe Launcher II
Covert Ops Cloaking Device II

Small Memetic Algorithm Bank I
Small Emission Scope Sharpener I
"""},
    {"role": "exploration", "tier": 3, "eft": """[Astero, 定番 Astero 探査]
Damage Control II
Small Armor Repairer II
Multispectrum Energized Membrane II

1MN Afterburner II
Data Analyzer II
Relic Analyzer II

Core Probe Launcher II
Covert Ops Cloaking Device II

Small Memetic Algorithm Bank I


Hobgoblin II x5
"""},

    # ---------- サルベージ ----------
    {"role": "salvage", "tier": 1, "eft": """[Cormorant, 定番 Cormorant サルベージ]
Expanded Cargohold II
Expanded Cargohold II

1MN Afterburner II
Cap Recharger II

Salvager II
Salvager II
Salvager II
Salvager II
Small Tractor Beam I
Small Tractor Beam I
Small Tractor Beam I
Small Tractor Beam I

Small Salvage Tackle I
Small Salvage Tackle I
Small Salvage Tackle I
"""},
    {"role": "salvage", "tier": 1, "eft": """[Catalyst, 定番 Catalyst サルベージ]
Expanded Cargohold II
Expanded Cargohold II

1MN Afterburner II
Cap Recharger II

Salvager II
Salvager II
Salvager II
Salvager II
Small Tractor Beam I
Small Tractor Beam I
Small Tractor Beam I
Small Tractor Beam I

Small Salvage Tackle I
Small Salvage Tackle I
Small Salvage Tackle I
"""},
    {"role": "salvage", "tier": 2, "eft": """[Noctis, 定番 Noctis サルベージ]
Expanded Cargohold II
Expanded Cargohold II
Inertial Stabilizers II

10MN Afterburner II
Medium Shield Extender II

Salvager II
Salvager II
Salvager II
Salvager II
Small Tractor Beam II
Small Tractor Beam II
Small Tractor Beam II
Small Tractor Beam II

Medium Salvage Tackle I
Medium Salvage Tackle I
Medium Salvage Tackle I
"""},

    # ---------- ドローン採掘 ----------
    {"role": "drone_mining", "tier": 1, "eft": """[Vexor, 定番 Vexor ドローン採掘]
Damage Control II
Medium Armor Repairer II
Multispectrum Energized Membrane II

10MN Afterburner II
Cap Recharger II
Drone Navigation Computer II

[Empty High slot]

Medium Drone Mining Augmentor I
Medium Drone Mining Augmentor I
Medium Drone Mining Augmentor I


Mining Drone II x5
Hobgoblin II x5
"""},
    {"role": "drone_mining", "tier": 1, "eft": """[Arbitrator, 定番 Arbitrator ドローン採掘]
Damage Control II
Medium Armor Repairer II
Multispectrum Energized Membrane II

10MN Afterburner II
Cap Recharger II
Drone Navigation Computer II

[Empty High slot]

Medium Drone Mining Augmentor I
Medium Drone Mining Augmentor I
Medium Drone Mining Augmentor I


Mining Drone II x5
Hobgoblin II x5
"""},

    # ---------- 特殊輸送 ----------
    {"role": "special_hauler", "tier": 1, "eft": """[Epithal, 定番 Epithal 特殊輸送（PI）]
Inertial Stabilizers II
Damage Control II

10MN Afterburner II
Medium Shield Extender II
Multispectrum Shield Hardener II

[Empty High slot]
"""},
    {"role": "special_hauler", "tier": 1, "eft": """[Kryos, 定番 Kryos 特殊輸送（鉱物・氷）]
Inertial Stabilizers II
Damage Control II

10MN Afterburner II
Medium Shield Extender II
Multispectrum Shield Hardener II

[Empty High slot]
"""},
    {"role": "special_hauler", "tier": 1, "eft": """[Hoarder, 定番 Hoarder 特殊輸送（ガス・弾薬）]
Inertial Stabilizers II
Damage Control II

10MN Afterburner II
Medium Shield Extender II
Multispectrum Shield Hardener II

[Empty High slot]
"""},
    {"role": "special_hauler", "tier": 1, "eft": """[Miasmos, 定番 Miasmos 特殊輸送（鉱石）]
Inertial Stabilizers II
Damage Control II

10MN Afterburner II
Medium Shield Extender II
Multispectrum Shield Hardener II

[Empty High slot]
"""},

    # ========== ここから PvP 向け ==========
    # ---------- タックル（相手のワープを止めて逃がさない。速さ重視） ----------
    {"role": "tackle", "tier": 1, "eft": """[Atron, PvP Atron タックル]
Overdrive Injector System II
Nanofiber Internal Structure II
Damage Control II

5MN Microwarpdrive II
Warp Disruptor II
Stasis Webifier II

Light Neutron Blaster II, Null S
Light Neutron Blaster II, Null S

Small Polycarbon Engine Housing I
Small Polycarbon Engine Housing I
Small Polycarbon Engine Housing I


Null S x500
"""},
    {"role": "tackle", "tier": 1, "eft": """[Slasher, PvP Slasher タックル]
Overdrive Injector System II
Damage Control II

5MN Microwarpdrive II
Warp Disruptor II
Stasis Webifier II
Small Shield Extender II

125mm Gatling AutoCannon II, Barrage S
125mm Gatling AutoCannon II, Barrage S
125mm Gatling AutoCannon II, Barrage S

Small Core Defense Field Extender I
Small Polycarbon Engine Housing I
Small Polycarbon Engine Housing I


Barrage S x1000
"""},
    {"role": "tackle", "tier": 1, "eft": """[Executioner, PvP Executioner タックル]
Overdrive Injector System II
Damage Control II
Nanofiber Internal Structure II

5MN Microwarpdrive II
Warp Disruptor II

Small Focused Pulse Laser II, Scorch S
Small Focused Pulse Laser II, Scorch S
Small Focused Pulse Laser II, Scorch S

Small Polycarbon Engine Housing I
Small Polycarbon Engine Housing I
Small Polycarbon Engine Housing I


Scorch S x2
"""},
    {"role": "tackle", "tier": 1, "eft": """[Condor, PvP Condor タックル]
Overdrive Injector System II
Nanofiber Internal Structure II

5MN Microwarpdrive II
Warp Disruptor II
Stasis Webifier II
Small Shield Extender II

Light Missile Launcher II, Scourge Light Missile
Light Missile Launcher II, Scourge Light Missile
Light Missile Launcher II, Scourge Light Missile

Small Polycarbon Engine Housing I
Small Polycarbon Engine Housing I
Small Polycarbon Engine Housing I


Scourge Light Missile x500
"""},
    {"role": "tackle", "tier": 2, "eft": """[Stiletto, PvP Stiletto インターセプター]
Nanofiber Internal Structure II
Overdrive Injector System II

5MN Microwarpdrive II
Warp Disruptor II
Warp Scrambler II
Small Shield Extender II

125mm Gatling AutoCannon II, Barrage S
125mm Gatling AutoCannon II, Barrage S

Small Polycarbon Engine Housing I
Small Polycarbon Engine Housing I


Barrage S x1000
"""},
    {"role": "tackle", "tier": 2, "eft": """[Ares, PvP Ares インターセプター]
Nanofiber Internal Structure II
Overdrive Injector System II
Damage Control II

5MN Microwarpdrive II
Warp Disruptor II
Warp Scrambler II

Light Ion Blaster II, Null S
Light Ion Blaster II, Null S

Small Polycarbon Engine Housing I
Small Polycarbon Engine Housing I


Null S x500
"""},

    # ---------- ブローラー（近距離で殴り合う。スクランブラー・ウェブで捕まえる） ----------
    {"role": "brawler", "tier": 1, "eft": """[Incursus, PvP Incursus ブローラー]
Small Ancillary Armor Repairer, Nanite Repair Paste
Magnetic Field Stabilizer II
Damage Control II

1MN Afterburner II
Initiated Compact Warp Scrambler
Fleeting Compact Stasis Webifier

Light Neutron Blaster II, Void S
Light Neutron Blaster II, Void S
Light Neutron Blaster II, Void S

Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
Small Nanobot Accelerator I


Void S x500
Nanite Repair Paste x50
"""},
    {"role": "brawler", "tier": 1, "eft": """[Rifter, PvP Rifter ブローラー]
Small Ancillary Armor Repairer, Nanite Repair Paste
Gyrostabilizer II
Damage Control II

1MN Afterburner II
Initiated Compact Warp Scrambler
Fleeting Compact Stasis Webifier

200mm AutoCannon II, EMP S
200mm AutoCannon II, EMP S
200mm AutoCannon II, EMP S

Small Auxiliary Nano Pump I
Small Auxiliary Nano Pump I
Small Nanobot Accelerator I


EMP S x1000
Nanite Repair Paste x50
"""},
    {"role": "brawler", "tier": 1, "eft": """[Merlin, PvP Merlin ブローラー]
Magnetic Field Stabilizer II
Damage Control II

1MN Afterburner II
Initiated Compact Warp Scrambler
Fleeting Compact Stasis Webifier
Small Shield Extender II

Light Ion Blaster II, Void S
Light Ion Blaster II, Void S
Light Ion Blaster II, Void S

Small Core Defense Field Extender I
Small Core Defense Field Extender I
Small Core Defense Field Extender I


Void S x500
"""},
    {"role": "brawler", "tier": 1, "eft": """[Punisher, PvP Punisher ブローラー]
Small Ancillary Armor Repairer, Nanite Repair Paste
Heat Sink II
Damage Control II
200mm Steel Plates II

1MN Afterburner II
Warp Scrambler II

Small Focused Pulse Laser II, Multifrequency S
Small Focused Pulse Laser II, Multifrequency S

Small Trimark Armor Pump I
Small Trimark Armor Pump I
Small Trimark Armor Pump I


Multifrequency S x2
Nanite Repair Paste x50
"""},
    {"role": "brawler", "tier": 2, "eft": """[Catalyst, PvP Catalyst ブローラー]
Magnetic Field Stabilizer II
Magnetic Field Stabilizer II
Damage Control II

1MN Afterburner II
Initiated Compact Warp Scrambler

Light Ion Blaster II, Void S
Light Ion Blaster II, Void S
Light Ion Blaster II, Void S
Light Ion Blaster II, Void S
Light Ion Blaster II, Void S
Light Ion Blaster II, Void S
Light Ion Blaster II, Void S

Small Core Defense Field Extender I
Small Core Defense Field Extender I
Small Core Defense Field Extender I


Void S x1000
"""},
    {"role": "brawler", "tier": 3, "eft": """[Thorax, PvP Thorax ブローラー]
800mm Steel Plates II
Damage Control II
Magnetic Field Stabilizer II
Magnetic Field Stabilizer II
Multispectrum Energized Membrane II

50MN Microwarpdrive II
Warp Scrambler II
Stasis Webifier II

Heavy Electron Blaster II, Void M
Heavy Electron Blaster II, Void M
Heavy Electron Blaster II, Void M
Heavy Electron Blaster II, Void M
Heavy Electron Blaster II, Void M

Medium Trimark Armor Pump I
Medium Trimark Armor Pump I
Medium Trimark Armor Pump I

Hobgoblin II x5

Void M x1000
"""},
    {"role": "brawler", "tier": 3, "eft": """[Rupture, PvP Rupture ブローラー]
800mm Steel Plates II
Damage Control II
Gyrostabilizer II
Gyrostabilizer II
Multispectrum Energized Membrane II

50MN Microwarpdrive II
Warp Scrambler II
Stasis Webifier II

425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M
425mm AutoCannon II, EMP M

Medium Trimark Armor Pump I
Medium Trimark Armor Pump I
Medium Trimark Armor Pump I

Warrior II x5

EMP M x1000
"""},

    # ---------- カイト（距離を取って戦う。ディスラプター・MWD） ----------
    {"role": "kiter", "tier": 1, "eft": """[Kestrel, PvP Kestrel カイト]
Ballistic Control System II
Nanofiber Internal Structure II

5MN Microwarpdrive II
Warp Disruptor II
Small Azeotropic Restrained Shield Extender
Small Azeotropic Restrained Shield Extender

Light Missile Launcher II, Scourge Light Missile
Light Missile Launcher II, Scourge Light Missile
Light Missile Launcher II, Scourge Light Missile
Light Missile Launcher II, Scourge Light Missile

Small Core Defense Field Extender I
Small Core Defense Field Extender I
Small Core Defense Field Extender I


Scourge Light Missile x1000
"""},
    {"role": "kiter", "tier": 2, "eft": """[Corax, PvP Corax カイト]
Ballistic Control System II
Nanofiber Internal Structure II

5MN Microwarpdrive II
Warp Disruptor II
Small Azeotropic Restrained Shield Extender

Light Missile Launcher II, Scourge Light Missile
Light Missile Launcher II, Scourge Light Missile
Light Missile Launcher II, Scourge Light Missile
Light Missile Launcher II, Scourge Light Missile
Light Missile Launcher II, Scourge Light Missile

Small Core Defense Field Extender I
Small Core Defense Field Extender I
Small Core Defense Field Extender I


Scourge Light Missile x1500
"""},
    {"role": "kiter", "tier": 3, "eft": """[Caracal, PvP Caracal カイト]
Ballistic Control System II
Ballistic Control System II
Nanofiber Internal Structure II

50MN Microwarpdrive II
Warp Disruptor II
Medium Shield Extender II
Medium Shield Extender II
Multispectrum Shield Hardener II

Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile
Rapid Light Missile Launcher II, Scourge Light Missile

Medium Core Defense Field Extender I
Medium Core Defense Field Extender I
Medium Core Defense Field Extender I


Scourge Light Missile x2000
"""},

    # ---------- ロジ（味方の装甲・シールドを遠隔で回復） ----------
    {"role": "logistics", "tier": 1, "eft": """[Navitas, PvP Navitas ロジ]
Damage Control II
200mm Steel Plates II
Capacitor Power Relay II

1MN Afterburner II
Cap Recharger II
Cap Recharger II

Small Remote Armor Repairer II
Small Remote Armor Repairer II

Small Capacitor Control Circuit I
Small Capacitor Control Circuit I
Small Capacitor Control Circuit I
"""},
    {"role": "logistics", "tier": 3, "eft": """[Exequror, PvP Exequror ロジ]
Damage Control II
800mm Steel Plates II
Multispectrum Energized Membrane II
Capacitor Power Relay II

10MN Afterburner II
Cap Recharger II
Cap Recharger II

Medium Remote Armor Repairer II
Medium Remote Armor Repairer II
Medium Remote Armor Repairer II

Medium Capacitor Control Circuit I
Medium Capacitor Control Circuit I
Medium Capacitor Control Circuit I
"""},
    {"role": "logistics", "tier": 3, "eft": """[Osprey, PvP Osprey ロジ]
Damage Control II
Power Diagnostic System II

10MN Afterburner II
Medium Shield Extender II
Multispectrum Shield Hardener II
Cap Recharger II
Cap Recharger II

Medium Remote Shield Booster II
Medium Remote Shield Booster II
Medium Remote Shield Booster II

Medium Capacitor Control Circuit I
Medium Capacitor Control Circuit I
Medium Capacitor Control Circuit I
"""},
    {"role": "logistics", "tier": 3, "eft": """[Scythe, PvP Scythe ロジ]
Damage Control II
Power Diagnostic System II

10MN Afterburner II
Medium Shield Extender II
Multispectrum Shield Hardener II
Cap Recharger II

Medium Remote Shield Booster II
Medium Remote Shield Booster II
Medium Remote Shield Booster II

Medium Capacitor Control Circuit I
Medium Capacitor Control Circuit I
Medium Capacitor Control Circuit I
"""},
]
