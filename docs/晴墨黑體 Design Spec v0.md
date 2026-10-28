# 晴墨黑體 Design Spec v0

Oct 28, 2026 · @Eddy Kuo

## 定位與目標

晴墨黑體（Qingmo Sans TC）是以 SIL OFL 1.1 釋出的繁體中文「明黑混合」內文字型：黑體的骨架與清晰度，加上明體的書寫筆勢，主戰場是 10–16 pt 的螢幕與印刷內文。

- **使用情境**：App/Web UI 內文、長篇閱讀、簡報、品牌輔助字
- **v1.0 目標**：Big5 完整字集 + 教育部常用字、6 個字重的 Variable Font、橫排與直排
- **非目標（v1）**：強烈個性的標題展示字、簡體字集、手寫風格、hinting 完整度

## Clean-room 規範

所有字形只能源自 OFL 母體與本專案自己的參數、程式碼；任何第三方商用字型的字形資料一律不進入 repo、建置流程或模型。

| 類別 | 規則 |
| --- | --- |
| 禁止 | 開啟、擷取、描繪、比對任何商用字型檔（含 jf 金萱）的 outline；以其字樣訓練或提示任何生成模型；名稱或宣傳使用「金萱」 |
| 允許來源 | Source Han Sans VF（OFL）、本 Spec 的參數、公開文獻中的文字描述 |
| 允許參考 | 字型設計通論（中宮、重心、筆勢等概念）；視覺審查僅限人眼，不存檔、不入版控 |
| 紀錄 | 每個參數變更寫入 `FONTLOG.txt` 與 commit message；`CLEANROOM.md` 由每位貢獻者簽署 |

## 風格參數

設計意象：「晴」= 中宮開朗、留白通透；「墨」= 筆畫有明體的粗細對比與墨暈般的軟角。以下數值為 Regular（wght 400）的 v0 初值，Phase 1 以實際字樣調整。

| 參數 | v0 初值 | 實作方式 |
| --- | --- | --- |
| 字身比例 | 方正，寬高比 1.00 | 不做整字縮放 |
| 中宮 | 比母體放鬆 3% | per-component 外移，保持部件筆畫粗細 |
| 重心 | 居中，上移 ≤ 0.5% | 上下結構字調整部件高度比 |
| 筆畫對比（豎 : 橫） | 100 : 82 | 依筆畫方向做非對稱 offset |
| 起筆 | 斜切 12° | terminal 幾何重建 |
| 收筆 | 微收 8% 寬度 | 末端 taper |
| 折角 | 外角軟化 r = 6 units（UPM 1000） | corner rounding，隨字重縮放 |
| 點 | 上尖下圓的錐形點 | 點類筆畫模板替換 |
| 捺 | 收尾帶短平台再出鋒 | 捺類筆畫模板替換 |
| 撇 | 出鋒漸細，末端不留尖刺 | taper + 最小寬度限制 |

## 差異化定義

晴墨與金萱同屬「明黑混合」類型，但在 5 個可辨識的維度上刻意走不同方向；比較依據僅限 justfont 公開文章對金萱的文字描述（瘦長骨架、中宮緊收、重心偏上）。

| 維度 | 金萱（公開描述） | 晴墨決策 |
| --- | --- | --- |
| 骨架比例 | 瘦長 | 方正，偏 UI 可讀性 |
| 中宮 | 緊收 | 放鬆，留白通透 |
| 重心 | 偏上 | 居中 |
| 折角 | — | 墨暈軟角，作為晴墨的識別特徵 |
| 筆端 | — | 統一 12° 斜切 + 捺筆短平台，自有規則 |

任何參數若被調整到接近左欄描述，須在 PR 中說明理由並經維護者核可。

## 母體與授權

母體採 Source Han Sans TC 的 Variable 版本：字集涵蓋繁體需求，且各 master 點相容，改造後可直接輸出 wght 可變字型。

- **授權**：衍生作品必須維持 SIL OFL 1.1；不得單獨販售字型檔，可隨軟體散布
- **Reserved Font Name**：母體保留 "Source"，晴墨的任何名稱欄位（`name` table ID 1/4/6/16）不得出現此字
- **版權聲明**：`OFL.txt` 同時列出 Adobe 原始版權（含 RFN 聲明）與晴墨貢獻者版權
- **主要技術風險**：每一步幾何改造都必須保持跨 master 的點數與順序一致，否則 VF 插值失效；Phase 1 的首要驗收即為此
- **已確認（Phase 1）**：母體 VF 的 wght 範圍為 250–900，named instances 250 / 300 / 350 / 400 / 500 / 700 / 900，並有非線性 `avar`；晴墨沿用該字重曲線

## 字集與分期

&#91;embedded content: 開發分期 · 5 個階段、4 道關卡\]

Phase 1 的跨 master 點相容驗證是整個專案的技術分水嶺：過不了，就要改用 static instance 逐一改造再重建 VF。

## 字重與度量

單一 wght 軸的 Variable Font，另輸出 6 個 static instances；度量沿用母體，避免與既有排版習慣衝突。

| 項目 | 規格 |
| --- | --- |
| 可變軸 | `wght` 250–900（母體 `fvar` 範圍；Phase 1 定案） |
| Named instances | ExtraLight 250 · Light 300 · Regular 400 · Medium 500 · Bold 700 · Heavy 900（ExtraLight 的 usWeightClass 仍為 200） |
| 中文字重名 | 極細 · 細 · 標準 · 中 · 粗 · 特粗 |
| UPM | 1000 |
| 漢字字寬 | 全形 1000 units |
| 字面框 | 沿用母體 ICF：ideo 基線 -120；icfb / icft = -67 / 827（wght 250）、-78 / 838（400）、-94 / 854（900） |
| 直排 | 保留 `vhea` / `vmtx` 與 `vert` / `vrt2` feature；標點直排字形一併改造 |
| 拉丁字母 | v1 沿用母體內含字形，僅做字重對齊；v2 評估自製 |
| 輸出格式 | TTF（VF + static）、WOFF2；OTF/CFF2 於 v1.0 再評估 |

## 命名規格與 QA 驗收

名稱已做初步網路查核（同名字型、品牌皆未發現），正式發布前仍須完成 TIPO 第 9、16 類近似檢索。

| 欄位 | 值 |
| --- | --- |
| Family（中 / 英） | 晴墨黑體 / Qingmo Sans TC |
| PostScript | `QingmoSansTC-Regular` 等 |
| VF 檔名 | `QingmoSansTC[wght].ttf` |
| Repo | `qingmo-sans` |
| License | SIL OFL 1.1 |

每個 release 必須全數通過：

- [ ] 跨 master 點相容 100%（VF 可編譯、插值無破形）
- [ ] 破字 0：無自交、方向錯誤、殘留 overlap（skia-pathops 檢查）
- [ ] 灰度一致：同結構類別的字面墨色覆蓋率標準差低於門檻（Phase 1 定門檻值）
- [ ] fontbakery 無 FAIL
- [ ] 12 / 16 / 24 px 全字表渲染人工抽檢高頻 500 字
- [ ] `name` table 不含 "Source"

### Sources

- [justfont：金萱設計說明](https://blog.justfont.com/?p=6590)
- [Source Han Sans（GitHub）](https://github.com/adobe-fonts/source-han-sans)
- [SIL Open Font License 1.1](https://openfontlicense.org)
