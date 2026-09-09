import { defineConfig } from "@hey-api/openapi-ts";

// Generates the TypeScript client straight from the exported OpenAPI spec
// (../openapi.json — see ../../backend/scripts/export_openapi.py and
// ../generate.sh, the single place both this and the Python client are
// regenerated from). Output lands in src/generated/ and is checked in
// (see README.md) so `npm install @nuance/sdk` works without a build step,
// same reasoning src/client.ts's own docstring gives for shipping the
// generated output rather than requiring consumers to run codegen
// themselves.
export default defineConfig({
  input: "../openapi.json",
  output: "src/generated",
  plugins: [
    "@hey-api/typescript",
    "@hey-api/sdk",
    {
      name: "@hey-api/client-fetch",
      // No baseUrl baked in — src/client.ts's createNuanceClient sets it
      // per-instance (staging vs. Bradbury-backed prod backend vs. a local
      // dev server), matching how the API key/JWT are also supplied
      // per-instance rather than hardcoded at generation time.
    },
  ],
});
