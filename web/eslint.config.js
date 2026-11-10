import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/", "coverage/", "src/api/schema.d.ts"] },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "@typescript-eslint/no-floating-promises": [
        "error",
        // A data router's navigate() resolves when the navigation settles and never rejects: fire and forget.
        { allowForKnownSafeCalls: [{ from: "package", name: "NavigateFunction", package: "react-router" }] },
      ],
      "@typescript-eslint/no-misused-promises": "error",
      "@typescript-eslint/await-thenable": "error",
      // `const { dropped: _dropped, ...rest } = obj` is how the code omits a key.
      "@typescript-eslint/no-unused-vars": ["error", { ignoreRestSiblings: true }],
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
    },
  },
  prettier,
);
