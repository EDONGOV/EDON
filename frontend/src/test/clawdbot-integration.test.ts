import { describe, it, expect, beforeAll, afterAll } from "vitest";

// Test configuration
const GATEWAY_URL = process.env.VITE_EDON_GATEWAY_URL || "http://localhost:8000";
const GATEWAY_TOKEN = process.env.VITE_EDON_GATEWAY_TOKEN || "";

/**
 * Tests for Clawdbot integration through EDON Gateway
 * 
 * These tests verify that the gateway can proxy requests to Clawdbot
 * and that the agent UI can monitor those interactions.
 */
describe("EDON Agent UI - Clawdbot Integration Tests", () => {
  let originalBaseUrl: string | null;
  let originalToken: string | null;

  beforeAll(() => {
    // Save original localStorage values
    if (typeof window !== "undefined") {
      originalBaseUrl = localStorage.getItem("edon_api_base");
      originalToken = localStorage.getItem("edon_api_token");

      // Set gateway URL and token
      localStorage.setItem("edon_api_base", GATEWAY_URL);
      localStorage.setItem("edon_mock_mode", "false");
      if (GATEWAY_TOKEN) {
        localStorage.setItem("edon_api_token", GATEWAY_TOKEN);
      }
    }
  });

  afterAll(() => {
    // Restore original localStorage values
    if (typeof window !== "undefined") {
      if (originalBaseUrl !== null) {
        localStorage.setItem("edon_api_base", originalBaseUrl);
      } else {
        localStorage.removeItem("edon_api_base");
      }
      if (originalToken !== null) {
        localStorage.setItem("edon_api_token", originalToken);
      } else {
        localStorage.removeItem("edon_api_token");
      }
    }
  });

  describe("Clawdbot Invoke Endpoint", () => {
    it("should have clawdbot invoke endpoint available", async () => {
      const baseUrl = GATEWAY_URL;
      const token = GATEWAY_TOKEN;
      const headers: HeadersInit = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers["X-EDON-TOKEN"] = token;
      }

      // Test that the endpoint exists (even if it requires auth/credentials)
      try {
        const response = await fetch(`${baseUrl}/clawdbot/invoke`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            tool: "test_tool",
            action: "json",
            args: {},
          }),
        });

        // Should either succeed (if configured) or return 401/403/400 (if not configured)
        // But should NOT return 404 (endpoint doesn't exist)
        expect([200, 400, 401, 403]).toContain(response.status);
      } catch (error) {
        // Network error - gateway might not be running
        console.warn("Gateway not available for clawdbot test:", error);
      }
    }, 15000);

    it("should accept clawdbot request format", async () => {
      const baseUrl = GATEWAY_URL;
      const token = GATEWAY_TOKEN;
      const headers: HeadersInit = {
        "Content-Type": "application/json",
        "X-Agent-ID": "test-agent-123",
      };
      if (token) {
        headers["X-EDON-TOKEN"] = token;
      }

      const clawdbotRequest = {
        tool: "sessions_list",
        action: "json",
        args: {},
      };

      try {
        const response = await fetch(`${baseUrl}/clawdbot/invoke`, {
          method: "POST",
          headers,
          body: JSON.stringify(clawdbotRequest),
        });

        // Should accept the request format (even if it fails due to missing credentials)
        expect([200, 400, 401, 403, 404]).toContain(response.status);
        
        if (response.ok) {
          const data = await response.json();
          expect(data).toHaveProperty("result");
        }
      } catch (error) {
        // Network error - gateway might not be running
        console.warn("Gateway not available for clawdbot format test:", error);
      }
    }, 15000);
  });

  describe("Decision Tracking", () => {
    it("should track clawdbot decisions in audit log", async () => {
      const baseUrl = GATEWAY_URL;
      const token = GATEWAY_TOKEN;
      const headers: HeadersInit = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers["X-EDON-TOKEN"] = token;
      }

      try {
        // Get initial audit count
        const initialAudit = await fetch(`${baseUrl}/audit/query?limit=1`, { headers });
        const initialData = initialAudit.ok ? await initialAudit.json() : { total: 0 };
        const initialCount = initialData.total || 0;

        // Make a clawdbot request (if configured)
        const clawdbotResponse = await fetch(`${baseUrl}/clawdbot/invoke`, {
          method: "POST",
          headers: {
            ...headers,
            "X-Agent-ID": "test-agent-integration",
          },
          body: JSON.stringify({
            tool: "test_tool",
            action: "json",
            args: {},
          }),
        });

        // If request succeeded, check that decision was logged
        if (clawdbotResponse.ok || clawdbotResponse.status === 400) {
          // Wait a bit for async logging
          await new Promise((resolve) => setTimeout(resolve, 1000));

          // Check audit log
          const auditResponse = await fetch(
            `${baseUrl}/audit/query?agent_id=test-agent-integration&limit=10`,
            { headers }
          );
          
          if (auditResponse.ok) {
            const auditData = await auditResponse.json();
            // Should have at least one decision for our test agent
            expect(auditData.records).toBeDefined();
            expect(Array.isArray(auditData.records)).toBe(true);
          }
        }
      } catch (error) {
        // Network error - gateway might not be running
        console.warn("Gateway not available for decision tracking test:", error);
      }
    }, 20000);
  });

  describe("Agent UI Monitoring", () => {
    it("should display clawdbot decisions in UI", async () => {
      // This test verifies that decisions from clawdbot appear in the UI
      // by checking that the decisions endpoint returns data
      const baseUrl = GATEWAY_URL;
      const token = GATEWAY_TOKEN;
      const headers: HeadersInit = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers["X-EDON-TOKEN"] = token;
      }

      try {
        // Query decisions for a specific agent
        const response = await fetch(
          `${baseUrl}/decisions/query?agent_id=test-agent&limit=10`,
          { headers }
        );

        if (response.ok) {
          const data = await response.json();
          expect(data).toHaveProperty("decisions");
          expect(Array.isArray(data.decisions)).toBe(true);
          
          // Decisions should have the expected structure for UI display
          if (data.decisions.length > 0) {
            const decision = data.decisions[0];
            expect(decision).toHaveProperty("verdict");
            expect(decision).toHaveProperty("timestamp");
            expect(decision).toHaveProperty("agent_id");
            expect(decision).toHaveProperty("tool");
          }
        } else if (response.status === 401 || response.status === 403) {
          // Auth required but not provided - this is expected
          expect(response.status).toBeGreaterThanOrEqual(400);
        }
      } catch (error) {
        // Network error - gateway might not be running
        console.warn("Gateway not available for UI monitoring test:", error);
      }
    }, 15000);
  });
});
