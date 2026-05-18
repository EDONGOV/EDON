# console — Tenant-facing web app

See root `CLAUDE.md` for the full project map.

- **Package name:** edon-console
- **Stack:** React 18, TypeScript, Vite, Tailwind
- **Dev:** `npm run dev` (port 5173)
- **Build:** `npm run build` → `dist/`
- **API base:** points to `backend/edon_gateway` (configure in `src/api.ts`)

This is the primary UI agents and users interact with. All new tenant-facing features go here.
