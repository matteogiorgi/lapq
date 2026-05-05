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
- Python bindings and ML experiments. The intended split is a small C core for
  the data structure and Python code for predictions, datasets, and plots.

## Build

```sh
make
make test
make sanitize
make check
make benchmark
```

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
