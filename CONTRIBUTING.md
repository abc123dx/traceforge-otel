# Contributing to TraceForge

Thanks for helping make agent traces easier to understand.

## Set up

```bash
git clone https://github.com/abc123dx/traceforge-otel.git
cd traceforge-otel
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Before opening a pull request:

```bash
ruff check .
ruff format --check .
mypy
pytest
traceforge demo
```

## Design principles

1. **Local first.** Core analysis must not require an account, collector, or network request.
2. **Evidence over guesses.** Findings should link back to concrete spans and documented
   heuristics.
3. **Never lose input.** Parser compatibility should be additive and preserve unknown
   attributes.
4. **Stable automation.** Treat the JSON schema as an API; discuss breaking changes first.
5. **Honest cost.** Do not hard-code vendor pricing without a maintenance and versioning plan.

## Pull requests

Keep changes focused, add tests for new behavior, and update examples or documentation when the
user-visible contract changes. New semantic-convention aliases should include a fixture showing
their exporter representation.

Use synthetic trace data only. Never commit production traces, prompts, API keys, personal data,
or customer identifiers.
