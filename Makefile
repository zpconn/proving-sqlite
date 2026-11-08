# Top-level targets (GOAL.md §1.9, §3.4). Frozen with the gate at checkpoint 1.
#   make prove               every merged proof, every configuration
#   make coverage            coverage of every merged proof
#   make probe               the configuration probe
#   make gate                the full gate
#   make gate CARD=C-NN      the gate for one card and the cards whose proofs call its functions
#                            (BASE=<commit>: also require PROOF spans changed since it to be in C-NN's functions)
# Each target's last line of standard output is its RESULT line.
MAKEFLAGS += --no-print-directory
PY := python3
CARD ?=
BASE ?=
CONFIG ?= all

.PHONY: prove coverage probe gate
prove:
	@$(PY) tools/gate.py prove --config $(CONFIG)
coverage:
	@$(PY) tools/gate.py coverage --config $(CONFIG)
probe:
	@$(PY) tools/prove.py probe --config $(CONFIG)
gate:
	@$(PY) tools/gate.py gate $(if $(CARD),--card $(CARD),) $(if $(BASE),--base $(BASE),)
