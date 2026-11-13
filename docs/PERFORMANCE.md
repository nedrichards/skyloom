# Profiling

Run measurements sequentially with other tests, using invented demo data and
ignored `build*/` output directories. Keep the window visible and use the same
backend, renderer, display, motion settings and workload for comparisons.

## Installed application

```sh
mkdir -p build-performance
flatpak run --user --command=python3 \
  --filesystem="$PWD:ro" --filesystem="$PWD/build-performance" \
  --env=PYTHONPATH=/app/share/skyloom com.nedrichards.Skyloom \
  "$PWD/scripts/performance-pass.py" --posts 250 \
  --output "$PWD/build-performance/candidate.json"
python3 scripts/compare-performance.py build-performance/baseline.json build-performance/candidate.json
```

Collect a baseline before editing and rebuild/install before the candidate.
Use `--help` for startup, scrolling, interactions, idle, reduced-motion and
plain-list control workloads. Run `--profile` separately: cProfile overhead
invalidates frame comparisons.

Focused probes in `scripts/` cover post-cell binding, label/row measurement,
media residency and thread prefetch. Their `--help` describes inputs. Construction
and retain-all modes simulate alternative ownership with current code; they are
not old-binary comparisons or compositor benchmarks.

## Interpreting results

Keep tail latency, cold construction, work counts and travelled distance alongside
frame cadence. Missing or throttled samples cannot establish improvement. Static
pages need not present continuously; a gap between presentations is not evidence
of a main-thread stall. Paint spans do not measure GPU completion. CPU/context
switches do not measure battery energy, and estimated decoded pixels are not RSS.

A fresh matched baseline is still needed for overall scrolling claims. Dense
cold views and long conversations remain priorities in [ROADMAP.md](ROADMAP.md).
Validate physical momentum under the normal renderer as well as scripted input.
