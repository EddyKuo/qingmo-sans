"""產生逐字檢查用的 2D 字表（單一 HTML，字型以 WOFF2 內嵌，雙擊即可開啟）。

    python scripts/qa/font_map.py [--font FONT] [--base BASE] [--out build/proof/font-map.html]

- 列出 FONT cmap 的全部字元，可依 Unicode 區塊或常用程度（同 webfont_slices.py 的切片順序）排列
- 字級、字重可調；可把母體（clean-room 允許的唯一比較對象）以淡紅色疊在下方
- 點字看大圖（晴墨 / 母體並排、250 / 400 / 900）；鍵盤 1 = OK、2 = 有問題、0 = 清除，標記後自動前進
- 檢查進度存在瀏覽器 localStorage（依版號分開），可匯出「有問題」清單
- 若有 build/transformed/transform-report.json，安全網略過改造的字會加上標記
預設字型：fonts/variable/ 的 VF，沒有就用 release-font/variable/。輸出只放 build/proof/（不進版控）。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fontTools import subset  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

from common import BUILD, ROOT, base_path, load_spec  # noqa: E402
from charsets.base_lists import is_cjk  # noqa: E402
from webfont_slices import big5_levels, plan  # noqa: E402

VF_NAME = "QingmoSansTC[wght].ttf"

BLOCKS = [
    (0x0000, 0x007F, "基本拉丁"), (0x0080, 0x00FF, "拉丁補充"), (0x2000, 0x206F, "一般標點"),
    (0x3000, 0x303F, "CJK 符號與標點"), (0x3100, 0x312F, "注音"), (0x3400, 0x4DBF, "擴充 A"),
    (0x4E00, 0x9FFF, "CJK 統一漢字"), (0xF900, 0xFAFF, "CJK 相容漢字"), (0xFF00, 0xFFEF, "全形與半形"),
    (0x20000, 0x2A6DF, "擴充 B"), (0x2A700, 0x2B73F, "擴充 C"), (0x2B740, 0x2B81F, "擴充 D"),
    (0x2B820, 0x2CEAF, "擴充 E"), (0x2CEB0, 0x2EBEF, "擴充 F"), (0x2F800, 0x2FA1F, "相容漢字補充"),
]
GROUPS = ["非漢字", "高頻 500", "Big5 常用字", "Big5 次常用字", "其餘漢字"]


def default_font() -> pathlib.Path:
    for d in (ROOT / "fonts" / "variable", ROOT / "release-font" / "variable"):
        if (d / VF_NAME).exists():
            return d / VF_NAME
    sys.exit("找不到可變字型：請先 make all，或用 --font 指定")


def woff2_b64(path: pathlib.Path, unicodes: list[int] | None = None) -> str:
    """轉成 WOFF2（給 unicodes 時先子集化），回傳 base64。"""
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    font = subset.load_font(str(path), opts)
    if unicodes is not None:
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=unicodes)
        sub.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, opts)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def block_of(cp: int) -> int:
    return next((i for i, (lo, hi, _) in enumerate(BLOCKS) if lo <= cp <= hi), len(BLOCKS))


def group_of(cp: int, hf: set[int], common: set[int], less: set[int]) -> int:
    if not is_cjk(cp):
        return 0
    return 1 if cp in hf else 2 if cp in common else 3 if cp in less else 4


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", type=pathlib.Path, default=None)
    ap.add_argument("--base", type=pathlib.Path, default=None, help="母體；預設 build/base/，--no-base 不嵌入")
    ap.add_argument("--no-base", action="store_true")
    ap.add_argument("--report", type=pathlib.Path, default=BUILD / "transformed" / "transform-report.json")
    ap.add_argument("--out", type=pathlib.Path, default=BUILD / "proof" / "font-map.html")
    args = ap.parse_args()

    spec = load_spec()
    font = args.font or default_font()
    cmap = TTFont(font, lazy=True).getBestCmap()
    cps = sorted(cmap)

    # 常用程度順序與網頁切片相同
    freq_order = [cp for piece in plan(set(cps), 400) for cp in piece]
    rank = {cp: i for i, cp in enumerate(freq_order)}
    from common import read_charset
    hf = read_charset(ROOT / spec["charsets"]["highfreq500"])
    common, less = (set(x) for x in big5_levels())

    skipped = {}
    if args.report.exists():
        for name, info in json.loads(args.report.read_text(encoding="utf-8")).items():
            skipped[name] = info["skipped"]
    by_name = {}
    for cp, name in cmap.items():
        if name in skipped:
            by_name[cp] = skipped[name]

    chars = [[cp, block_of(cp), group_of(cp, hf, common, less), rank[cp]] for cp in cps]

    print(f"嵌入 {font.name}（{len(cps)} 字）…")
    fonts = {"qingmo": woff2_b64(font)}
    base = args.base or base_path(spec)
    if not args.no_base and base.exists():
        print(f"嵌入母體 {base.name}（子集化為相同字元）…")
        fonts["base"] = woff2_b64(base, cps)

    data = {
        "version": spec["family"]["version"],
        "family": spec["family"]["en"],
        "chars": chars,
        "blocks": [b[2] for b in BLOCKS] + ["其他"],
        "groups": GROUPS,
        "skipped": {str(cp): v for cp, v in by_name.items()},
        "hasBase": "base" in fonts,
    }
    faces = "".join(
        f'@font-face{{font-family:"QM-{k}";src:url(data:font/woff2;base64,{v}) format("woff2");'
        f"font-weight:250 900;font-display:block}}\n" for k, v in fonts.items())
    html = TEMPLATE.replace("/*FACES*/", faces).replace("/*DATA*/", json.dumps(data, ensure_ascii=False))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"OK {args.out}（{args.out.stat().st_size / 1048576:.1f} MB）")


TEMPLATE = r"""<!doctype html>
<html lang="zh-Hant-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>晴墨黑體 字表檢查</title>
<style>
/*FACES*/
:root {
  --bg: #fafaf8; --panel: #ffffff; --ink: #1a1a1a; --muted: #6b6b6b; --line: #e3e3de;
  --accent: #2f6fdf; --ok: #2e9b57; --bad: #d33a2c; --base: rgba(220, 40, 30, .38); --skip: #c98a00;
  --cell: 56px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161616; --panel: #1f1f1f; --ink: #ececec; --muted: #9a9a9a; --line: #333;
    --accent: #6ea0ff; --ok: #4cc27a; --bad: #ff6b5e; --base: rgba(255, 90, 80, .45); --skip: #e0a82a;
  }
}
:root[data-theme="dark"] {
  --bg: #161616; --panel: #1f1f1f; --ink: #ececec; --muted: #9a9a9a; --line: #333;
  --accent: #6ea0ff; --ok: #4cc27a; --bad: #ff6b5e; --base: rgba(255, 90, 80, .45); --skip: #e0a82a;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
header { position: sticky; top: 0; z-index: 5; background: var(--panel); border-bottom: 1px solid var(--line);
  padding: 10px 16px; display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; }
header h1 { font-size: 16px; margin: 0; white-space: nowrap; }
header label { display: inline-flex; gap: 6px; align-items: center; color: var(--muted); white-space: nowrap; }
header input[type=range] { width: 110px; }
header select, header input[type=search], header button { font: inherit; color: var(--ink); background: var(--bg);
  border: 1px solid var(--line); border-radius: 6px; padding: 3px 8px; }
header button { cursor: pointer; }
header input[type=search] { width: 150px; }
.progress { margin-left: auto; color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }
.progress b { color: var(--ink); }
.bar { height: 3px; background: var(--line); position: sticky; top: var(--hdr, 52px); z-index: 4; }
.bar i { display: block; height: 100%; background: var(--ok); width: 0; }
main { display: flex; align-items: flex-start; }
#map { flex: 1; min-width: 0; padding: 8px 16px 80px; }
section { content-visibility: auto; contain-intrinsic-size: auto 600px; }
section h2 { font-size: 13px; font-weight: 600; color: var(--muted); margin: 18px 0 6px;
  position: sticky; top: calc(var(--hdr, 52px) + 3px); background: var(--bg); padding: 4px 0; z-index: 2; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--cell), 1fr)); border-left: 1px solid var(--line); border-top: 1px solid var(--line); }
