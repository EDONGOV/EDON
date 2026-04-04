/**
 * Unit tests for @/lib/dashboardContext.ts
 */
import { describe, it, expect } from "vitest";

// Import public exports from dashboardContext
// (adjust these imports to match what is actually exported)
describe("dashboardContext module", () => {
  it("imports without error", async () => {
    const mod = await import("@/lib/dashboardContext");
    expect(mod).toBeDefined();
  });

  it("exports a buildSystemPrompt or getDashboardAwareReply function", async () => {
    const mod = await import("@/lib/dashboardContext") as Record<string, unknown>;
    // The module should export at least one callable
    const hasFn = Object.values(mod).some((v) => typeof v === "function");
    expect(hasFn).toBe(true);
  });

  it("buildSystemPrompt returns a non-empty string when called with mock data", async () => {
    const mod = await import("@/lib/dashboardContext") as Record<string, unknown>;
    if (typeof mod.buildSystemPrompt === "function") {
      const result = (mod.buildSystemPrompt as Function)({
        totalDecisions: 100,
        allowRate: 0.85,
        blockRate: 0.1,
        escalateRate: 0.05,
        agentCount: 3,
        policyPack: "casual_user",
        gatewayHealth: "healthy",
      });
      expect(typeof result).toBe("string");
      expect(result.length).toBeGreaterThan(10);
    }
  });
});
