CC ?= gcc
AR ?= ar
CFLAGS ?= -std=c99 -Wall -Wextra -pedantic -O2
CPPFLAGS ?= -Iinclude
BUILD_DIR ?= build
TEST_ENV ?=
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
JUPYTER ?= $(if $(wildcard .venv/bin/jupyter),.venv/bin/jupyter,jupyter)

LIB := $(BUILD_DIR)/liblapq.a
OBJ := \
	$(BUILD_DIR)/src/lapq.o \
	$(BUILD_DIR)/src/skiplist.o \
	$(BUILD_DIR)/src/handles.o \
	$(BUILD_DIR)/src/stats.o
DOCS_DIR := docs
REPORT_BASENAME := lapq-lib
REPORT_NOTEBOOK := $(DOCS_DIR)/$(REPORT_BASENAME).ipynb
REPORT_PDF := $(DOCS_DIR)/$(REPORT_BASENAME).pdf
REPORT_TEMPLATE := $(DOCS_DIR)/templates/academic-paper.tex.j2

.PHONY: all test sanitize python-test check benchmark package docs clean

all: $(LIB)

$(BUILD_DIR)/src:
	mkdir -p $@

$(BUILD_DIR)/src/%.o: src/%.c src/lapq_internal.h include/lapq/lapq.h | $(BUILD_DIR)/src
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

$(LIB): $(OBJ)
	rm -f $@
	$(AR) rcs $@ $^

$(BUILD_DIR)/lapq_test: tests/lapq_test.c $(LIB)
	$(CC) $(CPPFLAGS) $(CFLAGS) tests/lapq_test.c $(LIB) -o $@

test: $(BUILD_DIR)/lapq_test
	$(TEST_ENV) $<

sanitize:
	$(MAKE) BUILD_DIR=$(BUILD_DIR)/sanitize CFLAGS='-std=c99 -Wall -Wextra -pedantic -fsanitize=address,undefined -g' TEST_ENV='ASAN_OPTIONS=detect_leaks=0' test

python-test:
	$(PYTHON) -m pip install --no-build-isolation -e .
	$(PYTHON) -m pytest tests/python

check: test sanitize python-test benchmark

$(BUILD_DIR)/lapq_benchmark: benchmarks/lapq_benchmark.c $(LIB)
	$(CC) $(CPPFLAGS) $(CFLAGS) benchmarks/lapq_benchmark.c $(LIB) -o $@

benchmark: $(BUILD_DIR)/lapq_benchmark
	$< 100000

package:
	rm -rf dist
	$(PYTHON) -m build --no-isolation

docs: $(REPORT_PDF)

$(REPORT_PDF): $(REPORT_NOTEBOOK) $(DOCS_DIR)/references.bib $(REPORT_TEMPLATE)
	$(JUPYTER) nbconvert $< --to pdf --template-file $(REPORT_TEMPLATE) --no-prompt --TagRemovePreprocessor.enabled=True --TagRemovePreprocessor.remove_input_tags='["hide"]' --output $(REPORT_BASENAME) --output-dir $(DOCS_DIR)

clean:
	rm -rf $(BUILD_DIR)
