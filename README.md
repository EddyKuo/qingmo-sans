# 晴墨黑體 Qingmo Sans TC

繁體中文「明黑混合」內文字型：黑體的骨架與清晰度，加上明體的書寫筆勢。以 [SIL OFL 1.1](OFL.txt) 免費開源，衍生自 Source Han Sans TC。

> 狀態：**Phase 0**（規格與骨架）。目前尚無字形改造，所有 transform 為 identity stub。

## 建置

```bash
pip install -r requirements.txt
make smoke        # 下載 Lora 可變字型（OFL），驗證整條 pipeline（不需中文母體）
make smoke SMOKE_FONT=path/to/any-VF.ttf SMOKE_MASTERS=400,700
make all          # 需先在 config/spec.yaml 鎖定 base.url / base.sha256（Phase 1）
```

Pipeline：

```
fetch_base → subset(phase charset) → extract_masters(wght 200/400/900)
  → transform/{contrast, terminals, corners} → check_compat（點相容閘門）
  → build_vf（designspace + STAT + 命名）→ qa/{check_names, coverage}
```

## 目錄

| 路徑 | 內容 |
| --- | --- |
| `config/spec.yaml` | 機器可讀的 Design Spec：命名、母體、軸、字重、風格參數 |
| `config/charsets/` | 各階段字集 |
| `scripts/` | 建置腳本；`transform/` 是幾何改造，`qa/` 是驗收閘門 |
| `tests/smoke_test.py` | 端到端 smoke test |
| `CLEANROOM.md` | 貢獻前必讀的 clean-room 規範 |
| `FONTLOG.txt` | 版本與參數變更紀錄 |

## 授權

字型：SIL Open Font License 1.1。母體版權 Copyright 2014-2021 Adobe，Reserved Font Name 'Source'。
建置腳本：MIT（TODO：加入 `LICENSE-CODE`）。
