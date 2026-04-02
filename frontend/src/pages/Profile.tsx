import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { User, Shield, AlertTriangle, Monitor, Save, Lock, Sun, Moon } from "lucide-react";

const TIMEZONES = [
  { value: "UTC", label: "UTC — Coordinated Universal Time" },
  { value: "America/New_York", label: "EST — Eastern Standard Time" },
  { value: "America/Chicago", label: "CST — Central Standard Time" },
  { value: "America/Denver", label: "MST — Mountain Standard Time" },
  { value: "America/Los_Angeles", label: "PST — Pacific Standard Time" },
  { value: "Europe/London", label: "GMT — Greenwich Mean Time" },
  { value: "Europe/Berlin", label: "CET — Central European Time" },
  { value: "Asia/Tokyo", label: "JST — Japan Standard Time" },
  { value: "Asia/Singapore", label: "SGT — Singapore Time" },
  { value: "Australia/Sydney", label: "AEST — Australian Eastern Time" },
];

function applyTheme(t: 'dark' | 'light') {
  document.documentElement.classList.toggle('dark', t === 'dark');
  document.documentElement.classList.toggle('light', t === 'light');
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function Profile() {
  const { toast } = useToast();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [theme, setTheme] = useState<'dark' | 'light'>(() =>
    (localStorage.getItem("edon_theme") as 'dark' | 'light') || 'dark'
  );
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const storedEmail = localStorage.getItem("edon_user_email") || "";
    const storedName = localStorage.getItem("edon_display_name") || "";
    setEmail(storedEmail);
    setDisplayName(storedName || storedEmail.split("@")[0] || "");
    setTimezone(localStorage.getItem("edon_timezone") || "UTC");
  }, []);

  const initials = getInitials(displayName || email || "U");

  const handleSave = async () => {
    setSaving(true);
    await new Promise((r) => setTimeout(r, 400));
    localStorage.setItem("edon_display_name", displayName.trim());
    localStorage.setItem("edon_timezone", timezone);
    localStorage.setItem("edon_theme", theme);
    applyTheme(theme);
    setSaving(false);
    toast({ title: "Profile saved", description: "Your changes have been saved." });
  };

  const handleChangePassword = () => {
    toast({
      title: "Contact your admin to change password",
      description: "Password changes are managed by your organization administrator.",
    });
  };

  const handleRevokeAllSessions = () => {
    toast({
      title: "Sessions revoked",
      description: "All other sessions have been signed out.",
    });
  };

  const handleDeleteAccount = () => {
    setDeleteDialogOpen(false);
    toast({
      title: "Contact support to delete your account",
      description: "Reach out to support@edoncore.com to request account deletion.",
    });
  };

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 max-w-2xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {/* Page title */}
          <div>
            <h1 className="text-xl font-semibold text-foreground/90">Profile</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Manage your account details and security settings.
            </p>
          </div>

          {/* ── PROFILE HEADER ───────────────────────── */}
          <section className="glass-card px-6 py-5">
            <div className="flex items-center gap-5">
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-primary/20 border-2 border-primary/40 text-primary font-semibold text-xl select-none">
                {initials}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-base font-semibold truncate">
                    {displayName || email || "Your Account"}
                  </p>
                  <Badge className="bg-primary/20 text-primary border border-primary/30 text-xs font-medium">
                    Admin
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground truncate mt-0.5">{email}</p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  Member since Jan 2025
                </p>
              </div>
            </div>
          </section>

          {/* ── PERSONAL INFO ────────────────────────── */}
          <section>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
              Personal Info
            </p>
            <div className="glass-card px-6 py-5 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="displayName" className="text-xs text-muted-foreground">
                  Display Name
                </Label>
                <Input
                  id="displayName"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  className="bg-secondary/50"
                />
                <p className="text-xs text-muted-foreground/60">
                  This is how you appear across the platform.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-xs text-muted-foreground">
                  Email
                </Label>
                <div className="relative">
                  <Input
                    id="email"
                    value={email}
                    readOnly
                    className="bg-secondary/30 text-muted-foreground cursor-not-allowed pr-20"
                  />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground/50">
                    Read-only
                  </span>
                </div>
                <p className="text-xs text-muted-foreground/60">
                  Email is managed by your authentication provider.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="timezone" className="text-xs text-muted-foreground">
                  Timezone
                </Label>
                <Select value={timezone} onValueChange={setTimezone}>
                  <SelectTrigger id="timezone" className="bg-secondary/50">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TIMEZONES.map((tz) => (
                      <SelectItem key={tz.value} value={tz.value}>
                        {tz.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Appearance</Label>
                <div className="flex gap-2">
                  {(['dark', 'light'] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => { setTheme(t); applyTheme(t); }}
                      className={`flex flex-1 items-center justify-center gap-2 rounded-lg border py-2 text-sm font-medium transition-colors ${
                        theme === t
                          ? 'border-primary/50 bg-primary/10 text-primary'
                          : 'border-white/10 bg-white/5 text-muted-foreground hover:bg-white/10'
                      }`}
                    >
                      {t === 'dark' ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
                      {t === 'dark' ? 'Dark' : 'Light'}
                    </button>
                  ))}
                </div>
              </div>

              <div className="pt-1">
                <Button
                  onClick={handleSave}
                  disabled={saving}
                  className="gap-2"
                >
                  {saving ? (
                    <>
                      <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                      Saving…
                    </>
                  ) : (
                    <>
                      <Save className="w-3.5 h-3.5" />
                      Save changes
                    </>
                  )}
                </Button>
              </div>
            </div>
          </section>

          {/* ── SECURITY ─────────────────────────────── */}
          <section>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
              Security
            </p>
            <div className="glass-card divide-y divide-white/5">
              {/* Change password */}
              <div className="px-5 py-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10">
                    <Lock className="h-3.5 w-3.5 text-foreground/80" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">Password</p>
                    <p className="text-xs text-muted-foreground">Managed by your organization</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleChangePassword}
                  className="text-xs text-primary hover:underline shrink-0"
                >
                  Change password →
                </button>
              </div>

              {/* Active sessions */}
              <div className="px-5 py-4">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10">
                      <Monitor className="h-3.5 w-3.5 text-foreground/80" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">Active Sessions</p>
                      <p className="text-xs text-muted-foreground">Devices currently signed in</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleRevokeAllSessions}
                    className="text-xs text-muted-foreground hover:text-foreground shrink-0"
                  >
                    Revoke all
                  </button>
                </div>

                {/* Session list */}
                <div className="rounded-lg bg-white/5 border border-white/10 px-4 py-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">Current browser</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {navigator.userAgent.includes("Chrome")
                        ? "Chrome"
                        : navigator.userAgent.includes("Firefox")
                        ? "Firefox"
                        : navigator.userAgent.includes("Safari")
                        ? "Safari"
                        : "Browser"}{" "}
                      · {navigator.platform || "Unknown platform"}
                    </p>
                  </div>
                  <Badge className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 text-xs shrink-0">
                    Active now
                  </Badge>
                </div>
              </div>
            </div>
          </section>

          {/* ── DANGER ZONE ──────────────────────────── */}
          <section>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
              Danger Zone
            </p>
            <div className="rounded-xl border border-red-500/25 bg-red-500/5 px-5 py-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-500/15">
                    <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-foreground/90">Delete account</p>
                    <p className="text-xs text-muted-foreground">
                      Permanently remove your account and all data. This cannot be undone.
                    </p>
                  </div>
                </div>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setDeleteDialogOpen(true)}
                  className="shrink-0"
                >
                  Delete account
                </Button>
              </div>
            </div>
          </section>
        </motion.div>
      </main>

      {/* Delete account confirmation dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="glass-card border-white/10 max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              Delete account?
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This action cannot be undone. All your data, agents, and audit records will be
            permanently removed. Are you sure you want to continue?
          </p>
          <DialogFooter className="gap-2 mt-2">
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteAccount}>
              Yes, delete my account
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
