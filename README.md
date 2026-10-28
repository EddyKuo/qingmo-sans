# 晴墨黑體 Qingmo Sans TC

繁體中文「明黑混合」內文字型：黑體的骨架與清晰度，加上明體的書寫筆勢。以 [SIL OFL 1.1](OFL.txt) 免費開源，衍生自 Source Han Sans TC。

> 狀態：**Phase 1**（PoC 字集 337 字）。設計規格見 [`docs/晴墨黑體 Design Spec v0.md`](docs/晴墨黑體%20Design%20Spec%20v0.md)，
> 研究與建置過程見 [`docs/研究與建置紀錄.md`](docs/研究與建置紀錄.md)。

## 建置

```bash
pip install -r requirements.txt
make all          # 下載並驗證母體 → 改造 → VF + 6 個 static + WOFF2 → QA
make test         # transform 單元測試（不需字型檔）
make smoke        # 用 Lora 可變字型（OFL）跑整條 pipeline，不需中文母體
```

Windows 沒有 `make` 時，依 Makefile 的順序直接執行 `python scripts/...`。

Pipeline：

```
fetch_base → subset(phase charset) → extract_masters(wght 250/400/900)
  → transform/{proportion, contrast, terminals, strokes, corners} → check_compat（點相容閘門）
  → build_vf（designspace + 母體 avar 曲線 + STAT + 命名）
  → build_static（6 個 instance、removeOverlaps、WOFF2）
  → qa/{regressions, check_names, coverage, outlines, gray}
```

## 產出

| 路徑 | 內容 |
| --- | --- |
| `fonts/variable/QingmoSansTC[wght].ttf` | 可變字型，wght 250–900，預設 400 |
| `fonts/static/QingmoSansTC-{ExtraLight,Light,Regular,Medium,Bold,Heavy}.ttf` | static instances（已移除 overlap） |
| `fonts/webfonts/*.woff2` | 上述全部的 WOFF2 |

## 風格改造（Phase 1）

只作用於 CJK 統一漢字；拉丁字母、標點、注音沿用母體字形。所有「改哪些點」的判斷在 Regular（wght 400）master 上做一次，再套到每個 master，確保點相容。

| Transform | Spec 參數 | 做法 |
| --- | --- | --- |
| `proportion` | 中宮 +3%、重心上移 ≤ 0.5%、寬高比 1.00 | 字面框內單調位移場；成對的豎畫 / 橫畫整筆平移，保持筆寬 |
| `contrast` | 豎 : 橫 = 100 : 82 | 偵測橫畫上下緣，兩緣各向內移動 |
| `terminals` | 起筆斜切 12°、收筆微收 8% | 只處理看得見的筆端（藏在其他筆畫裡的不算） |
| `strokes` | 點上尖下圓、捺短平台出鋒、撇出鋒漸細 | 依筆端朝向與形狀辨識點 / 撇 / 捺，套用模板；點的圓頭需加點 |
| `corners` | 外角軟化 r = 6 units，隨字重縮放 | 在所有 master 的同一批轉角插入二次曲線圓角 |

## QA 閘門

| 檢查 | 腳本 | Phase 1 結果 |
| --- | --- | --- |
| 跨 master 點相容 | `scripts/check_compat.py` | 963 / 963 |
| 不新增自交（masters 與中間字重） | `scripts/qa/regressions.py` | 通過 |
| `name` 不含 "Source" | `scripts/qa/check_names.py` | 通過 |
| 字集覆蓋 | `scripts/qa/coverage.py` | 337 / 337 |
| 破字 0（自交、方向、殘留 overlap） | `scripts/qa/outlines.py` | VF 與 6 個 static 通過 |
| 灰度一致（std ≤ 母體 × 1.05） | `scripts/qa/gray.py` | 比值 0.97–0.99 |
| fontbakery check-universal | `fontbakery`（選用） | 0 FAIL |
| 12 / 16 / 24 px 人工抽檢 | — | Claude 已目視校樣（見研究紀錄 §9），人工抽檢待執行 |

## 目錄

| 路徑 | 內容 |
| --- | --- |
| `config/spec.yaml` | 機器可讀的 Design Spec：命名、母體、軸、字重、風格參數、QA 門檻 |
| `config/charsets/` | 各階段字集 |
| `scripts/` | 建置腳本；`transform/` 是幾何改造，`qa/` 是驗收閘門 |
| `tests/` | `test_transforms.py` 單元測試、`smoke_test.py` 端到端測試 |
| `docs/` | Design Spec、研究與建置紀錄 |
| `CLAUDE.md` | Claude Code 工作指引（繁中回答、架構規則、閘門） |
| `CLEANROOM.md` | 貢獻前必讀的 clean-room 規範 |
| `FONTLOG.txt` | 版本與參數變更紀錄 |

## 授權

字型：SIL Open Font License 1.1。母體版權 Copyright 2014-2021 Adobe，Reserved Font Name 'Source'。
建置腳本：MIT（見 [`LICENSE-CODE`](LICENSE-CODE)）。
