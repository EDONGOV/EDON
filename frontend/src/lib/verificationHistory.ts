/**
 * Lightweight persistence for Governance Verification Test results.
 * localStorage key: edon_verification_history. Append-only, cap at 50 entries.
 */

const STORAGE_KEY = "edon_verification_history";
const MAX_ENTRIES = 50;

export type VerificationHistoryRecord = {
  timestamp: string;
  allow_pack: string;
  block_pack: string;
  tool_op: string;
  agent_id: string;
  verdict_allow: string;
  verdict_block: string;
  pass: boolean;
  intent_id_allow?: string;
  intent_id_block?: string;
  latency_allow_ms?: number;
  latency_block_ms?: number;
  gateway_version?: string;
};

export function getVerificationHistory(): VerificationHistoryRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed as VerificationHistoryRecord[];
  } catch {
    return [];
  }
}

export function appendVerificationRecord(record: VerificationHistoryRecord): void {
  if (typeof window === "undefined") return;
  try {
    const list = getVerificationHistory();
    list.unshift(record);
    const capped = list.slice(0, MAX_ENTRIES);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(capped));
  } catch (e) {
    console.warn("Verification history persistence failed", e);
  }
}
