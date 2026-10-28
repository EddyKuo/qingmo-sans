# 晴墨黑體 build pipeline
.RECIPEPREFIX = >
PY ?= python3
VF := fonts/variable/QingmoSansTC[wght].ttf
STATICS = $(wildcard fonts/static/*.ttf)
BASE_SUBSET := build/subset/base-phase1.ttf
# 任一可變 TTF；--masters 需落在它的 wght 範圍內
SMOKE_FONT ?= build/smoke/Lora[wght].ttf
SMOKE_MASTERS ?= 400,700

.PHONY: all fetch inspect subset masters transform compat build static qa test smoke clean

all: static qa

fetch:
> $(PY) scripts/fetch_base.py

inspect: fetch
> $(PY) scripts/inspect_base.py

subset: fetch
> $(PY) scripts/subset.py --charset phase1

masters: subset
> $(PY) scripts/extract_masters.py

transform: masters
> $(PY) scripts/transform/pipeline.py

compat: transform
> $(PY) scripts/check_compat.py build/transformed

build: compat
> $(PY) scripts/build_vf.py

static: build
> $(PY) scripts/build_static.py

qa:
> $(PY) scripts/qa/check_names.py "$(VF)" $(STATICS)
> $(PY) scripts/qa/coverage.py "$(VF)" --charset phase1
> $(PY) scripts/qa/coverage.py "$(VF)" --charset highfreq500
> $(PY) scripts/qa/regressions.py --vf "$(VF)"
> $(PY) scripts/qa/outlines.py "$(VF)"
> $(PY) scripts/qa/outlines.py --no-overlap $(STATICS)
> $(PY) scripts/qa/gray.py "$(VF)" --base $(BASE_SUBSET) --wght 400

test:
> $(PY) tests/test_transforms.py

$(SMOKE_FONT):
> mkdir -p $(dir $@)
> curl -sSL -o "$@" "https://github.com/google/fonts/raw/main/ofl/lora/Lora%5Bwght%5D.ttf"

smoke: $(SMOKE_FONT)
> $(PY) tests/smoke_test.py "$(SMOKE_FONT)" --masters $(SMOKE_MASTERS)

clean:
> rm -rf build fonts
