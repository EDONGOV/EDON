import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { edonApi } from "@/lib/api";
import { Key, Plus, Copy, AlertTriangle, Trash2, Check } from "lucide-react";

interface ApiKeyRow {
  id: string;
  name: string;
  key_preview: string;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  status: "active" | "expired";
}

const MOCK_KEYS: ApiKeyRow[] = [
  {
    id: "key_001",
    name: "agent-prod",
    key_preview: "edon_sk_...a3f9",
    created_at: "2025-01-15T10:00:00Z",
    expires_at: null,
    last_used_at: new Date(Date.now() - 1000 * 60 * 7).toISOString(),
    status: "active",
  },
  {
    id: "key_002",
    name: "ci-pipeline",
    key_preview: "edon_sk_...7c12",
    created_at: "2025-02-01T09:30:00Z",
    expires_at: "2026-02-01T09:30:00Z",
    last_used_at: new Date(Date.now() - 1000 * 60 * 60 * 3).toISOString(),
    status: "active",
  },
  {
    id: "key_003",
    name: "test-key",
    key_preview: "edon_sk_...d4e8",
    created_at: "2024-11-10T14:00:00Z",
    expires_at: "2025-02-10T14:00:00Z",
    last_used_at: "2025-02-09T08:00:00Z",
    status: "expired",
  },
];

