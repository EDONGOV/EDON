## EDON × Telegram — Capability Matrix (User-Friendly)

This is the **Telegram experience** users get after payment and linking their account.
Designed to be **simple, fast, and safe**.

---

### 0) First-Run Onboarding (critical)

**User goals**
- “Is EDON alive?”
- “Is it watching anything?”
- “Can I control it?”

**Telegram must do**
- Auto-link tenant on first open (connect code)
- Show live status within 5 seconds
- Show one real (or simulated) decision

**Commands / UI**
- `/start`
- Inline **Connect system** button
- Status card

---

### 1) System Visibility (read‑only, always available)

**1.1 Live status**
- Online / degraded / offline
- Connected agents / bots
- Current mode (auto / supervised / locked)

**Example**
```
EDON Status
• Mode: Supervised
• Active policies: 4
• Last decision: 3s ago
```

**1.2 Decision feed**
- Last N decisions
- Filter by: Allowed / Blocked / Escalated

**Example**
```
Blocked: Movement outside zone
Policy: Boundary Guard
Confidence: 0.42
```

**Buttons**
- [ View details ]
- [ Override ]

---

### 2) Live Decision Control (Telegram’s killer feature)

**2.1 Approve / block / override**
For any **escalated** decision:
- [ Allow once ]
- [ Allow always ]
- [ Keep blocking ]

Each action:
- Creates an audit entry
- Optionally updates policy instance

**2.2 Emergency controls**
- Pause EDON
- Resume EDON
- Lock to “human approval only”

**Example**
```
⚠ Emergency Controls
[ Pause System ]
[ Require Human Approval ]
```

**Requirements**
- 1 tap
- Reversible
- Logged

---

### 3) Policy Management (instance-level only)

**3.1 View active policies**
Show name, scope, key thresholds, status

**Example**
```
Latency Guard
• Threshold: 300ms
• Scope: Navigation
```

**3.2 Enable / disable policy packs**
From a predefined catalog

**Example**
```
Available Policies
[ Safety Guard ]
[ Latency Failsafe ]
[ Human Approval ]
```

Tap → instance created.

**3.3 Tune parameters (safe knobs only)**
- Thresholds
- Confidence levels
- Time windows
- Severity levels

**UI**
- Inline +/- buttons
- Dropdown selectors
- No freeform input

**3.4 Scope policies**
Apply to:
- All agents
- Specific bots
- Task categories

---

### 4) Lightweight Policy Creation (wizard‑only)

**What “creation” means in Telegram**
- User answers a few questions
- EDON compiles a template‑based policy

**Supported**
- Threshold guards
- Time‑based controls
- Human‑in‑the‑loop triggers

**Not allowed**
- Boolean logic trees
- Condition chaining
- Expressions
- YAML / JSON editing

---

### 5) Alerts & Notifications (high‑signal only)

Telegram notifies when:
- Policy blocks an action
- Human approval is required
- System enters degraded mode
- New agent connects
- Policy changes take effect

Each alert includes **context + action buttons**.

---

### 6) Audit & Accountability (summarized)

**Recent audit entries**
- Policy enabled / disabled
- Overrides performed
- Emergency actions taken

Read‑only summaries only.  
Deep audit → web console.

---

### 7) Multi‑User & Roles (lightweight)

Role enforcement is **server‑side**.

| Role     | Can do |
|----------|--------|
| Viewer   | See status + alerts |
| Operator | Approve / override |
| Admin    | Enable policies, emergency actions |

---

### 8) Cross‑Platform Hand‑off (intentional)

When a user hits a boundary:
```
This action requires advanced policy logic.
[ Open Web Console ]
```

Telegram never pretends to be more powerful than it is.

---

### 9) Commands Surface (minimal)

Most users should never type commands.

**Supported**
- `/start`
- `/status`
- `/policies`
- `/decisions`
- `/help`

Everything else via buttons.

---

### What Telegram must NEVER do

- ❌ Full policy authoring  
- ❌ Version management  
- ❌ Multi‑condition logic  
- ❌ Long‑form configuration  
- ❌ Debugging / logs  
- ❌ Raw data exports  

Those live in the web console.
