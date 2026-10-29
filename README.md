# 晴墨黑體 Qingmo Sans TC

繁體中文「明黑混合」內文字型：黑體的骨架與清晰度，加上明體的書寫筆勢。以 [SIL OFL 1.1](OFL.txt) 免費開源，衍生自 Source Han Sans TC。

> 狀態：**全字集 0.101**（母體全部 17,760 個漢字，含 Big5 13,064 字）。設計規格見 [`docs/晴墨黑體 Design Spec v0.md`](docs/晴墨黑體%20Design%20Spec%20v0.md)，
> 研究與建置過程見 [`docs/研究與建置紀錄.md`](docs/研究與建置紀錄.md)。

## 建置

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make all PY=.venv/bin/python          # 下載並驗證母體 → 改造 → VF + 6 個 static + WOFF2 → QA（全字集約 30 分鐘）
make all PY=.venv/bin/python CHARSET=phase1   # 只建 549 字的快速版本
make webfonts PY=.venv/bin/python     # 網頁用 unicode-range 切片 WOFF2 + CSS（約 10 秒）
make release                          # 成品搬到 release-font/，並刪除中間檔
make test PY=.venv/bin/python         # transform 單元測試（不需字型檔）
make smoke PY=.venv/bin/python        # 用 Lora 可變字型（OFL）跑整條 pipeline，不需中文母體
```

Windows 沒有 `make` 時，依 Makefile 的順序直接執行 `.venv/Scripts/python scripts/...`。

Pipeline：

```
fetch_base → subset(phase charset) → extract_masters(wght 250/400/900)
  → transform/{proportion, contrast, terminals, strokes, corners} → check_compat（點相容閘門）
  → build_vf（designspace + 母體 avar 曲線 + STAT + 命名）
  → build_static（6 個 instance、removeOverlaps、WOFF2）
  → qa/{regressions, check_names, coverage, outlines, gray}
