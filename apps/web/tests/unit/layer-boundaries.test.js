import path from "node:path";

import { Linter } from "eslint";
import { describe, expect, it } from "vitest";

import layerBoundaries from "../../eslint-rules/layer-boundaries.js";

const webRoot = path.resolve(import.meta.dirname, "../..");
const linter = new Linter();
const config = [
  {
    files: ["**/*.{js,ts,tsx}"],
    languageOptions: { ecmaVersion: "latest", sourceType: "module" },
    plugins: {
      project: { rules: { "layer-boundaries": layerBoundaries } },
    },
    rules: { "project/layer-boundaries": "error" },
  },
];

function messagesFor(source, relativeFileName) {
  return linter.verify(source, config, {
    filename: path.resolve(webRoot, relativeFileName),
  });
}

describe("layer-boundaries", () => {
  it("allows imports in the declared downward direction", () => {
    expect(messagesFor('import "@/shared/ui/Button";', "src/features/onboarding/View.tsx")).toEqual(
      [],
    );
    expect(messagesFor('import "../features/onboarding";', "src/pages/Welcome.tsx")).toEqual([]);
  });

  it("rejects an upward import from shared", () => {
    const messages = messagesFor(
      'export * from "@/features/onboarding";',
      "src/shared/ui/index.ts",
    );

    expect(messages).toHaveLength(1);
    expect(messages[0].ruleId).toBe("project/layer-boundaries");
  });

  it("rejects imports between sibling features", () => {
    const messages = messagesFor(
      'import "../../protected-transfer/model";',
      "src/features/risk-warning/model/state.ts",
    );

    expect(messages).toHaveLength(1);
    expect(messages[0].message).toContain("features -> shared");
  });
});
