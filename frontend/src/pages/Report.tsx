import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { edonApi } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ReportFinding {
  finding_id: string;
  finding_number: number;
  severity: "critical" | "high" | "medium";
  severity_score: number;
  plain_title: string;
  executive_summary: string;
  dollar_impact: number;
  dollar_label: string;
  primary_fix: string;
  vulnerability_class: string;
  data_classes: string[];
  is_external_sink: boolean;
  verified: boolean;
  exploitability_window: string;
  proof_chain: Array<{
    step: number;
    actor: string;
    action: string;
    target: string;
    rule_violated: string;
    consequence: string;
    is_critical: boolean;
  }>;
  proof_summary: string;
  rules_violated: string[];
  entry_point: string;
  final_outcome: string;
  evidence_trace_ids: string[];
  attack_narrative: string;
  attacker_type: string;
  indicators_of_compromise: string[];
  remediation_steps: string[];
}

interface ReportPayload {
  report_id: string;
  tenant_id: string | null;
  generated_at: string;
  engagement_label: string;
  headline: {
    total_risk_usd: number;
    findings_count: number;
    critical_count: number;
    high_count: number;
    confirmed_exploits: number;
    data_classes_at_risk: string[];
    engagement_days: number;
  };
  impact: {
    risk_prevented_usd: number;
    breach_cost_prevented: number;
    compliance_fine_prevented: number;
    downtime_prevented_usd: number;
    incidents_avoided: number;
    open_critical: number;
    open_high: number;
  };
  findings: ReportFinding[];
  close: {
    total_risk_usd: number;
    edon_annual_est: number;
    roi_multiple: number;
    roi_label: string;
    next_step: string;
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

function severityColor(s: string) {
  if (s === "critical") return { bg: "#1a0505", border: "#c0392b", badge: "#e74c3c", text: "#ff6b6b" };
  if (s === "high")     return { bg: "#1a0f00", border: "#c07000", badge: "#e67e22", text: "#f39c12" };
  return                       { bg: "#0a0f1a", border: "#2980b9", badge: "#3498db", text: "#5dade2" };
}

function exploitabilityLabel(w: string): string {
  if (w === "immediate") return "Exploitable now";
  if (w === "session")   return "Exploitable this session";
  if (w === "persistent") return "Persistent exposure";
  if (w === "latent")    return "Latent — triggered under conditions";
  return w;
}

// ── Animated counter ──────────────────────────────────────────────────────────

function AnimatedNumber({ value, prefix = "", suffix = "", duration = 1400 }: {
  value: number; prefix?: string; suffix?: string; duration?: number;
}) {
  const [display, setDisplay] = useState(0);
  const start = useRef(Date.now());

  useEffect(() => {
    start.current = Date.now();
    const tick = () => {
      const elapsed = Date.now() - start.current;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.floor(eased * value));
      if (progress < 1) requestAnimationFrame(tick);
      else setDisplay(value);
    };
    requestAnimationFrame(tick);
  }, [value, duration]);

  const formatted = display >= 1_000_000
    ? `${(display / 1_000_000).toFixed(1)}M`
    : display >= 1_000
    ? `${(display / 1_000).toFixed(0)}K`
    : display.toLocaleString();

  return <span>{prefix}{formatted}{suffix}</span>;
}

// ── Print styles injected into <head> ────────────────────────────────────────

const PRINT_CSS = `
@media print {
  body { background: white !important; color: black !important; }
  .no-print { display: none !important; }
  .page-break { page-break-after: always; }
  .report-cover { background: #0a0a0f !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
@page { margin: 0.5in; size: letter; }
`;

// ── Component ─────────────────────────────────────────────────────────────────

export default function Report() {
  const [params] = useSearchParams();
  const tenantId = params.get("tenant") ?? undefined;
  const topN = parseInt(params.get("top") ?? "10");

  const [report, setReport] = useState<ReportPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedFinding, setExpandedFinding] = useState<string | null>(null);

  useEffect(() => {
    const style = document.createElement("style");
    style.textContent = PRINT_CSS;
    document.head.appendChild(style);
    return () => document.head.removeChild(style);
  }, []);

