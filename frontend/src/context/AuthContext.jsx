import { createContext, useContext, useState, useCallback, useMemo } from "react";
import * as authApi from "../api/auth";

const AuthContext = createContext(null);

const ROLE_HOME = {
  ADMIN: "/admin/dashboard",
  PHARMACIST: "/pharmacist/dashboard",
  BLOOD_STAFF: "/blood/dashboard",
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem("auth_user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  const login = useCallback(async (username, password) => {
    const data = await authApi.login(username, password);
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("auth_user", JSON.stringify(data.user));
    setUser(data.user);
    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* already unusable token; proceed with local cleanup regardless */
    }
    localStorage.removeItem("access_token");
    localStorage.removeItem("auth_user");
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, login, logout, homePath: user ? ROLE_HOME[user.role] : "/" }), [user, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { ROLE_HOME };
