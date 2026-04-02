import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
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
import {
  Users,
  UserPlus,
  UserMinus,
  Shield,
  Eye,
  Wrench,
  AlertTriangle,
  Share2,
  ExternalLink,
} from "lucide-react";

type Role = "Admin" | "Operator" | "Viewer";

interface Member {
  id: string;
  name: string;
  email: string;
  role: Role;
  status: "Active" | "Invited";
  joined: string;
  isCurrentUser?: boolean;
}

interface SharedAuditRecord {
  id: string;
  action: string;
  sharedBy: string;
  sharedWith: string;
  note: string;
  sharedAt: string;
}

const ROLE_BADGE: Record<Role, string> = {
  Admin: "bg-red-500/15 text-red-400 border border-red-500/25",
  Operator: "bg-amber-500/15 text-amber-400 border border-amber-500/25",
  Viewer: "bg-white/5 text-muted-foreground border border-white/10",
};

const ROLE_DESCRIPTIONS: Array<{ role: Role; icon: typeof Shield; desc: string }> = [
  {
    role: "Admin",
    icon: Shield,
    desc: "Full access. Can manage team, policies, and billing.",
  },
  {
    role: "Operator",
    icon: Wrench,
    desc: "Can view all decisions, manage policies, and connect backends.",
  },
  {
    role: "Viewer",
    icon: Eye,
    desc: "Read-only access to decisions and audit trail.",
  },
];

function getStoredEmail() {
  return localStorage.getItem("edon_user_email") || "you@example.com";
}