```

## 產出

`make all` 把字型寫到 `fonts/`，中間檔寫到 `build/`。`make release` 會把成品搬到 `release-font/`，再刪除中間檔：

```
release-font/
├── variable/QingmoSansTC[wght].ttf      可變字型，wght 250–900，預設 400（約 19.8 MB）
├── static/QingmoSansTC-{ExtraLight,Light,Regular,Medium,Bold,Heavy}.ttf
│                                         static instances（已移除 overlap，各約 9 MB）
├── webfonts/*.woff2                      上述全部的整檔 WOFF2（VF 約 8.9 MB、static 約 3–3.7 MB）
├── webfont-slices/                       make webfonts 才有：每個字型切 45 片 WOFF2 + @font-face CSS + demo.html
├── 60-qingmo-sans-tc.conf                Linux fontconfig 設定
├── OFL.txt                               授權（OFL 要求隨字型散布）
└── FONTLOG.txt                           版本與變更紀錄
```

- `make release` 會先清空舊的 `release-font/`，再刪除 `fonts/` 和 `build/`（`build/base/` 的母體下載快取保留，下次建置不必重新下載）
- 要跑 `make bakery`、`make proof` 或看 `build/transformed/transform-report.json`，請在 `make release` 之前跑，因為它們讀的是 `fonts/` 和 `build/`
- `fonts/`、`build/`、`release-font/` 都不進版控；CI 的 `build` job 會把 `fonts/` 上傳成 artifact `qingmo-sans-fonts`，正式版本由 tag 觸發的 release workflow 發佈到 GitHub Releases（見「發佈流程」）

## 使用

從 [Releases](https://github.com/EddyKuo/qingmo-sans/releases) 下載 `QingmoSansTC-<版本>.zip`。

### 桌面（macOS / Windows / Linux）

安裝 `static/` 的 6 個 TTF；排版軟體支援可變字型的話，改裝 `variable/QingmoSansTC[wght].ttf`。兩者不要同時安裝，否則字型選單會重複。
macOS 與 Windows 的系統介面字型無法正式替換，安裝後可在 App 與網頁中使用。

### Linux 桌面預設字型

```bash
mkdir -p ~/.local/share/fonts ~/.config/fontconfig/conf.d
cp static/*.ttf ~/.local/share/fonts/
cp 60-qingmo-sans-tc.conf ~/.config/fontconfig/conf.d/
fc-cache -f
fc-match 'sans\-serif:lang=zh-tw'    # 應顯示 Qingmo Sans TC
```

設定檔讓 zh-TW / zh-HK / zh-MO 環境的 `sans-serif` 與 `system-ui` 優先使用晴墨，並開啟 `hintslight`（晴墨沒有 hinting，用 FreeType 輕量自動 hinting 讓小字較銳利）。GNOME 的介面字型另外設定：`gsettings set org.gnome.desktop.interface font-name 'Qingmo Sans TC 11'`。

### 網頁

下載 `QingmoSansTC-<版本>-webfont-slices.zip`，整個資料夾放到網站上：

```html
<link rel="stylesheet" href="/fonts/qingmo/qingmo-sans-tc.css">
<style>
  body { font-family: "Inter", "Qingmo Sans TC", sans-serif; line-height: 1.5; }
</style>
```

- `qingmo-sans-tc.css` 用可變字型，`font-weight` 可設 250–900 任意值，建議使用；`qingmo-sans-tc-static.css` 是 6 個固定字重
- 每個字型依常用程度切成 45 片：第 0 片是非漢字 + 高頻 500 字，接著是 Big5 常用字、次常用字，最後是其餘漢字。瀏覽器只下載頁面用到的切片
- 本機打開 `demo.html`（需經 HTTP 伺服器，例如 `python3 -m http.server`）可確認載入情況
- 只有一頁、字很少的網站，可以改用 `pyftsubset` 依頁面文字子集化，檔案更小

### App 內嵌（iOS / Android / Electron / Flutter）

打包 `static/` 中實際用到的字重（UI 內文常用 Regular、Medium，標題用 Bold），或打包一個 VF。英數字建議另外接一個拉丁 UI 字型，晴墨放在 fallback 第二順位。

### 用在 UI 時的注意事項

- 晴墨沒有 hinting：macOS、iOS、Android 不受影響；Windows 12–14 px 可能偏糊，請實測
- 母體行距偏大，UI 中建議明確設定行高（約 1.4–1.5）
- ExtraLight 在小字時太細，不建議用於 UI 內文

## 發佈流程

1. 更新 `config/spec.yaml` 的 `family.version`，並在 `FONTLOG.txt` 新增同版號的段落
2. 提交並推到 `main`
3. 推送同名 tag：`git tag v<版本> && git push origin v<版本>`

`.github/workflows/release.yml` 會依序執行：檢查 tag 與 spec 版號一致 → `make test` → `make all`（全字集約 1 小時以上）→ `make bakery` → `make webfonts` → `make release` → 打包兩個 zip 與 `SHA256SUMS.txt`，再以 FONTLOG 該版段落作為說明，建立 GitHub Release。0.x 版會標成 pre-release。

## 風格改造（Phase 1）

只作用於 CJK 統一漢字；拉丁字母、標點、注音沿用母體字形。若某項改造在某個字造成錯誤或新增自交，安全網只對該字略過該項（全字集 17,684 字中 118 字，清單在 `build/transformed/transform-report.json`）。所有「改哪些點」的判斷在 Regular（wght 400）master 上做一次，再套到每個 master，確保點相容。

| Transform | Spec 參數 | 做法 |
| --- | --- | --- |
| `proportion` | 中宮收緊（k = −25，最多內移約 31 units）、重心上移 2%、寬高比 1.00 | 字面框內單調位移場；成對的豎畫 / 橫畫整筆平移，保持筆寬 |
| `contrast` | 豎 : 橫 = 100 : 82 | 偵測橫畫上下緣，兩緣各向內移動 |
| `terminals` | 起筆斜切 12°、收筆微收 8% | 只處理看得見的筆端（藏在其他筆畫裡的不算） |
| `strokes` | 點上尖下圓、捺短平台出鋒、撇出鋒漸細 | 依筆端朝向與形狀辨識點 / 撇 / 捺，套用模板；點的圓頭需加點 |
| `corners` | 外角軟化 r = 6 units，隨字重縮放 | 在所有 master 的同一批轉角插入二次曲線圓角 |

## QA 閘門

| 檢查 | 腳本 | Phase 1 結果 |
| --- | --- | --- |
| 跨 master 點相容 | `scripts/check_compat.py` | 18,343 / 18,343 |
| 改造不新增自交（masters 與中間字重） | `scripts/qa/regressions.py` | 通過 |
| `name` 不含 "Source" | `scripts/qa/check_names.py` | 通過 |
| 字集覆蓋 | `scripts/qa/coverage.py` | 17,760 / 17,760（Big5 13,064、高頻 500 全數涵蓋） |
| 破字 0（自交、方向、殘留 overlap） | `scripts/qa/outlines.py` | VF 與 6 個 static 通過 |
| 灰度一致（std ≤ 母體 × 1.05） | `scripts/qa/gray.py` | wght 400 比值 0.918（15,384 字） |
| fontbakery check-universal | `fontbakery --config config/fontbakery.yaml` | 0 FAIL（檔案大小門檻見設定檔說明） |
| 12 / 16 / 24 px 人工抽檢高頻 500 字 | `scripts/qa/proof_sheet.py` 產生校樣 | Claude 已目視校樣（見研究紀錄 §9），人工抽檢待執行 |

## 目錄

| 路徑 | 內容 |
| --- | --- |
| `config/spec.yaml` | 機器可讀的 Design Spec：命名、母體、軸、字重、風格參數、QA 門檻 |
| `config/charsets/` | 各階段字集；`highfreq500.txt` 由 `scripts/charsets/highfreq.py` 從 Unihan 產生 |
| `config/fontconfig/` | Linux fontconfig 設定，隨 release 散布 |
| `scripts/` | 建置腳本；`transform/` 是幾何改造，`qa/` 是驗收閘門，`webfont_slices.py` 產生網頁切片，`release_notes.py` 產生發佈說明 |
| `.github/workflows/` | `build.yml`（每次 push：單元測試、smoke、全字集建置）、`release.yml`（推送 `v*` tag：建置並發佈 GitHub Release） |
| `tests/` | `test_transforms.py` 單元測試、`smoke_test.py` 端到端測試 |
| `docs/` | Design Spec、研究與建置紀錄 |
| `CLAUDE.md` | Claude Code 工作指引（繁中回答、架構規則、閘門） |
| `CLEANROOM.md` | 貢獻前必讀的 clean-room 規範 |
| `FONTLOG.txt` | 版本與參數變更紀錄 |

## 授權

字型：SIL Open Font License 1.1。母體版權 Copyright 2014-2021 Adobe，Reserved Font Name 'Source'。
建置腳本：MIT（見 [`LICENSE-CODE`](LICENSE-CODE)）。