  useEffect(() => {
    setLoading(true);
    edonApi.getProofReport({ tenant_id: tenantId, top_n: topN })
      .then(setReport)
      .catch(e => setError(e.message ?? "Failed to load report"))
      .finally(() => setLoading(false));
  }, [tenantId, topN]);

  if (loading) return (
    <div style={{ minHeight: "100vh", background: "#0a0a0f", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center", color: "#666" }}>
        <div style={{ fontSize: 13, letterSpacing: "0.2em", textTransform: "uppercase", marginBottom: 8 }}>
          Assembling report
        </div>
        <div style={{ width: 200, height: 2, background: "#1a1a2e", borderRadius: 1, overflow: "hidden" }}>
          <div style={{ width: "60%", height: "100%", background: "#e74c3c", animation: "slide 1.2s ease-in-out infinite" }} />
        </div>
      </div>
    </div>
  );

  if (error || !report) return (
    <div style={{ minHeight: "100vh", background: "#0a0a0f", display: "flex", alignItems: "center", justifyContent: "center", color: "#e74c3c" }}>
      {error ?? "No report data"}
    </div>
  );

  const { headline, findings, close } = report;

  return (
    <div style={{ background: "#0a0a0f", minHeight: "100vh", fontFamily: "'Inter', -apple-system, sans-serif", color: "#e8e8e8" }}>

      {/* Print button */}
      <div className="no-print" style={{
        position: "fixed", top: 16, right: 16, zIndex: 100,
        display: "flex", gap: 8,
      }}>
        <button
          onClick={() => window.print()}
          style={{
            background: "#1a1a2e", border: "1px solid #333", color: "#ccc",
            padding: "8px 16px", borderRadius: 6, cursor: "pointer", fontSize: 13,
          }}
        >
          Export PDF
        </button>
      </div>

      {/* ── COVER PAGE ── */}
      <div className="report-cover page-break" style={{
        minHeight: "100vh", background: "linear-gradient(135deg, #0a0a0f 0%, #0f0a1a 50%, #0a0f0a 100%)",
        display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center",
        padding: "80px 40px", textAlign: "center",
        borderBottom: "1px solid #1a1a2e",
      }}>
        {/* EDON mark */}
        <div style={{ marginBottom: 48 }}>
          <div style={{ fontSize: 11, letterSpacing: "0.4em", color: "#e74c3c", textTransform: "uppercase", marginBottom: 8 }}>
            EDON · AI Risk Assessment
          </div>
          <div style={{ width: 40, height: 1, background: "#e74c3c", margin: "0 auto" }} />
        </div>

        {/* The number */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 13, color: "#888", letterSpacing: "0.1em", marginBottom: 16, textTransform: "uppercase" }}>
            Total preventable exposure identified
          </div>
          <div style={{
            fontSize: "clamp(56px, 8vw, 96px)", fontWeight: 700,
            color: "#e74c3c", lineHeight: 1, letterSpacing: "-0.02em",
          }}>
            <AnimatedNumber value={headline.total_risk_usd} prefix="$" />
          </div>
        </div>

        {/* Stats row */}
        <div style={{ display: "flex", gap: 40, marginBottom: 48, flexWrap: "wrap", justifyContent: "center" }}>
          {[
            { label: "Findings", value: headline.findings_count },
            { label: "Critical", value: headline.critical_count, color: "#e74c3c" },
            { label: "Confirmed in traffic", value: headline.confirmed_exploits },
            { label: "Days of analysis", value: headline.engagement_days },
          ].map(s => (
            <div key={s.label} style={{ textAlign: "center" }}>
              <div style={{ fontSize: 32, fontWeight: 700, color: s.color ?? "#fff", lineHeight: 1 }}>
                {s.value}
              </div>
              <div style={{ fontSize: 12, color: "#555", marginTop: 4, textTransform: "uppercase", letterSpacing: "0.1em" }}>
                {s.label}
              </div>
            </div>
          ))}
        </div>

        {/* Data classes at risk */}
        {headline.data_classes_at_risk.length > 0 && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center", marginBottom: 48 }}>
            {headline.data_classes_at_risk.map(dc => (
              <span key={dc} style={{
                background: "#1a0505", border: "1px solid #4a1010",
                color: "#ff6b6b", padding: "4px 10px", borderRadius: 4, fontSize: 12,
                fontFamily: "monospace",
              }}>{dc}</span>
            ))}
          </div>
        )}

        {/* Report meta */}
        <div style={{ fontSize: 12, color: "#333", marginTop: "auto" }}>
          <span>{report.report_id}</span>
          <span style={{ margin: "0 12px" }}>·</span>
          <span>{new Date(report.generated_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}</span>
          {report.tenant_id && (
            <>
              <span style={{ margin: "0 12px" }}>·</span>
              <span>{report.tenant_id}</span>
            </>
          )}
        </div>
      </div>

      {/* ── EXECUTIVE SUMMARY ── */}
      <div className="page-break" style={{ maxWidth: 900, margin: "0 auto", padding: "80px 40px" }}>
        <div style={{ fontSize: 11, letterSpacing: "0.3em", color: "#555", textTransform: "uppercase", marginBottom: 24 }}>
          Executive Summary
        </div>
        <h2 style={{ fontSize: 28, fontWeight: 600, color: "#fff", marginBottom: 32, lineHeight: 1.3 }}>
          We found {headline.findings_count} verified exploit path{headline.findings_count !== 1 ? "s" : ""} in your AI systems.
          None of them are theoretical.
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 48 }}>
          {[
            { label: "Total exposure identified", value: formatMoney(headline.total_risk_usd), color: "#e74c3c" },
            { label: "Critical findings", value: String(headline.critical_count), color: "#e74c3c" },
            { label: "High findings", value: String(headline.high_count), color: "#e67e22" },
            { label: "Confirmed in live traffic", value: String(headline.confirmed_exploits), color: "#2ecc71" },
          ].map(m => (
            <div key={m.label} style={{
              background: "#0f0f1a", border: "1px solid #1a1a2e",
              borderRadius: 8, padding: "20px 24px",
            }}>
              <div style={{ fontSize: 28, fontWeight: 700, color: m.color, lineHeight: 1 }}>{m.value}</div>
              <div style={{ fontSize: 12, color: "#555", marginTop: 6, textTransform: "uppercase", letterSpacing: "0.08em" }}>{m.label}</div>
            </div>
          ))}
        </div>