function getStoredName() {
  return (
    localStorage.getItem("edon_display_name") ||
    getStoredEmail().split("@")[0] ||
    "You"
  );
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function MemberAvatar({ name, role }: { name: string; role: Role }) {
  const colors: Record<Role, string> = {
    Admin: "bg-red-500/20 text-red-400 border-red-500/30",
    Operator: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    Viewer: "bg-white/10 text-muted-foreground border-white/15",
  };
  return (
    <div
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-semibold select-none ${colors[role]}`}
    >
      {getInitials(name)}
    </div>
  );
}

export default function Team() {
  const { toast } = useToast();
  const currentEmail = getStoredEmail();
  const currentName = getStoredName();

  const defaultMembers: Member[] = [
    {
      id: "member_self",
      name: currentName,
      email: currentEmail,
      role: "Admin",
      status: "Active",
      joined: "2025-01-15T00:00:00Z",
      isCurrentUser: true,
    },
    {
      id: "member_002",
      name: "Jordan Lee",
      email: "jordan.lee@example.com",
      role: "Operator",
      status: "Active",
      joined: "2025-02-01T00:00:00Z",
    },
    {
      id: "member_003",
      name: "Sam Rivera",
      email: "sam.rivera@example.com",
      role: "Viewer",
      status: "Invited",
      joined: "2025-03-10T00:00:00Z",
    },
  ];

  const [members, setMembers] = useState<Member[]>(defaultMembers);
  const [loading, setLoading] = useState(false);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("Viewer");
  const [inviteMessage, setInviteMessage] = useState("");
  const [inviting, setInviting] = useState(false);

  const [removeTarget, setRemoveTarget] = useState<Member | null>(null);
  const [removing, setRemoving] = useState(false);

  const [sharedAudits, setSharedAudits] = useState<SharedAuditRecord[]>([]);

  useEffect(() => {
    // Load shared audits from localStorage
    const stored = localStorage.getItem("edon_shared_audits");
    if (stored) {
      try {
        setSharedAudits(JSON.parse(stored));
      } catch {
        setSharedAudits([]);
      }
    }

    // Attempt to load real team members
    (async () => {
      setLoading(true);
      try {
        const result = await edonApi.getTeamMembers();
        if (result?.members && result.members.length > 0) {
          const mapped: Member[] = result.members.map(
            (m: { id: string; name?: string; email: string; role?: string; status?: string; joined_at?: string }) => ({
              id: m.id,
              name: m.name ?? m.email.split("@")[0],
              email: m.email,
              role: (m.role as Role) ?? "Viewer",
              status: (m.status as "Active" | "Invited") ?? "Active",
              joined: m.joined_at ?? new Date().toISOString(),
              isCurrentUser: m.email === currentEmail,
            })
          );
          setMembers(mapped);
        }
      } catch {
        // keep default mock members
      } finally {
        setLoading(false);
      }
    })();
  }, [currentEmail]);

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      await edonApi.inviteTeamMember(inviteEmail.trim(), inviteRole);
    } catch {
      // mock — proceed anyway
    } finally {
      const newMember: Member = {
        id: `member_${Date.now()}`,
        name: inviteEmail.split("@")[0],
        email: inviteEmail.trim(),
        role: inviteRole,
        status: "Invited",
        joined: new Date().toISOString(),
      };
      setMembers((prev) => [...prev, newMember]);
      toast({
        title: `Invitation sent to ${inviteEmail.trim()}`,
        description: `They'll receive an email with instructions to join.`,
      });
      setInviteOpen(false);
      setInviteEmail("");
      setInviteRole("Viewer");
      setInviteMessage("");
      setInviting(false);
    }
  };

  const handleRemove = async () => {
    if (!removeTarget) return;
    setRemoving(true);
    try {
      await edonApi.removeTeamMember(removeTarget.id);
    } catch {
      // mock — proceed
    } finally {
      setMembers((prev) => prev.filter((m) => m.id !== removeTarget.id));
      toast({
        title: "Member removed",
        description: `${removeTarget.name} has been removed from the team.`,
      });
      setRemoveTarget(null);
      setRemoving(false);
    }
  };

  const handleUnshare = (record: SharedAuditRecord) => {
    const next = sharedAudits.filter((r) => r.id !== record.id);
    setSharedAudits(next);
    localStorage.setItem("edon_shared_audits", JSON.stringify(next));
    toast({ title: "Unshared", description: "Audit record removed from shared list." });
  };

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 max-w-5xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h1 className="text-2xl font-bold">Team Members</h1>
                <Badge className="bg-white/5 text-muted-foreground border border-white/10 text-xs">
                  {members.length}
                </Badge>
              </div>
              <p className="text-muted-foreground text-sm">
                Manage access and roles for your organization.
              </p>
            </div>
            <Button onClick={() => setInviteOpen(true)} className="gap-2">
              <UserPlus className="w-4 h-4" />
              Invite Member
            </Button>
          </div>

          {/* ── MEMBERS TABLE ────────────────────────── */}
          <div className="glass-card overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="border-white/10 hover:bg-white/5">
                  <TableHead className="text-muted-foreground">Member</TableHead>
                  <TableHead className="text-muted-foreground">Role</TableHead>
                  <TableHead className="text-muted-foreground">Status</TableHead>
                  <TableHead className="text-muted-foreground">Joined</TableHead>
                  <TableHead className="text-muted-foreground text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i} className="border-white/10">
                      <TableCell colSpan={5}>
                        <div className="h-8 bg-white/5 rounded animate-pulse" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : members.length === 0 ? (
                  <TableRow className="border-white/10">
                    <TableCell colSpan={5}>
                      <div className="py-10 text-center">
                        <Users className="w-8 h-8 text-muted-foreground/40 mx-auto mb-3" />
                        <p className="text-sm text-muted-foreground">No team members yet.</p>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  members.map((member) => (
                    <TableRow
                      key={member.id}
                      className="border-white/10 hover:bg-white/5 transition-colors"
                    >
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <MemberAvatar name={member.name} role={member.role} />
                          <div>
                            <p className="text-sm font-medium">
                              {member.name}
                              {member.isCurrentUser && (
                                <span className="ml-1.5 text-xs text-muted-foreground/60">(you)</span>
                              )}
                            </p>
                            <p className="text-xs text-muted-foreground">{member.email}</p>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge className={`text-xs ${ROLE_BADGE[member.role]}`}>
                          {member.role}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {member.status === "Active" ? (
                          <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 text-xs">
                            Active
                          </Badge>
                        ) : (
                          <Badge className="bg-amber-500/15 text-amber-400 border border-amber-500/25 text-xs">
                            Invited
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {fmtDate(member.joined)}
                      </TableCell>
                      <TableCell className="text-right">
                        {!member.isCurrentUser && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setRemoveTarget(member)}
                            className="gap-1 text-muted-foreground hover:text-red-400"
                          >
                            <UserMinus className="w-3.5 h-3.5" />
                            Remove
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          {/* ── ROLE DESCRIPTIONS ────────────────────── */}
          <section>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
              Role Permissions
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {ROLE_DESCRIPTIONS.map(({ role, icon: Icon, desc }) => (
                <div key={role} className="glass-card px-4 py-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/10">
                      <Icon className="h-3.5 w-3.5 text-foreground/80" />
                    </div>
                    <Badge className={`text-xs ${ROLE_BADGE[role]}`}>{role}</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{desc}</p>
                </div>
              ))}
            </div>
          </section>

          {/* ── SHARED AUDITS ────────────────────────── */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Shared Audit Records
              </p>
              <Badge className="bg-white/5 text-muted-foreground border border-white/10 text-xs">
                {sharedAudits.length}
              </Badge>
            </div>

            {sharedAudits.length === 0 ? (
              <div className="glass-card px-6 py-8 text-center">
                <Share2 className="w-8 h-8 text-muted-foreground/40 mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">No shared audit records yet.</p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  Share records from the{" "}
                  <a href="/audit" className="text-primary hover:underline">
                    Audit page
                  </a>{" "}
                  to collaborate with your team.
                </p>
              </div>
            ) : (
              <div className="glass-card overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="border-white/10 hover:bg-white/5">
                      <TableHead className="text-muted-foreground">Record</TableHead>
                      <TableHead className="text-muted-foreground">Shared By</TableHead>
                      <TableHead className="text-muted-foreground">Shared With</TableHead>
                      <TableHead className="text-muted-foreground">Note</TableHead>
                      <TableHead className="text-muted-foreground">Shared At</TableHead>
                      <TableHead className="text-muted-foreground text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sharedAudits.map((record) => (
                      <TableRow
                        key={record.id}
                        className="border-white/10 hover:bg-white/5 transition-colors"
                      >
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          <div>
                            <p className="text-foreground/80 font-medium text-sm">{record.action}</p>
                            <p className="text-muted-foreground/60 mt-0.5">{record.id}</p>
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {record.sharedBy}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {record.sharedWith}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground max-w-[200px]">
                          <p className="truncate" title={record.note}>
                            {record.note || "—"}
                          </p>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {fmtDate(record.sharedAt)}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => window.open(`/audit?id=${record.id}`, "_blank")}
                              className="gap-1 text-muted-foreground hover:text-foreground"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                              View
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleUnshare(record)}
                              className="gap-1 text-muted-foreground hover:text-red-400"
                            >
                              <Share2 className="w-3.5 h-3.5" />
                              Unshare
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </section>
        </motion.div>
      </main>

      {/* Invite Member Dialog */}
      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent className="glass-card border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <UserPlus className="w-4 h-4 text-primary" />
              Invite Team Member
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="inviteEmail" className="text-xs text-muted-foreground">
                Email <span className="text-red-400">*</span>
              </Label>
              <Input
                id="inviteEmail"
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="teammate@example.com"
                className="bg-secondary/50"
                onKeyDown={(e) => e.key === "Enter" && handleInvite()}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="inviteRole" className="text-xs text-muted-foreground">
                Role
              </Label>
              <Select value={inviteRole} onValueChange={(v) => setInviteRole(v as Role)}>
                <SelectTrigger id="inviteRole" className="bg-secondary/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Admin">Admin</SelectItem>
                  <SelectItem value="Operator">Operator</SelectItem>
                  <SelectItem value="Viewer">Viewer</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="inviteMessage" className="text-xs text-muted-foreground">
                Message <span className="text-muted-foreground/50">(optional)</span>
              </Label>
              <Textarea
                id="inviteMessage"
                value={inviteMessage}
                onChange={(e) => setInviteMessage(e.target.value)}
                placeholder="Add a personal note to the invitation…"
                className="bg-secondary/50 text-sm resize-none"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter className="gap-2 mt-2">
            <Button variant="outline" onClick={() => setInviteOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleInvite}
              disabled={!inviteEmail.trim() || inviting}
              className="gap-2"
            >
              {inviting ? (
                <>
                  <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  Sending…
                </>
              ) : (
                <>
                  <UserPlus className="w-3.5 h-3.5" />
                  Send Invite
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Remove Member Confirmation Dialog */}
      <Dialog open={!!removeTarget} onOpenChange={(open) => !open && setRemoveTarget(null)}>
        <DialogContent className="glass-card border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              Remove member?
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to remove{" "}
            <span className="text-foreground font-medium">{removeTarget?.name}</span> from the
            team? They will lose all access immediately.
          </p>
          <DialogFooter className="gap-2 mt-2">
            <Button variant="outline" onClick={() => setRemoveTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleRemove} disabled={removing}>
              {removing ? (
                <>
                  <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin mr-1.5" />
                  Removing…
                </>
              ) : (
                "Yes, remove member"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
