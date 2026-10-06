import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, LogIn, AlertCircle } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { apiErrorMessage } from "../api/client";
import { ROLE_HOME } from "../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await login(username, password);
      navigate(data.redirect_path || ROLE_HOME[data.user.role] || "/");
    } catch (err) {
      setError(apiErrorMessage(err, "Login failed. Please check your credentials."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card card fade-in">
        <div className="stack gap-2" style={{ alignItems: "center", marginBottom: 20 }}>
          <div className="sidebar-logo" style={{ width: 44, height: 44, borderRadius: 12 }}><Activity size={22} /></div>
          <span className="text-h1">MedBlood Intelligence</span>
          <span className="text-small">Sign in to continue</span>
        </div>

        <form className="stack gap-4" onSubmit={submit}>
          {error && (
            <div className="row gap-2" style={{ background: "var(--color-danger-50)", color: "var(--color-danger-600)", padding: "10px 12px", borderRadius: 10, fontSize: 13 }}>
              <AlertCircle size={15} /> {error}
            </div>
          )}
          <label className="stack gap-1">
            <span className="text-micro">Username</span>
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
          </label>
          <label className="stack gap-1">
            <span className="text-micro">Password</span>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          <button className="btn btn-primary" type="submit" disabled={loading} style={{ justifyContent: "center", padding: "11px" }}>
            {loading ? "Signing in..." : <>Sign in <LogIn size={15} /></>}
          </button>
        </form>
      </div>
    </div>
  );
}
