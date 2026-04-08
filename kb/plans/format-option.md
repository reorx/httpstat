# Phase 1: Structured Output + SLO for httpstat

## Context

httpstat is a single-file CLI (`httpstat.py`, ~380 lines) that wraps curl to display HTTP timing metrics. Currently it has manual `sys.argv` parsing, pretty-printed output, and a `HTTPSTAT_METRICS_ONLY` env var for raw JSON dump. We're adding agent-friendly structured output (`--format json`), SLO threshold checking (`--slo`), `NO_COLOR` support, and `--save` — making httpstat consumable by automated pipelines.

## Critical files

- `httpstat.py` — the entire application (single module)
- `httpstat_test.sh` — existing E2E tests
- `tests/test_httpstat.py` — **new**, unit tests for added logic

## Implementation steps

### Step 1: Add unit test infrastructure

- Create `tests/test_httpstat.py` with pytest
- Add `uv add --dev pytest` for test dependency
- Test `parse_bool()` first (existing function, establishes the pattern)

### Step 2: `NO_COLOR` support

In `httpstat.py`:
- Check `os.environ.get('NO_COLOR')` at module level (per no-color.org, presence of the var with _any_ value disables color)
- Update `ISATTY` logic: `ISATTY = sys.stdout.isatty() and 'NO_COLOR' not in os.environ`

Test: unit test that `make_color` returns undecorated string when `NO_COLOR` is set.

### Step 3: Argument parsing for `--format`, `--slo`, `--save`

Currently args are parsed manually from `sys.argv`. Keep that style (no argparse) for consistency. Extract new flags before passing remaining args to curl:

```python
def pop_arg(args, flag, has_value=True):
    """Remove flag (and its value if has_value) from args list, return value or True/None."""
```

Parse in `main()`:
- `--format` / `-f` → `output_format` (default `"pretty"`, validate against `pretty|json|jsonl`)
- `--slo` → `slo_spec` (raw string like `"total=500,connect=100"`)
- `--save` → `save_path` (file path string)
- If `HTTPSTAT_METRICS_ONLY` is true AND no explicit `--format`, set `output_format = "json"` (backward compat)

Tests: unit tests for `pop_arg`, `parse_slo`.

### Step 4: `parse_slo()` function

```python
SLO_KEY_MAP = {
    'total': 'time_total',
    'connect': 'time_connect',
    'ttfb': 'time_starttransfer',
    'dns': 'time_namelookup',
    'tls': 'time_pretransfer',
}

def parse_slo(spec: str) -> dict[str, int]:
    """Parse 'total=500,connect=100' → {'total': 500, 'connect': 100}"""
```

Validate keys against `SLO_KEY_MAP`, values must be positive ints. Exit with error on invalid input.

Tests: valid specs, invalid keys, invalid values, empty string.

### Step 5: `check_slo()` function

```python
def check_slo(slo: dict[str, int], timings: dict) -> tuple[bool, list[dict]]:
    """Returns (pass, violations). Each violation: {'key': ..., 'threshold_ms': ..., 'actual_ms': ...}"""
```

Tests: all pass, some violations, edge cases (exactly at threshold = pass).

### Step 6: `build_json_result()` function

```python
def build_json_result(url, d, headers_text, slo_result, exit_code) -> dict:
    """Build the v1 JSON schema output dict."""
```

Parses `status_line` and `status_code` from headers_text first line.
Constructs:
```
schema_version, url, ok, exit_code,
response {status_line, status_code, remote_ip, remote_port, headers},
timings_ms {dns, connect, tls, server, transfer, total, namelookup, initial_connect, pretransfer, starttransfer},
speed {download_kbs, upload_kbs},
slo {pass, violations}
```

Tests: snapshot-style test with known input dict → expected output structure.

### Step 7: Wire it all together in `main()`

Modify `main()` flow:
1. Pop `--format`, `--slo`, `--save` from args before curl invocation (unchanged curl logic)
2. After timings are computed and ranges calculated, branch on `output_format`:
   - `"pretty"`: existing pretty-print logic (unchanged), plus SLO violation warnings at the end
   - `"json"`: call `build_json_result()`, `json.dumps(indent=2)`, print
   - `"jsonl"`: same but `json.dumps()` (compact, single line)
3. If `--slo` specified: run `check_slo()`, if failed set exit code to 4
4. If `--save` specified: write output to file
5. SLO violations in pretty mode: print red warning lines after the timing diagram

### Step 8: Update help text

Add `--format`, `--slo`, `--save` to `print_help()`. Add `NO_COLOR` to the environments section.

### Step 9: E2E test additions

Add cases to `httpstat_test.sh`:
- `--format json` produces valid JSON with `schema_version`
- `--slo total=1` triggers exit code 4 (1ms threshold will always fail)
- `--save /tmp/httpstat_test_out.json` writes file
- `NO_COLOR=1` output contains no ANSI escapes

## Verification

```bash
# Unit tests
uv run pytest tests/ -v

# E2E tests
bash httpstat_test.sh

# Manual smoke tests
python httpstat.py https://example.com
python httpstat.py https://example.com --format json
python httpstat.py https://example.com --format json --slo total=100
python httpstat.py https://example.com --format json --save /tmp/out.json
NO_COLOR=1 python httpstat.py https://example.com
```
