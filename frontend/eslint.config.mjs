import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // genlayer-js's CalldataEncodable / receipt / provider types are
      // intentionally loose (contract-shape-dependent); typed wrappers in
      // lib/contract.ts + lib/tx.ts document the real shapes we care about.
      "@typescript-eslint/no-explicit-any": "off",
      // Data-fetching effects (setLoans(null) before a fetch, a mounted
      // flag for client-only AppKit rendering) are a standard, deliberate
      // pattern throughout this app, not an accidental cascade.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
