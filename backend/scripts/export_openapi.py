"""Dump the live FastAPI app's OpenAPI schema to a JSON file — the single
source of truth `sdk/generate.sh` (repo root) feeds to both the TypeScript
(`@hey-api/openapi-ts`) and Python (`openapi-python-client`) generators, per
ROADMAP.md Part 4 6.3 ("Generated SDKs — TypeScript + Python clients off one
OpenAPI spec").

Deliberately does NOT start a server or run the app's lifespan (init_db,
the chain indexer) — `FastAPI.openapi()` builds the schema purely from the
already-registered routers/routes/Pydantic models, so importing `app.main`
and calling it is enough. Run from the `backend/` directory (or anywhere,
via `python -m scripts.export_openapi`) with the venv active:

    backend$ .venv/bin/python -m scripts.export_openapi [output_path]

Default output path is `../sdk/openapi.json` (repo_root/sdk/openapi.json),
matching where sdk/generate.sh expects to find it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Import-time side effects to guard against: app.config.get_settings() reads
# .env, which is fine (every setting has a default); nothing else at import
# time touches the DB or network. See module docstring above re: why the
# lifespan (init_db/indexer) never needs to run for this.
from app.main import app  # noqa: E402


def export_openapi_schema(output_path: Path) -> None:
    schema = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"Wrote OpenAPI schema ({len(schema.get('paths', {}))} paths) to {output_path}")


if __name__ == "__main__":
    default_output = Path(__file__).resolve().parent.parent.parent / "sdk" / "openapi.json"
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else default_output
    export_openapi_schema(output)