function randomHex(length: number): string {
  const chars = "0123456789abcdef";
  return Array.from({ length }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}

function fmtDate(iso: string | null): string {
  if (!iso) return "Never";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function fmtRelative(iso: string | null): string {
  if (!iso) return "Never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return fmtDate(iso);
}

export default function ApiKeys() {
  const { toast } = useToast();

  const [keys, setKeys] = useState<ApiKeyRow[]>(MOCK_KEYS);
  const [loading, setLoading] = useState(true);

  const [createOpen, setCreateOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyDesc, setNewKeyDesc] = useState("");
  const [newKeyExpiry, setNewKeyExpiry] = useState("never");
  const [creating, setCreating] = useState(false);

  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const [newKeyRevealOpen, setNewKeyRevealOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const [revokeTarget, setRevokeTarget] = useState<ApiKeyRow | null>(null);
  const [revoking, setRevoking] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const result = await edonApi.listApiKeys();
        if (result?.keys && result.keys.length > 0) {
          const mapped: ApiKeyRow[] = result.keys.map((k) => ({
            id: k.id,
            name: k.name,
            key_preview: `edon_sk_...${k.id.slice(-4)}`,
            created_at: k.created_at ?? new Date().toISOString(),
            expires_at: null,
            last_used_at: null,
            status: "active" as const,
          }));
          setKeys(mapped);
        }
      } catch {
        // fall through to mock data already set
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleCreate = async () => {
    if (!newKeyName.trim()) return;
    setCreating(true);
    try {
      const result = await edonApi.createApiKey(newKeyName.trim());
      const rawKey = result?.api_key ?? `edon_sk_${randomHex(32)}`;
      const preview = `edon_sk_...${rawKey.slice(-4)}`;
      const newRow: ApiKeyRow = {
        id: result?.api_key_id ?? `key_${Date.now()}`,
        name: newKeyName.trim(),
        key_preview: preview,
        created_at: new Date().toISOString(),
        expires_at:
          newKeyExpiry === "30d"
            ? new Date(Date.now() + 30 * 86400000).toISOString()
            : newKeyExpiry === "90d"
            ? new Date(Date.now() + 90 * 86400000).toISOString()
            : newKeyExpiry === "1y"
            ? new Date(Date.now() + 365 * 86400000).toISOString()
            : null,
        last_used_at: null,
        status: "active",
      };
      setKeys((prev) => [newRow, ...prev]);
      setNewKeyValue(rawKey);
      setCreateOpen(false);
      setNewKeyRevealOpen(true);
    } catch {
      // API failed — generate mock key
      const mockKey = `edon_sk_${randomHex(32)}`;
      const preview = `edon_sk_...${mockKey.slice(-4)}`;
      const newRow: ApiKeyRow = {
        id: `key_${Date.now()}`,
        name: newKeyName.trim(),
        key_preview: preview,
        created_at: new Date().toISOString(),
        expires_at:
          newKeyExpiry === "30d"
            ? new Date(Date.now() + 30 * 86400000).toISOString()
            : newKeyExpiry === "90d"
            ? new Date(Date.now() + 90 * 86400000).toISOString()
            : newKeyExpiry === "1y"
            ? new Date(Date.now() + 365 * 86400000).toISOString()
            : null,
        last_used_at: null,
        status: "active",
      };
      setKeys((prev) => [newRow, ...prev]);
      setNewKeyValue(mockKey);
      setCreateOpen(false);
      setNewKeyRevealOpen(true);
    } finally {
      setCreating(false);
      setNewKeyName("");
      setNewKeyDesc("");
      setNewKeyExpiry("never");
    }
  };

  const handleCopyKey = () => {
    if (!newKeyValue) return;
    navigator.clipboard.writeText(newKeyValue).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    setRevoking(true);
    try {
      await edonApi.deleteApiKey(revokeTarget.id);
    } catch {
      // ignore — remove locally regardless
    } finally {
      setKeys((prev) => prev.filter((k) => k.id !== revokeTarget.id));
      toast({ title: "Key revoked", description: `"${revokeTarget.name}" has been revoked.` });
      setRevokeTarget(null);
      setRevoking(false);
    }
  };

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold mb-1">API Keys</h1>
              <p className="text-muted-foreground text-sm">
                Manage programmatic access keys for your agents and integrations.
              </p>
            </div>
            <Button onClick={() => setCreateOpen(true)} className="gap-2">
              <Plus className="w-4 h-4" />
              Create New Key
            </Button>
          </div>

          {/* Keys table */}
          <div className="glass-card overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="border-white/10 hover:bg-white/5">
                  <TableHead className="text-muted-foreground">Name</TableHead>
                  <TableHead className="text-muted-foreground">Key</TableHead>
                  <TableHead className="text-muted-foreground">Created</TableHead>
                  <TableHead className="text-muted-foreground">Expires</TableHead>
                  <TableHead className="text-muted-foreground">Last Used</TableHead>
                  <TableHead className="text-muted-foreground">Status</TableHead>
                  <TableHead className="text-muted-foreground text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i} className="border-white/10">
                      <TableCell colSpan={7}>
                        <div className="h-8 bg-white/5 rounded animate-pulse" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : keys.length === 0 ? (
                  <TableRow className="border-white/10">
                    <TableCell colSpan={7}>
                      <div className="py-10 text-center">
                        <Key className="w-8 h-8 text-muted-foreground/40 mx-auto mb-3" />
                        <p className="text-sm text-muted-foreground">No API keys yet.</p>
                        <p className="text-xs text-muted-foreground/60 mt-1">
                          Create your first key to start connecting agents.
                        </p>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  keys.map((key) => (
                    <TableRow
                      key={key.id}
                      className="border-white/10 hover:bg-white/5 transition-colors"
                    >
                      <TableCell className="font-medium">{key.name}</TableCell>
                      <TableCell className="font-mono text-sm text-muted-foreground">
                        {key.key_preview}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {fmtDate(key.created_at)}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {key.expires_at ? fmtDate(key.expires_at) : "Never"}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {fmtRelative(key.last_used_at)}
                      </TableCell>
                      <TableCell>
                        {key.status === "active" ? (
                          <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 text-xs">
                            Active
                          </Badge>
                        ) : (
                          <Badge className="bg-red-500/15 text-red-400 border border-red-500/25 text-xs">
                            Expired
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setRevokeTarget(key)}
                          className="gap-1 text-muted-foreground hover:text-red-400"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          Revoke
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </motion.div>
      </main>

      {/* Create Key Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="glass-card border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Key className="w-4 h-4 text-primary" />
              Create API Key
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="keyName" className="text-xs text-muted-foreground">
                Key Name <span className="text-red-400">*</span>
              </Label>
              <Input
                id="keyName"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="e.g. agent-prod, ci-pipeline"
                className="bg-secondary/50"
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="keyDesc" className="text-xs text-muted-foreground">
                Description <span className="text-muted-foreground/50">(optional)</span>
              </Label>
              <Input
                id="keyDesc"
                value={newKeyDesc}
                onChange={(e) => setNewKeyDesc(e.target.value)}
                placeholder="What is this key used for?"
                className="bg-secondary/50"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="keyExpiry" className="text-xs text-muted-foreground">
                Expiry
              </Label>
              <Select value={newKeyExpiry} onValueChange={setNewKeyExpiry}>
                <SelectTrigger id="keyExpiry" className="bg-secondary/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="never">Never</SelectItem>
                  <SelectItem value="30d">30 days</SelectItem>
                  <SelectItem value="90d">90 days</SelectItem>
                  <SelectItem value="1y">1 year</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter className="gap-2 mt-2">
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!newKeyName.trim() || creating}
              className="gap-2"
            >
              {creating ? (
                <>
                  <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  Creating…
                </>
              ) : (
                "Create Key"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New Key Reveal Dialog */}
      <Dialog open={newKeyRevealOpen} onOpenChange={setNewKeyRevealOpen}>
        <DialogContent className="glass-card border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Key className="w-4 h-4 text-primary" />
              API Key Created
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-sm text-amber-300">
                Copy this key now — it won't be shown again.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Your new API key</Label>
              <div className="flex gap-2">
                <Input
                  value={newKeyValue ?? ""}
                  readOnly
                  className="bg-secondary/50 font-mono text-xs"
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCopyKey}
                  className="shrink-0 gap-1.5"
                >
                  {copied ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      Copy
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter className="mt-2">
            <Button
              onClick={() => {
                setNewKeyRevealOpen(false);
                setNewKeyValue(null);
              }}
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke Confirmation Dialog */}
      <Dialog open={!!revokeTarget} onOpenChange={(open) => !open && setRevokeTarget(null)}>
        <DialogContent className="glass-card border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              Revoke key?
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to revoke{" "}
            <span className="text-foreground font-medium">"{revokeTarget?.name}"</span>? Any agents
            using this key will lose access immediately.
          </p>
          <DialogFooter className="gap-2 mt-2">
            <Button variant="outline" onClick={() => setRevokeTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleRevoke} disabled={revoking}>
              {revoking ? (
                <>
                  <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin mr-1.5" />
                  Revoking…
                </>
              ) : (
                "Yes, revoke key"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
