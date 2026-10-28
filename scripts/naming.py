"""Write Qingmo names into a font's name table, removing every inherited font-name record."""
from __future__ import annotations

from fontTools.ttLib import TTFont

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
    records = {
        0: copyright_text,
        1: fam["en"],
        2: subfamily,
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
    for nid in REPLACED_IDS:
        name.removeNames(nameID=nid)
    for nid, text in records.items():
        name.setName(text, nid, *WIN, EN)
    name.setName(fam["zh"], 1, *WIN, ZH_TW)
    name.setName(f"{fam['zh']} {zh_style}", 4, *WIN, ZH_TW)
    name.setName(fam["zh"], 16, *WIN, ZH_TW)
