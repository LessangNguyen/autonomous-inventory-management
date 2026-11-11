import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, session, type User } from "./api";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import ForecastsPage from "./pages/ForecastsPage";
import RecommendationsPage from "./pages/RecommendationsPage";
import OrdersPage from "./pages/OrdersPage";
import ProductsPage from "./pages/ProductsPage";
import ImportPage from "./pages/ImportPage";
import AlertsPage from "./pages/AlertsPage";
import AgentPage from "./pages/AgentPage";

type AuthState = {
  user: User | null;
  tenant: string;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (payload: { store_name: string; full_name: string; email: string; password: string }) => Promise<void>;
  signOut: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

const NAV = [
  { to: "/", label: "Tổng quan", icon: "◧" },
  { to: "/forecasts", label: "Dự báo nhu cầu", icon: "◔" },
  { to: "/recommendations", label: "Đề xuất nhập hàng", icon: "◈" },
  { to: "/orders", label: "Đơn nhập hàng", icon: "▤" },
  { to: "/products", label: "Sản phẩm & kho", icon: "▦" },
  { to: "/imports", label: "Nhập dữ liệu", icon: "⇪" },
  { to: "/alerts", label: "Cảnh báo", icon: "◉" },
  { to: "/agent", label: "Trợ lý AI", icon: "✦" },
];

const TITLES: Record<string, string> = {
  "/": "Tổng quan cửa hàng",
  "/forecasts": "Dự báo nhu cầu",
  "/recommendations": "Đề xuất nhập hàng",
  "/orders": "Đơn nhập hàng",
  "/products": "Sản phẩm & kho",
  "/imports": "Nhập dữ liệu",
  "/alerts": "Cảnh báo",
  "/agent": "Trợ lý AI",
};

export default function App() {
  const [user, setUser] = useState<User | null>(session.user);
  const [tenant, setTenant] = useState<string>(session.tenant);

  const value = useMemo<AuthState>(
    () => ({
      user,
      tenant,
      signIn: async (email, password) => {
        const result = await api.login(email, password);
        session.save(result.access_token, result.user, result.tenant_name);
        setUser(result.user);
        setTenant(result.tenant_name);
      },
      signUp: async (payload) => {
        const result = await api.register(payload);
        session.save(result.access_token, result.user, result.tenant_name);
        setUser(result.user);
        setTenant(result.tenant_name);
      },
      signOut: () => {
        session.clear();
        setUser(null);
        setTenant("");
      },
    }),
    [user, tenant],
  );

  useEffect(() => {
    const handler = () => setUser(null);
    window.addEventListener("aim:unauthorized", handler);
    return () => window.removeEventListener("aim:unauthorized", handler);
  }, []);

  return (
    <AuthContext.Provider value={value}>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
        <Route path="*" element={user ? <Shell /> : <Navigate to="/login" replace />} />
      </Routes>
    </AuthContext.Provider>
  );
}

function Shell() {
  const { user, tenant, signOut } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const title = TITLES[location.pathname] ?? "Inventory AI";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AI</div>
          <div>
            <div className="brand-name">Inventory AI</div>
            <div className="brand-sub">Autonomous Management</div>
          </div>
        </div>
        <nav>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="tenant">{tenant || "Cửa hàng"}</div>
          <div className="tenant-plan">Gói dùng thử · {user?.full_name}</div>
          <button
            className="btn btn-ghost btn-block"
            onClick={() => {
              signOut();
              navigate("/login");
            }}
          >
            Đăng xuất
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            <p className="muted">
              Cập nhật {new Date().toLocaleDateString("vi-VN")}
            </p>
          </div>
          <div className="topbar-actions">
            <NavLink to="/agent" className="btn btn-primary">
              ✦ Hỏi trợ lý AI
            </NavLink>
          </div>
        </header>
        <div className="content">
          <Routes>
            <Route index element={<DashboardPage />} />
            <Route path="forecasts" element={<ForecastsPage />} />
            <Route path="recommendations" element={<RecommendationsPage />} />
            <Route path="orders" element={<OrdersPage />} />
            <Route path="products" element={<ProductsPage />} />
            <Route path="imports" element={<ImportPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="agent" element={<AgentPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
