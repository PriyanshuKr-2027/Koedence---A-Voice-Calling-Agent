CONFIG ?= eval/config.yaml
OUT ?= results
PYTHON ?= python

.PHONY: all memory ablation emotion wer latency erasure figures

all: memory ablation emotion wer latency erasure figures

memory:
	$(PYTHON) -m eval.experiments.memory --config $(CONFIG) --out $(OUT)

ablation:
	$(PYTHON) -m eval.memory.run_ablation --config $(CONFIG) --out $(OUT)/ablation

emotion:
	$(PYTHON) -m eval.emotion.run_emotion --config $(CONFIG) --out $(OUT)/emotion --stub

wer:
	$(PYTHON) -m eval.experiments.wer --config $(CONFIG) --out $(OUT)

speech:
	$(PYTHON) -m eval.speech.run_wer --out $(OUT)

latency:
	$(PYTHON) -m eval.latency.replay --out $(OUT)
	$(PYTHON) -m eval.latency.summarise --out $(OUT)

erasure:
	$(PYTHON) -m eval.experiments.erasure --config $(CONFIG) --out $(OUT)

figures:
	$(PYTHON) -m eval.experiments.figures --config $(CONFIG) --out $(OUT)
