import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import ChatLauncher from "../chatbot/ChatLauncher";

export default function AppShell() {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => { setSidebarOpen(false); }, [location.pathname]);

  return (
    <div className="app-shell">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="app-main">
        <Topbar pathname={location.pathname} onMenuClick={() => setSidebarOpen((v) => !v)} theme={theme}
          onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))} />
        <main className="app-content">
          <Outlet />
        </main>
      </div>
      <ChatLauncher />
    </div>
  );
}