        <p style={{ fontSize: 16, color: "#aaa", lineHeight: 1.7, marginBottom: 16 }}>
          Every finding in this report was identified from observed behavior in your AI execution graph.
          Each represents a path an attacker — or a malfunctioning agent — can take to cause real damage.
          The dollar figures are derived from industry breach cost benchmarks applied to your specific data classes and system exposure.
        </p>
        <p style={{ fontSize: 16, color: "#aaa", lineHeight: 1.7 }}>
          No current policy blocks any of the paths below.
        </p>
      </div>

      {/* ── FINDINGS ── */}
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "0 40px 80px" }}>
        <div style={{ fontSize: 11, letterSpacing: "0.3em", color: "#555", textTransform: "uppercase", marginBottom: 32 }}>
          Findings — {findings.length} verified exploit path{findings.length !== 1 ? "s" : ""}
        </div>

        {findings.map((f, i) => {
          const colors = severityColor(f.severity);
          const isExpanded = expandedFinding === f.finding_id;
          const isLast = i === findings.length - 1;

          return (
            <div key={f.finding_id} style={{
              background: colors.bg, border: `1px solid ${colors.border}`,
              borderRadius: 8, marginBottom: isLast ? 0 : 16,
              overflow: "hidden",
            }}>
              {/* Finding header — always visible */}
              <div
                style={{ padding: "24px 28px", cursor: "pointer", userSelect: "none" }}
                onClick={() => setExpandedFinding(isExpanded ? null : f.finding_id)}
              >
                <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
                  {/* Severity badge */}
                  <div style={{ flexShrink: 0 }}>
                    <div style={{
                      background: colors.badge, color: "#fff",
                      padding: "3px 8px", borderRadius: 4, fontSize: 11,
                      fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em",
                    }}>
                      {f.severity}
                    </div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: colors.text, marginTop: 8, lineHeight: 1 }}>
                      #{f.finding_number.toString().padStart(2, "0")}
                    </div>
                  </div>

                  {/* Title + summary */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 17, fontWeight: 600, color: "#fff", marginBottom: 8, lineHeight: 1.3 }}>
                      {f.plain_title}
                    </div>
                    <div style={{ fontSize: 14, color: "#999", lineHeight: 1.5 }}>
                      {f.executive_summary}
                    </div>
                    {/* Tags */}
                    <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                      {f.verified && (
                        <span style={{ background: "#0a1a0f", border: "1px solid #1a4a2a", color: "#2ecc71", padding: "2px 8px", borderRadius: 3, fontSize: 11 }}>
                          Confirmed in traffic
                        </span>
                      )}
                      <span style={{ background: "#1a1a2e", border: "1px solid #2a2a4a", color: "#7986cb", padding: "2px 8px", borderRadius: 3, fontSize: 11 }}>
                        {exploitabilityLabel(f.exploitability_window)}
                      </span>
                      {f.data_classes.map(dc => (
                        <span key={dc} style={{ background: "#1a0a0a", border: "1px solid #3a1a1a", color: "#e57373", padding: "2px 8px", borderRadius: 3, fontSize: 11, fontFamily: "monospace" }}>
                          {dc}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Dollar + expand */}
                  <div style={{ flexShrink: 0, textAlign: "right" }}>
                    <div style={{ fontSize: 22, fontWeight: 700, color: colors.text, lineHeight: 1 }}>
                      {formatMoney(f.dollar_impact)}
                    </div>
                    <div style={{ fontSize: 11, color: "#555", marginTop: 4 }}>exposure</div>
                    <div style={{ fontSize: 11, color: "#444", marginTop: 8 }}>
                      {isExpanded ? "▲ collapse" : "▼ expand"}
                    </div>
                  </div>
                </div>
              </div>

              {/* Expanded detail */}
              {isExpanded && (
                <div style={{ borderTop: `1px solid ${colors.border}`, padding: "24px 28px" }}>

                  {/* Exploit chain */}
                  {f.proof_chain.length > 0 && (
                    <div style={{ marginBottom: 28 }}>
                      <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "#555", textTransform: "uppercase", marginBottom: 16 }}>
                        Exploit Chain
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {f.proof_chain.map(step => (
                          <div key={step.step} style={{
                            background: step.is_critical ? "#1a0505" : "#0f0f1a",
                            border: `1px solid ${step.is_critical ? "#4a1010" : "#1a1a2e"}`,
                            borderRadius: 6, padding: "12px 16px",
                            borderLeft: step.is_critical ? "3px solid #e74c3c" : "3px solid #1a1a2e",
                          }}>
                            <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                              <span style={{ fontSize: 11, color: "#555", flexShrink: 0, marginTop: 1 }}>
                                Step {step.step}
                              </span>
                              <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 13, color: step.is_critical ? "#ff6b6b" : "#ccc", fontWeight: step.is_critical ? 600 : 400 }}>
                                  {step.action}
                                </div>
                                <div style={{ fontSize: 11, color: "#555", marginTop: 4 }}>
                                  <span style={{ color: "#444" }}>No rule: </span>{step.rule_violated}
                                </div>
                                <div style={{ fontSize: 11, color: "#666", marginTop: 2 }}>
                                  <span style={{ color: "#444" }}>Enables: </span>{step.consequence}
                                </div>
                              </div>
                            </div>
                            {step.is_critical && (
                              <div style={{ marginTop: 8, fontSize: 11, fontWeight: 700, color: "#e74c3c", letterSpacing: "0.1em" }}>
                                ▶ EXPLOIT SUCCEEDS HERE
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Attack narrative */}
                  {f.attack_narrative && (
                    <div style={{ marginBottom: 28 }}>
                      <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "#555", textTransform: "uppercase", marginBottom: 12 }}>
                        Attack Scenario
                      </div>
                      <div style={{ fontSize: 13, color: "#aaa", lineHeight: 1.6, background: "#0f0f1a", border: "1px solid #1a1a2e", borderRadius: 6, padding: "12px 16px" }}>
                        {f.attack_narrative}
                      </div>
                    </div>
                  )}

                  {/* Fix */}
                  <div style={{ marginBottom: 28 }}>
                    <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "#555", textTransform: "uppercase", marginBottom: 12 }}>
                      Recommended Fix
                    </div>
                    <div style={{
                      background: "#0a150a", border: "1px solid #1a3a1a",
                      borderRadius: 6, padding: "12px 16px",
                      fontSize: 13, color: "#a8d5a2", lineHeight: 1.5,
                    }}>
                      {f.primary_fix}
                    </div>
                  </div>

                  {/* Indicators */}
                  {f.indicators_of_compromise.length > 0 && (
                    <div style={{ marginBottom: 16 }}>
                      <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "#555", textTransform: "uppercase", marginBottom: 12 }}>
                        Indicators to Watch
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {f.indicators_of_compromise.map((ioc, idx) => (
                          <div key={idx} style={{ fontSize: 12, color: "#888", display: "flex", gap: 8 }}>
                            <span style={{ color: "#444" }}>—</span>
                            <span>{ioc}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Evidence */}
                  {f.evidence_trace_ids.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "#444", textTransform: "uppercase", marginBottom: 8 }}>
                        Evidence Traces
                      </div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {f.evidence_trace_ids.slice(0, 6).map(tid => (
                          <span key={tid} style={{
                            fontFamily: "monospace", fontSize: 10, color: "#555",
                            background: "#0f0f1a", border: "1px solid #1a1a2e",
                            padding: "2px 6px", borderRadius: 3,
                          }}>{tid.slice(0, 16)}…</span>
                        ))}
                        {f.evidence_trace_ids.length > 6 && (
                          <span style={{ fontSize: 10, color: "#444" }}>+{f.evidence_trace_ids.length - 6} more</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── CLOSE SLIDE ── */}
      <div style={{
        background: "linear-gradient(135deg, #0a0a0f 0%, #0f0505 100%)",
        borderTop: "1px solid #1a0505",
        padding: "80px 40px",
        textAlign: "center",
      }}>
        <div style={{ maxWidth: 700, margin: "0 auto" }}>
          <div style={{ fontSize: 11, letterSpacing: "0.3em", color: "#555", textTransform: "uppercase", marginBottom: 24 }}>
            What this means
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24, marginBottom: 48 }}>
            <div style={{ background: "#0f0f1a", border: "1px solid #1a1a2e", borderRadius: 8, padding: "28px 20px" }}>
              <div style={{ fontSize: 13, color: "#555", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.08em" }}>Risk found</div>
              <div style={{ fontSize: 32, fontWeight: 700, color: "#e74c3c" }}>{formatMoney(close.total_risk_usd)}</div>
            </div>
            <div style={{ background: "#0f0f1a", border: "1px solid #1a1a2e", borderRadius: 8, padding: "28px 20px" }}>
              <div style={{ fontSize: 13, color: "#555", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.08em" }}>EDON / year</div>
              <div style={{ fontSize: 32, fontWeight: 700, color: "#fff" }}>{formatMoney(close.edon_annual_est)}</div>
            </div>
            <div style={{ background: "#0a150a", border: "1px solid #1a3a1a", borderRadius: 8, padding: "28px 20px" }}>
              <div style={{ fontSize: 13, color: "#555", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.08em" }}>ROI</div>
              <div style={{ fontSize: 32, fontWeight: 700, color: "#2ecc71" }}>{close.roi_multiple}x</div>
            </div>
          </div>

          <p style={{ fontSize: 16, color: "#888", marginBottom: 8 }}>{close.roi_label}</p>
          <p style={{ fontSize: 14, color: "#555", marginBottom: 48, lineHeight: 1.6 }}>{close.next_step}</p>

          <div style={{ fontSize: 12, color: "#333", letterSpacing: "0.1em" }}>
            EDON · {report.report_id}
          </div>
        </div>
      </div>

    </div>
  );
}
