# lapq

`lapq` is a small C99 experimental priority queue based on skip lists. It is
designed as a learning-augmented priority queue playground: predictions are
provided by callers as optional hints, while correctness always comes from the
ordinary comparator.

The current implementation supports generic caller-owned `void *` items,
`peek_min`, `extract_min`, predecessor/rank insertion hints, generational
handles for `decrease_key` and arbitrary removal, optional operation
statistics, deterministic tests, and a small benchmark harness.

Hints are advice, not truth. If a predecessor hint is stale, from another
queue, or simply inaccurate, the implementation falls back by correcting with
clean comparisons.

The public API uses an opaque `struct lapq` and a small `struct lapq_config`.
There is intentionally no backend vtable yet: this repo currently has one
skip-list implementation with configurable instrumentation, which keeps the C
core small while preserving room for indexed/rank-aware extensions later.

Internally, the C core is split into focused modules:

- `src/lapq.c`: public API facade and queue lifetime.
- `src/skiplist.c`: skip-list structure, insertion search, linking, unlinking,
  and invariant checks.
- `src/handles.c`: generational handle table.
- `src/stats.c`: clean-comparison and traversal instrumentation.
- `src/lapq_internal.h`: private shared definitions.

## Algorithmic status

Implemented:

- Standard skip-list priority queue with expected logarithmic insertion and
  expected constant-time minimum extraction.
- Pointer/predecessor hints corrected with clean comparisons. The hinted search
  now uses skip-list levels in both directions before refining the insertion
  position, instead of relying only on a level-0 linear correction.
- Rank hints as an experimental convenience API. At the moment, rank hints are
  converted to a starting node by walking level 0, so they are not yet the
  asymptotically strong online rank-prediction structure from the paper.
- Generational handles for `decrease_key` and arbitrary removal. The caller
  owns item storage and must update an item's key before calling
  `lapq_decrease_key`.

Not implemented yet:

- Dirty comparisons: there is only one clean comparator today.
- A vEB-like or indexed auxiliary structure for rank predictions.
- Real ML models. The Python graph/dataset layer and synthetic hint scenarios
  are present, but learned predictors are intentionally deferred until the
  dataset format and baseline measurements are stable.

Experiment reports treat clean comparisons as the primary algorithmic metric.
Wall-clock time is still recorded, but Python binding costs, hint-generation
costs, and auxiliary oracle structures can otherwise hide the effect of
predictions on the C data structure itself.

## Build

```sh
make
make test
make sanitize
make check
make benchmark
```

## Python Package

The Python package builds a CPython extension from the C core. For local
development, use a virtual environment and install the package in editable mode:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-build-isolation -e .
```

Basic usage:

```python
from lapq import PriorityQueue

queue = PriorityQueue()
queue.push(2.0, "b")
queue.push(1.0, "a")
assert queue.pop() == (1.0, "a")
```

`PriorityQueue` also exposes opaque handles for experiments: `push_handle`,
`push_with_predecessor`, `push_with_rank`, `remove`, `check_invariants`, and
instrumentation counters through `stats`. Python-facing `decrease_key` is not
exposed yet because the binding needs an explicit policy for mutating the
priority stored inside C-owned queue items.

Prediction experiments can pass opaque handles back to the C core as
predecessor hints. The C extension does not know how the prediction was
computed; it only receives the already-computed hint and validates/corrects it
with clean comparisons.

```python
from lapq import PriorityQueue

queue = PriorityQueue()
first = queue.push_handle(1.0, "a")
queue.push_with_predecessor(2.0, "b", first)
```

The first Python experiment helpers are intentionally synthetic: they are meant
to exercise the hint API before introducing real models.

```python
from lapq import run_insertion_scenario

result = run_insertion_scenario(10000, "noisy", noise=64)
print(result.stats, result.avg_error, result.max_error)
```

For graph experiments, DIMACS shortest-path graphs can be loaded into a compact
CSR representation and explored with Dijkstra. The first implementation uses
lazy duplicate queue entries; a true Python-facing `decrease_key` binding can be
added later without changing the graph/dataset layer.

```python
from lapq.datasets import collect_priority_queue_insertion_events
from lapq.dijkstra import dijkstra_lapq_hinted
from lapq.graph import load_dimacs_csr

graph = load_dimacs_csr("graphs/dimacs/USA-road-d.NY.gr")
result = dijkstra_lapq_hinted(graph, source=0, scenario="perfect")
events = collect_priority_queue_insertion_events(graph, source=0, max_events=1000)
```

The same path is available from the command line. CLI source ids are 1-based to
match DIMACS files:

```sh
python -m lapq.datasets graphs/dimacs/USA-road-d.NY.gr events.csv \
    --source 1 --max-events 100000

python -m lapq.datasets graphs/dimacs/USA-road-d.NY.gr events-ms.csv \
    --source-count 8 --source-seed 123 --max-events-per-source 50000

python -m lapq.dijkstra graphs/dimacs/USA-road-d.NY.gr \
    --source 1 --backend both --csv dijkstra.csv

python -m lapq.dijkstra graphs/dimacs/USA-road-d.NY.gr \
    --source 1 --backend lapq-hints --hint-scenario all --csv dijkstra-hints.csv

python -m lapq.analysis dijkstra.csv dijkstra-hints.csv \
    --csv dijkstra-analysis.csv

python -m lapq.analysis --queue-events events-ms.csv \
    --csv events-ms-analysis.csv

python -m lapq.replay events-ms.csv \
    --scenario heapq,baseline,perfect,noisy,bad_left --noise 64 --csv replay.csv
```

Local experiment outputs should be written under `results/`, which is ignored
by Git.

Build release artifacts with:

```sh
make package
```

This creates `dist/lapq-<version>.tar.gz` and a platform-specific wheel in
`dist/`, which can be attached to a GitHub Release. Wheels are specific to a
Python version, operating system, and architecture; CI should build the full
release matrix later.

## GitHub Releases

Release artifacts are built from Git tags. To publish a release:

```sh
git tag v0.1.0
git push origin v0.1.0
```

The release workflow builds the source distribution and wheels for CPython
3.9-3.13 on Linux, macOS, and Windows, then attaches them to a GitHub Release.
Linux wheels include `x86_64` and `aarch64`; macOS wheels include `x86_64` and
`arm64`; Windows wheels include `AMD64`.

`make benchmark` runs insertion/extraction scenarios for baseline, perfect
predecessor hints, noisy predecessor hints, bad hints from the left, bad hints
from the right, plus a `decrease_key` scenario. It reports time, clean
comparisons, level-0 and express-level steps, hint counts, invalid hints, and
average/maximum hint error. It also breaks skip-list traversal steps down by
search phase: backward correction, bottom-up expansion, and top-down refinement.
Pass a custom item count and noise value directly to the binary, for example:

```sh
build/lapq_benchmark 100000 64
build/lapq_benchmark --csv 100000 64
```

CSV columns are:

```text
scenario,n,noise,seconds,clean_cmp,level0_steps,express_steps,backward,
bottom_up,top_down,pred_hints,invalid_hints,avg_error,max_error,checksum
```

`make check` runs the deterministic test suite, the sanitizer build, and the
benchmark smoke test.
