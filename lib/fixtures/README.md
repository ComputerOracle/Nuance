# Part 1 Sync Point fixtures

Live-captured responses from the real backend (not hand-typed) — safe to
`import` directly for local mocking while the real endpoints are still
being pointed at. Backend implementation: `backend/app/routers/{governance,validators,agents}.py`.

| File | Endpoint | Auth |
|---|---|---|
| `proposals.json` | `GET /proposals` | optional — `user_vote` is `null` when anonymous |
| `proposal-detail.json` | `GET /proposals/{id}` | optional, plus a `votes[]` breakdown |
| `validators.json` | `GET /validators` | none |
| `agents.json` | `GET /agents` | none |

## Things the samples won't show you

- **`status`** is `"active" \| "passed" \| "rejected" \| "executed"` — the
  fixture only shows `"active"` (nothing's old enough to finalize yet).
  Build the UI for all four; `"executed"` isn't set by anything server-side
  yet (reserved for a future action, see `ROADMAP.md` Part 1).
- **`choice` / `user_vote`** is `"for" \| "against" \| "abstain"` —
  lowercase. `POST /proposals/{id}/vote` accepts any casing on the way in
  (`"FOR"` works too) but always echoes back lowercase.
- **Re-voting flips, it doesn't stack** — `POST` the same proposal's vote
  endpoint twice with a different `choice` and the tallies move accordingly
  (see `proposals.json`: one wallet voted `for` then flipped to `against`,
  so `total_for` is back to 0).
- **`turnout_pct` / `for_pct` / `against_pct` / `abstain_pct` / `quorum_met`**
  are computed on every read, not stored — don't expect them on a raw DB
  row, only from these endpoints.
- **`validators.json` / `agents.json` can legitimately come back `[]`** on
  a fresh database — both are computed from real `ConsensusJob` history,
  there's no seed data. `cases_judged: 0` never appears in the list; an
  entry only exists once it has at least one real case.
- **404 vs empty list**: `GET /proposals/{bad_id}` 404s; `GET /proposals`
  with none created yet returns `[]`, not 404.
