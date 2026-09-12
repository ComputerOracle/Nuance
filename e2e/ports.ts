// Shared between playwright.config.ts (webServer definitions) and any
// spec that needs to reach the backend directly (e.g. a raw API call as
// a *second* wallet identity the injected mock-wallet.ts can't represent
// at the same time as the first) — one place these two numbers live,
// rather than a magic-number duplicate risking silent drift between them.
export const BACKEND_PORT = 8099;
export const FRONTEND_PORT = 3100;