.c { position: relative; aspect-ratio: 1 / 1.22; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line);
  cursor: pointer; display: flex; flex-direction: column; align-items: center; justify-content: center; overflow: hidden; }
.c:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.c .g { position: relative; font-family: "QM-qingmo"; font-size: calc(var(--cell) * .62); line-height: 1;
  font-variation-settings: "wght" var(--wght, 400); }
.c .g::before { content: attr(data-ch); position: absolute; inset: 0; font-family: "QM-base"; color: var(--base);
  display: none; font-variation-settings: "wght" var(--wght, 400); }
body.overlay .c .g::before { display: block; }
body.overlay .c .g { color: color-mix(in srgb, var(--ink) 75%, transparent); }
.c small { font-size: 9px; color: var(--muted); margin-top: 3px; font-variant-numeric: tabular-nums; letter-spacing: -.2px; }
body.nolabel .c small { display: none; }
body.nolabel .c { aspect-ratio: 1; }
.c.ok { background: color-mix(in srgb, var(--ok) 13%, transparent); }
.c.bad { background: color-mix(in srgb, var(--bad) 18%, transparent); }
.c.bad::after { content: ""; position: absolute; top: 3px; right: 3px; width: 7px; height: 7px; border-radius: 50%; background: var(--bad); }
.c.sk::before { content: ""; position: absolute; top: 3px; left: 3px; width: 0; height: 0;
  border-top: 8px solid var(--skip); border-right: 8px solid transparent; }
