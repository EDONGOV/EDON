import { Decision } from '@/lib/api';
import { formatJSON } from '@/lib/redact';
import { Badge } from '@/components/ui/badge';
import { toolOp } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

interface DecisionDrawerProps {
  decision: Decision | null;
  open: boolean;
  onClose: () => void;
}

const verdictStyles = {
  allowed: 'badge-allowed',
  blocked: 'badge-blocked',
  confirm: 'badge-confirm',
};

const verdictClass = (verdict?: string) => {
  const v = (verdict ?? '').toLowerCase();
  return verdictStyles[v as keyof typeof verdictStyles] || 'badge-allowed';
};

export function DecisionDrawer({ decision, open, onClose }: DecisionDrawerProps) {
  if (!decision) return null;

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="glass-card border-l border-white/10 w-[500px] sm:max-w-[500px]">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-3">
            <Badge className={verdictClass(decision.verdict)}>
              {(decision.verdict ?? 'unknown').toString().toUpperCase()}
            </Badge>
            <span className="font-mono text-lg">{toolOp(decision.tool)}</span>
          </SheetTitle>
          <SheetDescription>
            Decision ID: {decision.id ?? '—'}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-120px)] mt-6 pr-4">
          <div className="space-y-6">
            {/* Metadata */}
            <section>
              <h4 className="text-sm font-semibold text-muted-foreground mb-3">Metadata</h4>
              <div className="glass-card p-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Timestamp</span>
                  <span>{(decision.timestamp ?? decision.created_at) ? new Date(decision.timestamp ?? decision.created_at!).toLocaleString() : '—'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Agent ID</span>
                  <span className="font-mono">{decision.agent_id ?? '—'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Latency</span>
                  <span>{decision.latency_ms != null ? `${decision.latency_ms}ms` : '—'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Policy Version</span>
                  <span className="font-mono">{decision.policy_version ?? 'N/A'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Reason Code</span>
                  <span className="font-mono">{decision.reason_code ?? '—'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Intent ID</span>
                  <span className="font-mono text-xs break-all">{decision.intent_id ?? '—'}</span>
                </div>
              </div>
            </section>

            {/* Explanation */}
            {decision.explanation && (
              <section>
                <h4 className="text-sm font-semibold text-muted-foreground mb-3">Explanation</h4>
                <div className="glass-card p-4">
                  <p className="text-sm">{decision.explanation}</p>
                </div>
              </section>
            )}

            {/* Safe Alternative */}
            {decision.safe_alternative && (
              <section>
                <h4 className="text-sm font-semibold text-muted-foreground mb-3">Safe Alternative</h4>
                <div className="glass-card p-4 border-l-2 border-emerald-500">
                  <p className="text-sm text-emerald-400">{decision.safe_alternative}</p>
                </div>
              </section>
            )}

            {/* Request Payload */}
            {decision.request_payload && (
              <section>
                <h4 className="text-sm font-semibold text-muted-foreground mb-3">Request Payload (Redacted)</h4>
                <div className="glass-card p-4">
                  <pre className="text-xs font-mono text-muted-foreground overflow-x-auto">
                    {formatJSON(decision.request_payload)}
                  </pre>
                </div>
              </section>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
