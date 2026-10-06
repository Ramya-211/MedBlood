import { Menu, Moon, Sun } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

const TITLES = {
  "/admin/dashboard": "Admin Overview",
  "/pharmacist/dashboard": "Medicine Intelligence",
  "/pharmacist/demand": "Medicine Demand",
  "/pharmacist/forecast": "Demand Forecasting",
  "/pharmacist/inventory": "Medicine Inventory",
  "/pharmacist/expiry": "Expiry Intelligence",
  "/pharmacist/alerts": "Alert Center",
  "/pharmacist/recommendations": "Recommendations",
  "/pharmacist/reports": "Report Center",
  "/blood/dashboard": "Blood Resource Intelligence",
  "/blood/demand": "Blood Demand",
  "/blood/forecast": "Demand Forecasting",
  "/blood/inventory": "Blood Inventory",
  "/blood/expiry": "Expiry Intelligence",
  "/blood/alerts": "Alert Center",
  "/blood/recommendations": "Recommendations",
  "/blood/reports": "Report Center",
};

const ROLE_LABEL = { ADMIN: "Admin", PHARMACIST: "Pharmacist", BLOOD_STAFF: "Blood Staff" };

export default function Topbar({ pathname, onMenuClick, theme, onToggleTheme }) {
  const { user } = useAuth();
  const title = TITLES[pathname] || "Overview";
  const initial = (user?.full_name || "?").charAt(0).toUpperCase();

  return (
    <header className="topbar">
      <button className="btn btn-ghost topbar-menu-btn" onClick={onMenuClick}><Menu size={19} /></button>
      <div className="text-h1 grow" style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</div>
      <div className="row gap-3">
        <button className="btn btn-ghost btn-sm" onClick={onToggleTheme} title="Toggle theme">
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <div className="row gap-2">
          <div className="topbar-avatar">{initial}</div>
          <div className="stack gap-0" style={{ lineHeight: 1.1 }}>
            <span className="text-small" style={{ fontWeight: 600, color: "var(--color-text-primary)" }}>{user?.full_name}</span>
            <span className="text-micro">{ROLE_LABEL[user?.role]}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
