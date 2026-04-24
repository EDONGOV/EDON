# admin — Internal admin panel

See root `CLAUDE.md` for the full project map.

- **Package name:** edon-admin
- **Stack:** React 18, TypeScript, Vite, Tailwind
- **Dev:** `npm run dev` (port 5174)
- **Build:** `npm run build` → `dist/`
- **API base:** points to `backend/edon_gateway` (same gateway as console)

Internal tooling for ops: tenant management, audit log viewer, kill-switch controls.
Do not expose admin routes in the public console.
