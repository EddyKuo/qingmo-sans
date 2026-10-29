# 晴墨黑體 build pipeline
PY ?= python3
VF := fonts/variable/QingmoSansTC[wght].ttf
STATICS = $(wildcard fonts/static/*.ttf)
CHARSET ?= full
BASE_SUBSET := build/subset/base-$(CHARSET).ttf
# 任一可變 TTF；--masters 需落在它的 wght 範圍內
SMOKE_FONT ?= build/smoke/Lora[wght].ttf
SMOKE_MASTERS ?= 400,700

RELEASE := release-font

.PHONY: all fetch inspect subset masters transform compat build static qa bakery proof fontmap webfonts test smoke release clean

all: static qa

fetch:
	$(PY) scripts/fetch_base.py

inspect: fetch
	$(PY) scripts/inspect_base.py

subset: fetch
	$(PY) scripts/subset.py --charset $(CHARSET)

masters: subset
	$(PY) scripts/extract_masters.py --src $(BASE_SUBSET)

transform: masters
	$(PY) scripts/transform/pipeline.py

compat: transform
	$(PY) scripts/check_compat.py build/transformed

build: compat
	$(PY) scripts/build_vf.py --avar-src $(BASE_SUBSET)

static: build
	$(PY) scripts/build_static.py

qa:
	$(PY) scripts/qa/check_names.py "$(VF)" $(STATICS)
	$(PY) scripts/qa/coverage.py "$(VF)" --charset $(CHARSET)
	$(PY) scripts/qa/coverage.py "$(VF)" --charset highfreq500
	$(PY) scripts/build_vf.py --indir build/masters --out build/qa/masters-vf.ttf --avar-src $(BASE_SUBSET)
	$(PY) scripts/qa/regressions.py --vf "$(VF)" --base-vf build/qa/masters-vf.ttf
	$(PY) scripts/qa/outlines.py "$(VF)"
	$(PY) scripts/qa/outlines.py --no-overlap $(STATICS)
	$(PY) scripts/qa/gray.py "$(VF)" --base $(BASE_SUBSET) --wght 400

bakery:
	fontbakery check-universal --config config/fontbakery.yaml $(STATICS)
	fontbakery check-universal --config config/fontbakery.yaml "$(VF)"

proof:
	$(PY) scripts/qa/proof_sheet.py fonts/static/QingmoSansTC-Regular.ttf

# 逐字檢查用的 2D 字表：build/proof/font-map.html（字型內嵌，雙擊開啟；fonts/ 不在時改用 release-font/）
fontmap:
	$(PY) scripts/qa/font_map.py

# 網頁用：依 unicode-range 切片的 WOFF2 + @font-face CSS（需先跑 make all）
webfonts:
	rm -rf fonts/webfont-slices
	$(PY) scripts/webfont_slices.py --outdir fonts/webfont-slices "$(VF)" $(STATICS)

test:
	$(PY) tests/test_transforms.py

$(SMOKE_FONT):
	mkdir -p $(dir $@)
	curl -sSL -o "$@" "https://github.com/google/fonts/raw/main/ofl/lora/Lora%5Bwght%5D.ttf"

smoke: $(SMOKE_FONT)
	$(PY) tests/smoke_test.py "$(SMOKE_FONT)" --masters $(SMOKE_MASTERS)

# 把 fonts/ 的成品搬到 release-font/（附 OFL、FONTLOG 與 fontconfig 設定），再刪除中間檔；
# 保留 build/base/ 的母體下載快取與 build/proof/ 的校樣。需先跑 make all（以及要的話 webfonts、bakery、proof）
release:
	test -f "$(VF)" || { echo "找不到 $(VF)，請先執行 make all"; exit 1; }
	rm -rf $(RELEASE)
	mkdir -p $(RELEASE)
	cp -R fonts/variable fonts/static fonts/webfonts OFL.txt FONTLOG.txt $(RELEASE)/
	if [ -d fonts/webfont-slices ]; then cp -R fonts/webfont-slices $(RELEASE)/; fi
	cp config/fontconfig/60-qingmo-sans-tc.conf $(RELEASE)/
	rm -rf fonts
	find build -mindepth 1 -maxdepth 1 ! -name base ! -name proof -exec rm -rf {} +

clean:
	rm -rf build fonts
