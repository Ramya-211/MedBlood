import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import {
  LayoutDashboard, Pill, Droplet, TrendingUp, Package, CalendarClock, BellRing,
  Lightbulb, FileBarChart2, Sparkles, LogOut, Users, Activity, X,
} from "lucide-react";

const NAV = {
ADMIN: [
  { to: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/admin/users", label: "User Management", icon: Users },
],
  PHARMACIST: [
    { to: "/pharmacist/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/pharmacist/demand", label: "Demand", icon: TrendingUp },
    { to: "/pharmacist/forecast", label: "Forecasting", icon: Sparkles },
    { to: "/pharmacist/inventory", label: "Inventory", icon: Package },
    { to: "/pharmacist/expiry", label: "Expiry", icon: CalendarClock },
    { to: "/pharmacist/alerts", label: "Alerts", icon: BellRing },
    { to: "/pharmacist/recommendations", label: "Recommendations", icon: Lightbulb },
    { to: "/pharmacist/reports", label: "Reports", icon: FileBarChart2 },
  ],
  BLOOD_STAFF: [
    { to: "/blood/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/blood/demand", label: "Demand", icon: TrendingUp },
    { to: "/blood/forecast", label: "Forecasting", icon: Sparkles },
    { to: "/blood/inventory", label: "Inventory", icon: Package },
    { to: "/blood/expiry", label: "Expiry", icon: CalendarClock },
    { to: "/blood/alerts", label: "Alerts", icon: BellRing },
    { to: "/blood/recommendations", label: "Recommendations", icon: Lightbulb },
    { to: "/blood/reports", label: "Reports", icon: FileBarChart2 },
  ],
};

const ROLE_ICON = { ADMIN: Users, PHARMACIST: Pill, BLOOD_STAFF: Droplet };

export default function Sidebar({ open, onClose }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const items = NAV[user?.role] || [];
  const RoleIcon = ROLE_ICON[user?.role] || Activity;

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <>
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <div className="sidebar-logo"><Activity size={18} strokeWidth={2.5} /></div>
          <div className="stack gap-0">
            <span className="text-h2" style={{ lineHeight: 1.1 }}>MedBlood</span>
            <span className="text-micro" style={{ letterSpacing: "0.02em" }}>Intelligence Platform</span>
          </div>
          <button className="btn btn-ghost sidebar-close" onClick={onClose}><X size={18} /></button>
        </div>

        <nav className="sidebar-nav">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={onClose} className={({ isActive }) => `sidebar-link ${isActive ? "sidebar-link-active" : ""}`}>
              <Icon size={17} strokeWidth={2} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="row gap-2 sidebar-user">
            <div className="sidebar-avatar"><RoleIcon size={15} /></div>
            <div className="stack gap-0" style={{ minWidth: 0 }}>
              <span className="text-small" style={{ color: "var(--color-text-primary)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user?.full_name}</span>
              <span className="text-micro">{user?.role?.replace("_", " ")}</span>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" style={{ width: "100%", justifyContent: "flex-start" }} onClick={handleLogout}>
            <LogOut size={15} /> Logout
          </button>
        </div>
      </aside>
      {open && <div className="sidebar-backdrop" onClick={onClose} />}
    </>
  );
}
