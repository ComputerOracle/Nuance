// All backend-backed data (escrows, disputes, predictions, governance
// proposals, validators, agents) is fetched from the API in nuance-app.tsx
// on mount — see loadData(). Nothing here seeds UI state anymore.

// Placeholder persona names shown by consensus-panel.tsx while a consensus
// job's stage-by-stage validator results are still streaming in (before
// GET /consensus/{job_id} has returned named results to replace them).
// Mirrors VALIDATOR_NAMES in backend/app/services/consensus.py.
export const VALIDATOR_NAMES = [
  "Validator-Alpha",
  "Validator-Beta",
  "Validator-Gamma",
] as const;
