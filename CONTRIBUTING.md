# Contributing

PRs stay narrow. Match the files around the change.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

## Style

Prefer the stdlib. Catalog prices are integer cents. Don't mix formatting-only diffs with behavior.

## Commits

Imperative subject, under 72 characters.
