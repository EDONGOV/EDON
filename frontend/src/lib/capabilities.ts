/**
 * Frontend-only capability detection for optional gateway endpoints.
 * Probes endpoints with X-EDON-TOKEN; 404 => false, any other status => true.
 * Never logs token.
 */

export type CapabilityKey = "timeseries" | "blockReasons";

export async function detectCapabilities(
  baseUrl: string,
  token: string
): Promise<Record<CapabilityKey, boolean>> {
  const base = baseUrl.trim().replace(/\/$/, "");
  const header = { "X-EDON-TOKEN": token };

  const check = async (url: string): Promise<boolean> => {
    try {
      const res = await fetch(url, { method: "GET", headers: header });
      return res.status !== 404;
    } catch {
      return false;
    }
  };

  const [timeseries, blockReasons] = await Promise.all([
    check(`${base}/timeseries?days=1`),
    check(`${base}/block-reasons?days=7`),
  ]);

  return { timeseries, blockReasons };
}
