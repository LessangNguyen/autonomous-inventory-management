import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../App";

type Mode = "login" | "register";

export default function LoginPage() {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [registrationOpen, setRegistrationOpen] = useState(true);
  const [checkingSetup, setCheckingSetup] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [storeName, setStoreName] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [demoCreds, setDemoCreds] = useState<{ email: string; password: string } | null>({
    email: "demo@inventory.ai",
    password: "demo1234",
  });

  useEffect(() => {
    let alive = true;
    api
      .authStatus()
      .then((status) => {
        if (!alive) return;
        setRegistrationOpen(status.registration_open);
        if (status.demo_email && status.demo_password) {
          setDemoCreds({ email: status.demo_email, password: status.demo_password });
        }
        // A brand-new installation has no account: start on the setup tab.
        if (!status.initialized && status.registration_open && !status.demo_enabled) {
          setMode("register");
        }
      })
      .catch(() => {
        // Status is a convenience only; login still works if it fails.
      })
      .finally(() => {
        if (alive) setCheckingSetup(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  async function quickDemoLogin() {
    const targetEmail = demoCreds?.email || "demo@inventory.ai";
    const targetPassword = demoCreds?.password || "demo1234";
    setMode("login");
    setEmail(targetEmail);
    setPassword(targetPassword);
    setError("");
    setLoading(true);
    try {
      await signIn(targetEmail, targetPassword);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể đăng nhập bằng tài khoản demo.");
    } finally {
      setLoading(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        await signIn(email, password);
      } else {
        await signUp({ store_name: storeName, full_name: fullName, email, password });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không đăng nhập được.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <section className="auth-hero">
        <div className="brand">
          <div className="brand-mark">AI</div>
          <div>
            <div className="brand-name">Inventory AI</div>
            <div className="brand-sub">Autonomous Inventory Management</div>
          </div>
        </div>
        <h2>Biết mặt hàng nào cần nhập, nhập bao nhiêu và khi nào.</h2>
        <p>
          Dự báo nhu cầu theo SKU, tính điểm đặt hàng lại, phát hiện bất thường và soạn đơn nhập
          nháp — dựa trên dữ liệu bán hàng và tồn kho của chính cửa hàng bạn.
        </p>
        <ul className="hero-points">
          <li>Không cần thay POS đang dùng</li>
          <li>Dự báo 7/14/30 ngày với backtesting theo thời gian</li>
          <li>AI Agent có kiểm soát, con người phê duyệt mọi đơn nhập</li>
        </ul>
        <div className="hero-foot">Bắt đầu bằng dữ liệu của bạn · Không dùng dữ liệu mẫu</div>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="tabs">
            <button
              className={mode === "login" ? "tab active" : "tab"}
              onClick={() => setMode("login")}
              type="button"
            >
              Đăng nhập
            </button>
            {registrationOpen && (
              <button
                className={mode === "register" ? "tab active" : "tab"}
                onClick={() => setMode("register")}
                type="button"
              >
                Tạo cửa hàng
              </button>
            )}
          </div>

          {demoCreds && (
            <div className="demo-callout">
              <div className="demo-callout-header">
                <span className="demo-badge">Tài khoản dùng thử / Demo</span>
                <span className="demo-badge-hint">Dành cho khách test giao diện</span>
              </div>
              <div className="demo-creds-info">
                <div>
                  <span className="demo-label">Email:</span> <code>{demoCreds.email}</code>
                </div>
                <div>
                  <span className="demo-label">Mật khẩu:</span> <code>{demoCreds.password}</code>
                </div>
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-block demo-quick-btn"
                onClick={quickDemoLogin}
                disabled={loading}
              >
                ⚡ Đăng nhập nhanh tài khoản Demo
              </button>
            </div>
          )}

          {mode === "register" && (
            <div className="alert alert-info">
              Lần đầu sử dụng: tạo cửa hàng và tài khoản chủ sở hữu. Sau đó vào{" "}
              <strong>Nhập dữ liệu</strong> để tải sản phẩm, tồn kho và lịch sử bán hàng của bạn.
            </div>
          )}

          <form onSubmit={submit} className="form">
            {mode === "register" && (
              <>
                <label>
                  Tên cửa hàng
                  <input
                    value={storeName}
                    onChange={(event) => setStoreName(event.target.value)}
                    placeholder="Ví dụ: Mỹ phẩm Hoa Sen"
                    required
                    minLength={2}
                  />
                </label>
                <label>
                  Họ tên
                  <input
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder="Nguyễn Văn A"
                    required
                    minLength={2}
                  />
                </label>
              </>
            )}
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </label>
            <label>
              Mật khẩu
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={8}
                required
              />
            </label>

            {error && <div className="alert alert-error">{error}</div>}

            <button className="btn btn-primary btn-block" disabled={loading || checkingSetup}>
              {loading
                ? "Đang xử lý…"
                : mode === "login"
                  ? "Vào dashboard"
                  : "Tạo cửa hàng"}
            </button>
          </form>

          {mode === "login" && (
            <p className="auth-note">
              Chưa có tài khoản? Chọn <strong>Tạo cửa hàng</strong> nếu hệ thống cho phép đăng ký.
            </p>
          )}
        </div>
        <p className="auth-note">
          Dữ liệu được tách riêng theo từng cửa hàng. Hệ thống không tự tạo số liệu mẫu và không
          chia sẻ dữ liệu của bạn.
        </p>
      </section>
    </div>
  );
}
