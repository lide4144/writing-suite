import { describe, expect, it } from "vitest";

import { appBuild, isAutomationMode } from "./app-build";

describe("M1 app build contract", () => {
  it("contains a public version, schema, and commit marker", () => {
    expect(appBuild.version).toBeTruthy();
    expect(appBuild.schema).toBe("m1");
    expect(appBuild.commit).toBeTruthy();
  });

  it("recognizes automation mode from the URL query", () => {
    expect(isAutomationMode("automation=1")).toBe(true);
    expect(isAutomationMode("automation=0")).toBe(false);
  });
});