.c.sel { outline: 2px solid var(--accent); outline-offset: -2px; z-index: 1; }
.c.hide { display: none; }
aside { width: 360px; flex: none; position: sticky; top: calc(var(--hdr, 52px) + 3px); height: calc(100vh - var(--hdr, 52px) - 3px);
  overflow: auto; border-left: 1px solid var(--line); background: var(--panel); padding: 16px; }
aside .big { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
aside .big div { border: 1px solid var(--line); border-radius: 8px; text-align: center; padding: 6px 0 4px; }
aside .big span { display: block; font-size: 128px; line-height: 1.1; }
aside .big em { font-style: normal; color: var(--muted); font-size: 12px; }
aside .weights { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 8px; text-align: center; }
aside .weights span { display: block; font-size: 54px; line-height: 1.15; }
aside .weights em { font-style: normal; color: var(--muted); font-size: 11px; }
aside .meta { margin: 12px 0; color: var(--muted); font-variant-numeric: tabular-nums; }
aside .meta b { color: var(--ink); font-size: 15px; }
aside .meta .skipnote { color: var(--skip); }
aside .acts { display: flex; gap: 8px; }
aside .acts button { flex: 1; font: inherit; padding: 8px 0; border-radius: 8px; border: 1px solid var(--line);
  background: var(--bg); color: var(--ink); cursor: pointer; }
aside .acts .ok.on { background: var(--ok); color: #fff; border-color: var(--ok); }
aside .acts .bad.on { background: var(--bad); color: #fff; border-color: var(--bad); }
aside textarea { width: 100%; margin-top: 8px; min-height: 60px; font: inherit; color: var(--ink); background: var(--bg);
  border: 1px solid var(--line); border-radius: 8px; padding: 6px 8px; }
aside .keys { color: var(--muted); font-size: 12px; margin-top: 12px; }
aside .keys kbd { font: 11px ui-monospace, monospace; border: 1px solid var(--line); border-radius: 4px; padding: 0 4px; }
.qm { font-family: "QM-qingmo"; } .bs { font-family: "QM-base"; }
#loading { position: fixed; inset: 0; display: grid; place-items: center; background: var(--bg); z-index: 9; color: var(--muted); }
@media (max-width: 860px) {
  main { flex-direction: column; }
  aside { width: 100%; position: fixed; bottom: 0; top: auto; height: auto; max-height: 55vh; border-left: 0; border-top: 1px solid var(--line); z-index: 6; }
  aside.closed { display: none; }
  aside .big span { font-size: 88px; }
  header input[type=range] { width: 80px; }
}
</style>
</head>
<body>
<div id="loading">載入字型中…</div>
<header>
  <h1>晴墨黑體 字表 <span id="ver" style="color:var(--muted);font-weight:400"></span></h1>
  <label>排列 <select id="order"><option value="block">Unicode 區塊</option><option value="freq">常用程度</option></select></label>
  <label>顯示 <select id="filter"><option value="all">全部</option><option value="todo">未檢查</option><option value="bad">有問題</option><option value="ok">OK</option><option value="skip">安全網略過</option></select></label>
  <label>字級 <input id="size" type="range" min="32" max="140" value="56"></label>
  <label>字重 <input id="wght" type="range" min="250" max="900" step="10" value="400"><span id="wv">400</span></label>
  <label><input id="overlay" type="checkbox"> 疊上母體</label>
  <label><input id="label" type="checkbox" checked> 碼位</label>
  <input id="q" type="search" placeholder="跳到：字 或 U+4E00">
  <button id="export">匯出有問題清單</button>
  <span class="progress">已檢查 <b id="done">0</b> / <span id="total">0</span>　有問題 <b id="nbad">0</b></span>
</header>
<div class="bar"><i id="barfill"></i></div>
<main>
  <div id="map"></div>
  <aside id="side" class="closed">
    <div class="big">
      <div><span class="qm" id="bq"></span><em>晴墨</em></div>
      <div><span class="bs" id="bb"></span><em>母體</em></div>
    </div>
    <div class="weights">
      <div><span class="qm" style="font-variation-settings:'wght' 250" id="w250"></span><em>250</em></div>
      <div><span class="qm" style="font-variation-settings:'wght' 400" id="w400"></span><em>400</em></div>
      <div><span class="qm" style="font-variation-settings:'wght' 900" id="w900"></span><em>900</em></div>
    </div>
    <div class="meta" id="meta"></div>
    <div class="acts">
      <button class="ok" id="bok">OK <kbd>1</kbd></button>
      <button class="bad" id="bbad">有問題 <kbd>2</kbd></button>
      <button id="bclr">清除 <kbd>0</kbd></button>
    </div>
    <textarea id="note" placeholder="備註（例如：右下點太大、與母體相比橫畫太細）"></textarea>
    <div class="keys"><kbd>←</kbd><kbd>→</kbd><kbd>↑</kbd><kbd>↓</kbd> 移動　<kbd>1</kbd> OK 並前進　<kbd>2</kbd> 有問題並前進　<kbd>0</kbd> 清除　<kbd>B</kbd> 疊上母體　<kbd>Esc</kbd> 關閉</div>
  </aside>
</main>
<script>
const D = /*DATA*/;
const KEY = "qingmo-fontmap-" + D.version;
let marks = {};
try { marks = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(marks)); } catch (e) {} };
const $ = id => document.getElementById(id);
const hex = cp => "U+" + cp.toString(16).toUpperCase().padStart(4, "0");
const map = $("map"), cells = new Map();
let order = [], sel = -1;

$("ver").textContent = D.version;
$("total").textContent = D.chars.length.toLocaleString();
if (!D.hasBase) { $("overlay").disabled = true; $("overlay").parentElement.title = "未嵌入母體"; }

function build() {
  const byFreq = $("order").value === "freq";
  const list = D.chars.slice().sort((a, b) => byFreq ? a[3] - b[3] : a[0] - b[0]);
  const names = byFreq ? D.groups : D.blocks, key = byFreq ? 2 : 1;
  map.textContent = ""; cells.clear(); order = [];
  let sec = null, grid = null, cur = -1;
  const frag = document.createDocumentFragment();
  for (const [cp, blk, grp] of list) {
    const k = byFreq ? grp : blk;
    if (k !== cur) {
      cur = k;
      sec = document.createElement("section");
      const n = list.filter(c => c[key] === k).length;
      sec.innerHTML = `<h2>${names[k]}　${n.toLocaleString()} 字</h2>`;
      grid = document.createElement("div"); grid.className = "grid";
      sec.appendChild(grid); frag.appendChild(sec);
    }
    const ch = String.fromCodePoint(cp);
    const c = document.createElement("div");
    c.className = "c"; c.dataset.cp = cp; c.dataset.i = order.length;
    const g = document.createElement("span"), lab = document.createElement("small");
    g.className = "g"; g.dataset.ch = ch; g.textContent = ch;
    lab.textContent = cp.toString(16).toUpperCase();
    c.append(g, lab);
    if (D.skipped[cp]) c.classList.add("sk");
    paint(c, cp);
    grid.appendChild(c); cells.set(cp, c); order.push(cp);
  }
  map.appendChild(frag);
  applyFilter(); stats();
  if (sel >= 0) select(order.indexOf(sel), false);
}

function paint(c, cp) {
  const m = marks[cp];
  c.classList.toggle("ok", m?.s === "ok");
  c.classList.toggle("bad", m?.s === "bad");
}

function applyFilter() {
  const f = $("filter").value;
  for (const [cp, c] of cells) {
    const s = marks[cp]?.s;
    const show = f === "all" || (f === "todo" && !s) || (f === "ok" && s === "ok") || (f === "bad" && s === "bad") || (f === "skip" && D.skipped[cp]);
    c.classList.toggle("hide", !show);
  }
}

function stats() {
  const v = Object.values(marks);
  const done = v.filter(m => m.s).length, bad = v.filter(m => m.s === "bad").length;
  $("done").textContent = done.toLocaleString(); $("nbad").textContent = bad.toLocaleString();
  $("barfill").style.width = (done / D.chars.length * 100) + "%";
}

function visible(i) { const c = cells.get(order[i]); return c && !c.classList.contains("hide"); }

function select(i, scroll = true) {
  if (i < 0 || i >= order.length) return;
  document.querySelector(".c.sel")?.classList.remove("sel");
  const cp = order[i], c = cells.get(cp), ch = String.fromCodePoint(cp);
  sel = cp; c.classList.add("sel");
  if (scroll) c.scrollIntoView({ block: "nearest" });
  $("side").classList.remove("closed");
  const w = getComputedStyle(document.documentElement).getPropertyValue("--wght") || 400;
  $("bq").textContent = ch; $("bb").textContent = D.hasBase ? ch : "";
  $("bq").style.fontVariationSettings = $("bb").style.fontVariationSettings = `"wght" ${w}`;
  for (const x of ["w250", "w400", "w900"]) $(x).textContent = ch;
  const info = D.chars.find(r => r[0] === cp);
  const sk = D.skipped[cp] ? `<br><span class="skipnote">安全網略過：${D.skipped[cp].join("、")}</span>` : "";
  $("meta").innerHTML = `<b>${ch}</b>　${hex(cp)}<br>${D.blocks[info[1]]}・${D.groups[info[2]]}${sk}`;
  const m = marks[cp] || {};
  $("bok").classList.toggle("on", m.s === "ok"); $("bbad").classList.toggle("on", m.s === "bad");
  $("note").value = m.n || "";
}

function mark(s, advance = true) {
  if (sel < 0) return;
  const m = marks[sel] || {};
  if (s) m.s = s; else delete m.s;
  if (m.s || m.n) marks[sel] = m; else delete marks[sel];
  save(); paint(cells.get(sel), sel); stats();
  if (advance) move(1); else select(order.indexOf(sel), false);
}

function move(d) {
  let i = order.indexOf(sel);
  do { i += d; } while (i >= 0 && i < order.length && !visible(i));
  if (i >= 0 && i < order.length) select(i);
}

function columns() {
  const c = cells.get(sel); if (!c) return 1;
  const grid = c.parentElement, first = grid.firstElementChild;
  return Math.max(1, Math.round(grid.clientWidth / first.getBoundingClientRect().width));
}

map.addEventListener("click", e => { const c = e.target.closest(".c"); if (c) select(+c.dataset.i, false); });
$("bok").onclick = () => mark("ok"); $("bbad").onclick = () => mark("bad"); $("bclr").onclick = () => mark(null, false);
$("note").addEventListener("input", e => {
  if (sel < 0) return;
  const m = marks[sel] || {}; m.n = e.target.value;
  if (m.s || m.n) marks[sel] = m; else delete marks[sel];
  save();
});
document.addEventListener("keydown", e => {
  if (e.target.closest?.("textarea, input, select")) { if (e.key === "Escape") e.target.blur(); return; }
  const k = e.key;
  if (k === "ArrowRight") move(1);
  else if (k === "ArrowLeft") move(-1);
  else if (k === "ArrowDown") { for (let n = columns(); n > 0; n--) move(1); }
  else if (k === "ArrowUp") { for (let n = columns(); n > 0; n--) move(-1); }
  else if (k === "1") mark("ok");
  else if (k === "2") mark("bad");
  else if (k === "0") mark(null, false);
  else if (k === "b" || k === "B") { $("overlay").click(); return; }
  else if (k === "Escape") { $("side").classList.add("closed"); return; }
  else return;
  e.preventDefault();
});
$("order").onchange = build;
$("filter").onchange = () => { applyFilter(); };
$("size").oninput = e => document.documentElement.style.setProperty("--cell", e.target.value + "px");
$("wght").oninput = e => {
  document.documentElement.style.setProperty("--wght", e.target.value); $("wv").textContent = e.target.value;
  if (sel >= 0) $("bq").style.fontVariationSettings = $("bb").style.fontVariationSettings = `"wght" ${e.target.value}`;
};
$("overlay").onchange = e => document.body.classList.toggle("overlay", e.target.checked);
$("label").onchange = e => document.body.classList.toggle("nolabel", !e.target.checked);
$("q").addEventListener("keydown", e => {
  if (e.key !== "Enter") return;
  const v = e.target.value.trim();
  const m = v.match(/^(?:U\+)?([0-9a-f]{4,6})$/i);
  const cp = m ? parseInt(m[1], 16) : v.codePointAt(0);
  const i = order.indexOf(cp);
  if (i >= 0) { if (!visible(i)) { $("filter").value = "all"; applyFilter(); } select(i); e.target.blur(); }
  else e.target.setCustomValidity("字表中沒有這個字"), e.target.reportValidity(), setTimeout(() => e.target.setCustomValidity(""), 1500);
});
$("export").onclick = () => {
  const rows = Object.entries(marks).filter(([, m]) => m.s === "bad").sort((a, b) => a[0] - b[0])
    .map(([cp, m]) => `${String.fromCodePoint(+cp)}\t${hex(+cp)}\t${(m.n || "").replace(/\s+/g, " ")}`);
  const text = `# 晴墨黑體 ${D.version} 字表檢查：有問題 ${rows.length} 字\n# 字\t碼位\t備註\n` + rows.join("\n") + "\n";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  a.download = `qingmo-${D.version}-issues.txt`; a.click(); URL.revokeObjectURL(a.href);
};
new ResizeObserver(() => document.documentElement.style.setProperty("--hdr", document.querySelector("header").offsetHeight + "px"))
  .observe(document.querySelector("header"));

build();
document.fonts.load('40px "QM-qingmo"', "永").then(() => $("loading").remove());
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
