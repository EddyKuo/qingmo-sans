"""Write Qingmo names into a font's name table, removing every inherited font-name record.

Also finalizes the font as unhinted (prep dropout control + gasp) and syncs head.fontRevision
with the version string, which fontbakery checks.
"""
from __future__ import annotations

from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import ttProgram

WIN = (3, 1)
EN, ZH_TW = 0x409, 0x404

# Font-name records that must not carry the base's Reserved Font Name
REPLACED_IDS = (0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17, 21, 22, 25)


def set_names(font: TTFont, spec: dict, subfamily: str = "Regular", variable: bool = True) -> None:
    fam = spec["family"]
    zh_style = next((i["zh"] for i in spec["instances"] if i["name"] == subfamily), subfamily)
    ps_name = f"{fam['ps_prefix']}-{subfamily}"
    copyright_text = (
        "Copyright 2014-2021 Adobe (http://www.adobe.com/), with Reserved Font Name 'Source'. "
        "Copyright 2026 The Qingmo Sans Project Authors"
        f" ({fam['repo']})."
    )
    # static 非 RIBBI 字重（Light、Medium…）：legacy family 帶字重名、subfamily 為 Regular；
    # 完整的家族 / 字重放在 typographic names（ID 16 / 17）
    ribbi = variable or subfamily in ("Regular", "Bold")
    legacy_family = fam["en"] if ribbi else f"{fam['en']} {subfamily}"
    legacy_style = subfamily if ribbi else "Regular"
    records = {
        0: copyright_text,
        1: legacy_family,
        2: legacy_style,
        3: f"{fam['version']};{fam['vendor']};{ps_name}",
        4: f"{fam['en']} {subfamily}",
        5: f"Version {fam['version']}",
        6: ps_name,
        13: "This Font Software is licensed under the SIL Open Font License, Version 1.1.",
        14: "https://openfontlicense.org",
        16: fam["en"],
        17: subfamily,
    }
    if variable:
        records[25] = fam["ps_prefix"]

    name = font["name"]
    name.removeNames(platformID=1)          # Mac 平台名稱已淘汰，只保留 Windows
    for nid in REPLACED_IDS:
        name.removeNames(nameID=nid)
    font["head"].fontRevision = float(fam["version"])
    for nid, text in records.items():
        name.setName(text, nid, *WIN, EN)
    name.setName(fam["zh"] if ribbi else f"{fam['zh']} {zh_style}", 1, *WIN, ZH_TW)
    name.setName(f"{fam['zh']} {zh_style}", 4, *WIN, ZH_TW)
    name.setName(fam["zh"], 16, *WIN, ZH_TW)
    name.setName(zh_style, 17, *WIN, ZH_TW)


def mark_unhinted(font: TTFont) -> None:
    """母體無 hinting：加上 smart dropout control 的 prep 與全平滑 gasp，避免小字號破洞。"""
    prep = newTable("prep")
    prep.program = ttProgram.Program()
    prep.program.fromAssembly(["PUSHW[ ]", "511", "SCANCTRL[ ]", "PUSHB[ ]", "4", "SCANTYPE[ ]"])
    font["prep"] = prep
    gasp = newTable("gasp")
    gasp.gaspRange = {0xFFFF: 0x000F}
    font["gasp"] = gasp
    font["maxp"].maxStackElements = max(font["maxp"].maxStackElements, 2)
