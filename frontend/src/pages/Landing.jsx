import { Link } from "react-router-dom";
import {
  Activity, TrendingUp, Package, CalendarClock, BellRing, Lightbulb, FileBarChart2, Sparkles,
  Database, Brain, LineChart as LineChartIcon, ShieldCheck, ArrowRight, Pill, Droplet,
} from "lucide-react";

const FEATURES = [
  { icon: TrendingUp, title: "Medicine & Blood Demand Analysis", text: "Daily, weekly, monthly and yearly demand patterns across every medicine and blood segment." },
  { icon: Sparkles, title: "Demand Forecasting", text: "Linear Regression, Random Forest and XGBoost compared on real metrics, with clearly labeled future forecasts." },
  { icon: Package, title: "Inventory Management", text: "Live stock status, batch-level tracking, and low/critical/overstock detection." },
  { icon: CalendarClock, title: "Expiry Management", text: "Near-expiry and expired batch tracking derived directly from real dates." },
  { icon: BellRing, title: "Intelligent Alerts", text: "Shortage, stock and expiry alerts generated from actual calculated conditions." },
  { icon: Lightbulb, title: "Smart Recommendations", text: "Every recommendation explains the real data behind it — never guesswork." },
  { icon: FileBarChart2, title: "Reports & Analytics", text: "Dedicated demand, forecast, inventory, expiry, alert and recommendation reports." },
  { icon: Brain, title: "AI-Powered Chatbot", text: "Ask natural-language questions and get answers grounded in the live database." },
];

const FLOW = [
  { icon: Database, label: "Data" }, { icon: TrendingUp, label: "Demand Analysis" }, { icon: Brain, label: "Machine Learning" },
  { icon: Sparkles, label: "Forecasting" }, { icon: Package, label: "Inventory Analysis" }, { icon: CalendarClock, label: "Expiry Monitoring" },
  { icon: Lightbulb, label: "Recommendations" }, { icon: BellRing, label: "Alerts" }, { icon: FileBarChart2, label: "Reports" }, { icon: Sparkles, label: "AI Assistant" },
];

export default function Landing() {
  return (
    <div className="landing">
      <header className="landing-nav">
        <div className="row gap-2">
          <div className="sidebar-logo"><Activity size={18} /></div>
          <span className="text-h1">MedBlood Intelligence</span>
        </div>
        <Link to="/login" className="btn btn-primary">Login</Link>
      </header>

      <section className="landing-hero">
        <span className="badge badge-accent" style={{ marginBottom: 16 }}>Healthcare + AI Analytics Platform</span>
        <h1 className="landing-title">Integrated Medicine &amp; Blood Management</h1>
        <p className="landing-subtitle">
          Demand prediction, inventory monitoring and intelligent recommendations powered by machine learning.
        </p>
        <div className="row gap-3" style={{ marginTop: 28 }}>
          <Link to="/login" className="btn btn-primary">Login <ArrowRight size={15} /></Link>
          <a href="#features" className="btn btn-secondary">Explore Features</a>
        </div>
      </section>

      <section id="features" className="landing-section">
        <h2 className="text-display" style={{ textAlign: "center", marginBottom: 8 }}>Everything the system can do</h2>
        <p className="text-secondary" style={{ textAlign: "center", marginBottom: 32 }}>One consistent platform for medicine and blood resource intelligence.</p>
        <div className="grid grid-cols-4">
          {FEATURES.map((f) => (
            <div className="card stack gap-2" key={f.title}>
              <div className="kpi-icon kpi-icon-accent"><f.icon size={18} /></div>
              <div className="text-h2" style={{ fontSize: 15 }}>{f.title}</div>
              <div className="text-small">{f.text}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section" style={{ background: "var(--color-surface)" }}>
        <h2 className="text-display" style={{ textAlign: "center", marginBottom: 32 }}>How it works</h2>
        <div className="landing-flow">
          {FLOW.map((f, i) => (
            <div className="landing-flow-step" key={i}>
              <div className="kpi-icon kpi-icon-primary"><f.icon size={16} /></div>
              <span className="text-small" style={{ fontWeight: 600 }}>{f.label}</span>
              {i < FLOW.length - 1 && <ArrowRight size={14} className="landing-flow-arrow" />}
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2 className="text-display" style={{ textAlign: "center", marginBottom: 32 }}>Built for three roles</h2>
        <div className="grid grid-cols-3">
          <div className="card stack gap-2">
            <div className="kpi-icon kpi-icon-info"><ShieldCheck size={18} /></div>
            <div className="text-h2" style={{ fontSize: 15 }}>Admin</div>
            <p className="text-small">Manages users, monitors system-wide alerts, and oversees medicine and blood operations.</p>
          </div>
          <div className="card stack gap-2">
            <div className="kpi-icon kpi-icon-primary"><Pill size={18} /></div>
            <div className="text-h2" style={{ fontSize: 15 }}>Pharmacist</div>
            <p className="text-small">Analyzes medicine demand, forecasts, inventory, expiry, alerts and recommendations.</p>
          </div>
          <div className="card stack gap-2">
            <div className="kpi-icon kpi-icon-blood"><Droplet size={18} /></div>
            <div className="text-h2" style={{ fontSize: 15 }}>Blood Staff</div>
            <p className="text-small">Tracks blood demand, supply, inventory, expiry, alerts and recommendations.</p>
          </div>
        </div>
      </section>

      <section className="landing-section">
        <div className="card stack gap-3" style={{ maxWidth: 760, margin: "0 auto" }}>
          <div className="row gap-2"><LineChartIcon size={18} style={{ color: "var(--color-primary-500)" }} /><span className="text-h2">About this project</span></div>
          <p className="text-secondary">
           MedBlood is an integrated medicine and blood resource management platform designed to help healthcare organizations make better, data-driven decisions about essential resources. By combining inventory monitoring, expiry management, demand analysis, alerts, and machine-learning-based forecasting, the system can help identify potential shortages early, reduce excess or expired stock, and support timely resource planning.
The platform demonstrates how machine learning and centralized resource management can improve the availability of critical medicines and blood supplies, reduce wastage, and support more efficient healthcare inventory management. This academic project uses demonstration datasets and does not represent actual hospital, pharmacy, or blood-bank records.
This gives your project a much stronger message: the project isn't just storing data—it is designed to help prevent shortages, reduce wastage, and support better healthcare decisions.
          </p>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="row-between wrap gap-3">
          <span className="text-h2" style={{ fontSize: 14 }}>MedBlood Intelligence Platform</span>
          <span className="text-small">React · MySQL · Scikit-learn · XGBoost</span>
        </div>
        <p className="text-micro" style={{ marginTop: 10 }}>An Integrated medicine and Blood Management and Prediction Platform</p>
      </footer>
    </div>
  );
}
