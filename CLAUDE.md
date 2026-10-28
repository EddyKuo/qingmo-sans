# CLAUDE.md

本檔提供 Claude Code 在此 repo 工作時的指引。

## 溝通

- **一律使用繁體中文回答**，包含說明、問題、摘要與 commit message
- 程式碼識別字、指令、檔名維持原文

## 專案

晴墨黑體（Qingmo Sans TC）：以 Source Han Sans TC（SIL OFL 1.1）為母體、用程式做幾何改造的繁中「明黑混合」內文字型。

- 設計規格（PRD）：`docs/晴墨黑體 Design Spec v0.md`
- 機器可讀規格：`config/spec.yaml`，所有風格參數與 QA 門檻都在這裡
- 研究與建置過程：`docs/研究與建置紀錄.md`

## 建置與測試

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
make all      # fetch → subset → masters → transform → compat → VF → static/WOFF2 → QA
make test     # transform 單元測試
make smoke    # 用 Lora（OFL）跑整條 pipeline，不需中文母體
```

Windows 沒有 `make`：依 `Makefile` 順序直接執行 `.venv/Scripts/python scripts/...`，並設定 `PYTHONIOENCODING=utf-8`。

## 架構規則

- Transform 只作用於 CJK 統一漢字；拉丁、標點、注音沿用母體
- 「改哪些點」一律在參考 master（wght 400）上判斷，再套到每個 master；不可在各 master 各自判斷，否則點相容會壞
- Point transform：`transform(...) -> points`，點數不得改變
- Structural transform（`strokes`、`corners`）：`transform_structure(...) -> (points, end_pts, flags)`，
  所有 master 必須做相同的結構變更，排在所有 point transform 之後；pipeline 會依序傳入「套用過前面結構性 transform 的參考輪廓」
- 新增的點不可帶 `OVERLAP_SIMPLE`（0x40）旗標，否則 OTS 會拒絕
- VF 沿用母體 `avar` 字重曲線（`build_vf.py` 的 axis map），不要移除

## 提交前必須全數通過

| 閘門 | 指令 |
| --- | --- |
| 點相容 | `scripts/check_compat.py build/transformed` |
| 不新增自交（各 master 與中間字重） | `scripts/qa/regressions.py --vf "fonts/variable/QingmoSansTC[wght].ttf"` |
| 名稱、字集、破字、灰度 | `make qa` |
| 單元測試、smoke | `make test`、`make smoke` |
| fontbakery（選用但目標 0 FAIL） | `fontbakery check-universal fonts/static/*.ttf` |

## Clean-room（見 `CLEANROOM.md`）

- 禁止開啟、渲染、擷取或程式比對任何商用字型（含系統內建的微軟正黑體、新細明體、jf 金萱等）的字形，診斷問題也不行
- 只能用母體、本專案參數與程式碼，以及公開文獻的文字描述
- 校樣圖只放在 `build/proof/`（不進版控）

## 紀錄規則

- 研究發現、量測值、遇到的問題與修正過程，追加到 `docs/研究與建置紀錄.md`
- 參數或字形變更寫入 `FONTLOG.txt`，並在 commit message 說明理由
- PRD 中要求「Phase N 量測後記錄」的欄位，量測後直接更新 Design Spec
