SHELL := /bin/bash

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../../..)
SIM ?= icarus
TOPLEVEL_LANG := verilog
TOPLEVEL := plasma_pl_loopback_axi_lite
MODULE := test_pl_loopback
VERILOG_SOURCES := \
	$(ROOT)/rtl/bus/plasma_pl_loopback_core.sv \
	$(ROOT)/rtl/bus/plasma_pl_loopback_axi_lite.sv
COMPILE_ARGS += -g2012
SIM_BUILD := $(ROOT)/build/pl-loopback-sim
export PYTHONPATH := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
