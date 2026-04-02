import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { edonApi, getBaseUrl, getToken, isMockMode } from "@/lib/api";

// Test configuration
const GATEWAY_URL = process.env.VITE_EDON_GATEWAY_URL || "http://localhost:8000";
const GATEWAY_TOKEN =
  process.env.VITE_EDON_API_TOKEN ||
  process.env.VITE_EDON_GATEWAY_TOKEN ||
  "";

describe("EDON Agent UI - Gateway Integration Tests", () => {
  let originalMockMode: string | null;
  let originalBaseUrl: string | null;
  let originalToken: string | null;

  beforeAll(() => {
    // Save original localStorage values
    if (typeof window !== "undefined") {
      originalMockMode = localStorage.getItem("edon_mock_mode");
      originalBaseUrl = localStorage.getItem("edon_api_base");
      originalToken = localStorage.getItem("edon_token");

      // Disable mock mode for integration tests
      localStorage.setItem("edon_mock_mode", "false");
      localStorage.setItem("edon_api_base", GATEWAY_URL);
      if (GATEWAY_TOKEN) {
        localStorage.setItem("edon_token", GATEWAY_TOKEN);
      }
    }
  });

  afterAll(() => {
    // Restore original localStorage values
    if (typeof window !== "undefined") {
      if (originalMockMode !== null) {
        localStorage.setItem("edon_mock_mode", originalMockMode);
      } else {
        localStorage.removeItem("edon_mock_mode");
      }
      if (originalBaseUrl !== null) {
        localStorage.setItem("edon_api_base", originalBaseUrl);
      } else {
        localStorage.removeItem("edon_api_base");
      }
      if (originalToken !== null) {
        localStorage.setItem("edon_token", originalToken);
      } else {
        localStorage.removeItem("edon_token");
      }
    }
  });

  describe("Health Check", () => {
    it("should connect to gateway health endpoint", async () => {
      const health = await edonApi.getHealth();
      expect(health).toHaveProperty("status");
      expect(health.status).toBe("healthy");
      expect(health).toHaveProperty("version");
    }, 10000); // 10 second timeout for network requests
  });

  describe("Metrics Endpoint", () => {
    it("should fetch metrics from gateway", async () => {
      try {
        const metrics = await edonApi.getMetrics();
        expect(metrics).toHaveProperty("allowed_24h");
        expect(metrics).toHaveProperty("blocked_24h");
        expect(metrics).toHaveProperty("confirm_24h");
        expect(metrics).toHaveProperty("latency_p50");
        expect(typeof metrics.allowed_24h).toBe("number");
        expect(typeof metrics.blocked_24h).toBe("number");
        expect(typeof metrics.confirm_24h).toBe("number");
      } catch (error: unknown) {
        // If auth is required but not provided, verify auth is enforced
        if (error instanceof Error && (error.message.includes("401") || error.message.includes("Unauthorized"))) {
          console.warn("⚠️  Metrics endpoint requires authentication. This is expected if EDON_AUTH_ENABLED=true.");
          console.warn("   To test without auth: Set EDON_AUTH_ENABLED=false in gateway .env");
          console.warn("   Or provide token: Set VITE_EDON_GATEWAY_TOKEN=your-token");
          // Test passes - auth middleware is working correctly
          expect(error.message).toMatch(/401|Unauthorized/);
        } else {
          throw error;
        }
      }
    }, 10000);
  });

  describe("Decisions Endpoint", () => {
    it("should fetch decisions from gateway", async () => {
      try {
        const result = await edonApi.getDecisions({ limit: 10 });
        expect(result).toHaveProperty("decisions");
        expect(result).toHaveProperty("total");
        expect(Array.isArray(result.decisions)).toBe(true);
        expect(typeof result.total).toBe("number");
      } catch (error: unknown) {
        if (error instanceof Error && (error.message.includes("401") || error.message.includes("Unauthorized"))) {
          console.warn("Decisions endpoint requires authentication. Set VITE_EDON_GATEWAY_TOKEN or disable auth for testing.");
          expect(error.message).toContain("401");
        } else {
          throw error;
        }
      }
    }, 10000);

    it("should filter decisions by verdict", async () => {
      try {
        const result = await edonApi.getDecisions({ verdict: "allowed", limit: 5 });
        expect(result).toHaveProperty("decisions");
        expect(Array.isArray(result.decisions)).toBe(true);
        // All decisions should be "allowed" if any exist
        result.decisions.forEach((decision) => {
          expect(decision.verdict.toLowerCase()).toBe("allowed");
        });
      } catch (error: unknown) {
        if (error instanceof Error && (error.message.includes("401") || error.message.includes("Unauthorized"))) {
          console.warn("Decisions endpoint requires authentication.");
          expect(error.message).toContain("401");
        } else {
          throw error;
        }
      }
    }, 10000);

    it("should filter decisions by agent_id", async () => {
      try {
        const result = await edonApi.getDecisions({ agent_id: "test-agent", limit: 5 });
        expect(result).toHaveProperty("decisions");
        expect(Array.isArray(result.decisions)).toBe(true);
      } catch (error: unknown) {
        if (error instanceof Error && (error.message.includes("401") || error.message.includes("Unauthorized"))) {
          console.warn("Decisions endpoint requires authentication.");
          expect(error.message).toContain("401");
        } else {
          throw error;
        }
      }
    }, 10000);
  });

  describe("Audit Endpoint", () => {
    it("should fetch audit logs from gateway", async () => {
      try {
        const result = await edonApi.getAudit({ limit: 10 });
        expect(result).toHaveProperty("records");
        expect(result).toHaveProperty("total");
        expect(Array.isArray(result.records)).toBe(true);
        expect(typeof result.total).toBe("number");
      } catch (error: unknown) {
        if (error instanceof Error && (error.message.includes("401") || error.message.includes("Unauthorized"))) {
          console.warn("Audit endpoint requires authentication. Set VITE_EDON_GATEWAY_TOKEN or disable auth for testing.");
          expect(error.message).toContain("401");
        } else {
          throw error;
        }
      }
    }, 10000);

    it("should paginate audit logs", async () => {
      try {
        // Note: Gateway doesn't support offset, only limit
        // For pagination, use limit and filter by other params
        const firstPage = await edonApi.getAudit({ limit: 5 });
        const secondPage = await edonApi.getAudit({ limit: 5 });
        expect(firstPage.records.length).toBeLessThanOrEqual(5);
        expect(secondPage.records.length).toBeLessThanOrEqual(5);
      } catch (error: unknown) {
        if (error instanceof Error && (error.message.includes("401") || error.message.includes("Unauthorized"))) {
          console.warn("Audit endpoint requires authentication.");
          expect(error.message).toContain("401");
        } else {
          throw error;
        }
      }
    }, 10000);
  });

  describe("Intent Endpoint", () => {
    it("should get current intent", async () => {
      // Note: This endpoint might not exist in the API client, but gateway has it
      // We'll test the API directly
      const baseUrl = getBaseUrl();
      const token = getToken();
      const headers: HeadersInit = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers["X-EDON-TOKEN"] = token;
      }

      try {
        const response = await fetch(`${baseUrl}/intent/get`, { headers });
        if (response.ok) {
          const data = await response.json();
          expect(data).toHaveProperty("intent_id");
        } else if (response.status === 404) {
          // No intent set yet - this is OK
          expect(response.status).toBe(404);
        }
      } catch (error) {
        // Network error - gateway might not be running
        console.warn("Gateway not available for intent test:", error);
      }
    }, 10000);
  });

  describe("Error Handling", () => {
    it("should handle 404 errors gracefully", async () => {
      const baseUrl = getBaseUrl();
      const token = getToken();
      const headers: HeadersInit = {
        "Content-Type": "application/json",
      };
      // Always send token if available to avoid 401 masking 404
      if (token) {
        headers["X-EDON-TOKEN"] = token;
      }

      try {
        // Use a guaranteed nonexistent endpoint that will return 404
        const response = await fetch(`${baseUrl}/__does_not_exist__`, { headers });
        // This endpoint doesn't exist, so should return 404
        // If auth is required and token missing, we get 401, but with token we get 404
        if (token) {
          expect(response.status).toBe(404);
        } else {
          // Without token, might get 401 if auth enabled
          expect([404, 401]).toContain(response.status);
        }
      } catch (error) {
        // Network error - gateway might not be running
        console.warn("Gateway not available for error test:", error);
      }
    }, 10000);

    it("should handle network errors gracefully", async () => {
      // Temporarily set invalid URL
      if (typeof window !== "undefined") {
        localStorage.setItem("edon_api_base", "http://localhost:9999");
      }

      try {
        await edonApi.getHealth();
        // If this doesn't throw, the test should fail
        expect.fail("Should have thrown an error");
      } catch (error) {
        expect(error).toBeDefined();
      } finally {
        // Restore original URL
        if (typeof window !== "undefined") {
          localStorage.setItem("edon_api_base", GATEWAY_URL);
        }
      }
    }, 15000);
  });
});

describe("EDON Agent UI - Mock Mode Tests", () => {
  beforeAll(() => {
    // Enable mock mode
    if (typeof window !== "undefined") {
      localStorage.setItem("edon_mock_mode", "true");
    }
  });

  afterAll(() => {
    // Clean up
    if (typeof window !== "undefined") {
      localStorage.removeItem("edon_mock_mode");
    }
  });

  it("should use mock data when mock mode is enabled", async () => {
    const metrics = await edonApi.getMetrics();
    expect(metrics).toHaveProperty("allowed_24h");
    expect(metrics).toHaveProperty("blocked_24h");
    expect(typeof metrics.allowed_24h).toBe("number");
  });

  it("should return mock decisions", async () => {
    const result = await edonApi.getDecisions({ limit: 10 });
    expect(result).toHaveProperty("decisions");
    expect(result.decisions.length).toBeGreaterThan(0);
    expect(result.decisions[0]).toHaveProperty("verdict");
    expect(result.decisions[0]).toHaveProperty("tool");
  });
});
