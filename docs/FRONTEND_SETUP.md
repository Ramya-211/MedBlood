# Frontend Setup (React + Vite + JavaScript)

## Prerequisites
- Node.js 18+
- The backend running (see `docs/DATABASE_SETUP.md`), with CORS configured to allow this frontend's origin.

## Setup

```bash
cd frontend
cp .env.example .env
# edit .env if your backend isn't at http://localhost:8000
npm install
npm run dev
```

Opens at `http://localhost:5173`. Make sure the backend's `CORS_ORIGINS` includes this URL.

## Build for production

```bash
npm run build
npm run preview   # serve the production build locally to verify
```

## Structure

```
src/
  api/        thin wrappers around every backend endpoint (one file per module)
  context/    AuthContext (JWT storage, login/logout, role-based home path)
  routes/     ProtectedRoute (role-gated route guard)
  components/
    layout/   Sidebar, Topbar, AppShell
    ui/       KpiCard, StatusBadge, DataTable, FilterBar, Section, EmptyState, ErrorState, Skeleton
    charts/   TrendChart, BarComparisonChart, StatusDonut (Recharts)
    chatbot/  ChatLauncher (floating button), ChatPanel, ChatMessage
  pages/
    Landing.jsx, Login.jsx
    admin/AdminDashboard.jsx
    pharmacist/{Dashboard,Demand,Forecast,Inventory,Expiry,Alerts,Recommendations,Reports}.jsx
    blood/{Dashboard,Demand,Forecast,Inventory,Expiry,Alerts,Recommendations,Reports}.jsx
  styles/tokens.css   design system (colors, type, spacing, radius, shadow — light + dark theme)
  styles/global.css   base styles + all reusable component classes
```

## Design system

All colors/spacing/typography are CSS variables in `styles/tokens.css`. Status colors are semantic
and consistent everywhere via `StatusBadge`: green = healthy/safe, amber = warning/near-expiry/low,
red = critical/expired, blue = informational, purple = AI/forecast. Dark mode is a full token
override (`:root[data-theme="dark"]`), toggled from the topbar and persisted in `localStorage`.

## Data integrity in the UI

Every page calls the real backend — no page invents a number. Demand, forecast, backtest, supply,
and inventory are never relabeled or merged: forecast charts always show historical backtest and
future forecast as visually distinct series (see `forecast/overview` usage in both Forecast pages).

## Known limitation

No headless browser was available in the environment this was built in to capture literal
screenshots for final visual QA. Instead, every page's data bindings were verified against live
API responses field-by-field (see Phase 8 report), and `npm run build` / `oxlint` were run clean.
A manual look at each page in a real browser is recommended before a live demo.
