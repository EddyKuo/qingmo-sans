# 晴墨黑體 build pipeline
.RECIPEPREFIX = >
PY ?= python3
VF := fonts/variable/QingmoSansTC[wght].ttf
STATICS = $(wildcard fonts/static/*.ttf)
CHARSET ?= full
BASE_SUBSET := build/subset/base-$(CHARSET).ttf
# 任一可變 TTF；--masters 需落在它的 wght 範圍內
SMOKE_FONT ?= build/smoke/Lora[wght].ttf
SMOKE_MASTERS ?= 400,700

.PHONY: all fetch inspect subset masters transform compat build static qa bakery proof test smoke clean

all: static qa

fetch:
> $(PY) scripts/fetch_base.py

inspect: fetch
> $(PY) scripts/inspect_base.py

subset: fetch
> $(PY) scripts/subset.py --charset $(CHARSET)

masters: subset
> $(PY) scripts/extract_masters.py --src $(BASE_SUBSET)

transform: masters
> $(PY) scripts/transform/pipeline.py

compat: transform
> $(PY) scripts/check_compat.py build/transformed

build: compat
> $(PY) scripts/build_vf.py --avar-src $(BASE_SUBSET)

static: build
> $(PY) scripts/build_static.py

qa:
> $(PY) scripts/qa/check_names.py "$(VF)" $(STATICS)
> $(PY) scripts/qa/coverage.py "$(VF)" --charset $(CHARSET)
> $(PY) scripts/qa/coverage.py "$(VF)" --charset highfreq500
> $(PY) scripts/build_vf.py --indir build/masters --out build/qa/masters-vf.ttf --avar-src $(BASE_SUBSET)
> $(PY) scripts/qa/regressions.py --vf "$(VF)" --base-vf build/qa/masters-vf.ttf
> $(PY) scripts/qa/outlines.py "$(VF)"
> $(PY) scripts/qa/outlines.py --no-overlap $(STATICS)
> $(PY) scripts/qa/gray.py "$(VF)" --base $(BASE_SUBSET) --wght 400

bakery:
> fontbakery check-universal --config config/fontbakery.yaml $(STATICS)
> fontbakery check-universal --config config/fontbakery.yaml "$(VF)"

proof:
> $(PY) scripts/qa/proof_sheet.py fonts/static/QingmoSansTC-Regular.ttf

test:
> $(PY) tests/test_transforms.py

$(SMOKE_FONT):
> mkdir -p $(dir $@)
> curl -sSL -o "$@" "https://github.com/google/fonts/raw/main/ofl/lora/Lora%5Bwght%5D.ttf"

smoke: $(SMOKE_FONT)
> $(PY) tests/smoke_test.py "$(SMOKE_FONT)" --masters $(SMOKE_MASTERS)

clean:
> rm -rf build fonts
