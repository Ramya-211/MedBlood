import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import ProtectedRoute from "./routes/ProtectedRoute";
import AppShell from "./components/layout/AppShell";

import Landing from "./pages/Landing";
import Login from "./pages/Login";

import AdminDashboard from "./pages/admin/AdminDashboard";
import UserManagement from "./pages/admin/UserManagement";
import PharmacistDashboard from "./pages/pharmacist/Dashboard";
import PharmacistDemand from "./pages/pharmacist/Demand";
import PharmacistForecast from "./pages/pharmacist/Forecast";
import PharmacistInventory from "./pages/pharmacist/Inventory";
import PharmacistExpiry from "./pages/pharmacist/Expiry";
import PharmacistAlerts from "./pages/pharmacist/Alerts";
import PharmacistRecommendations from "./pages/pharmacist/Recommendations";
import PharmacistReports from "./pages/pharmacist/Reports";

import BloodDashboard from "./pages/blood/Dashboard";
import BloodDemand from "./pages/blood/Demand";
import BloodForecast from "./pages/blood/Forecast";
import BloodInventory from "./pages/blood/Inventory";
import BloodExpiry from "./pages/blood/Expiry";
import BloodAlerts from "./pages/blood/Alerts";
import BloodRecommendations from "./pages/blood/Recommendations";
import BloodReports from "./pages/blood/Reports";

function RootRedirect() {
  const { user, homePath } = useAuth();
  return user ? <Navigate to={homePath} replace /> : <Landing />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<Login />} />

          <Route element={<ProtectedRoute allow={["ADMIN"]} />}>
            <Route element={<AppShell />}>
              <Route path="/admin/dashboard" element={<AdminDashboard />} />
            <Route path="/admin/users" element={<UserManagement />} />
            </Route>
          </Route>

          <Route element={<ProtectedRoute allow={["PHARMACIST"]} />}>
            <Route element={<AppShell />}>
              <Route path="/pharmacist/dashboard" element={<PharmacistDashboard />} />
              <Route path="/pharmacist/demand" element={<PharmacistDemand />} />
              <Route path="/pharmacist/forecast" element={<PharmacistForecast />} />
              <Route path="/pharmacist/inventory" element={<PharmacistInventory />} />
              <Route path="/pharmacist/expiry" element={<PharmacistExpiry />} />
              <Route path="/pharmacist/alerts" element={<PharmacistAlerts />} />
              <Route path="/pharmacist/recommendations" element={<PharmacistRecommendations />} />
              <Route path="/pharmacist/reports" element={<PharmacistReports />} />
            </Route>
          </Route>

          <Route element={<ProtectedRoute allow={["BLOOD_STAFF"]} />}>
            <Route element={<AppShell />}>
              <Route path="/blood/dashboard" element={<BloodDashboard />} />
              <Route path="/blood/demand" element={<BloodDemand />} />
              <Route path="/blood/forecast" element={<BloodForecast />} />
              <Route path="/blood/inventory" element={<BloodInventory />} />
              <Route path="/blood/expiry" element={<BloodExpiry />} />
              <Route path="/blood/alerts" element={<BloodAlerts />} />
              <Route path="/blood/recommendations" element={<BloodRecommendations />} />
              <Route path="/blood/reports" element={<BloodReports />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
