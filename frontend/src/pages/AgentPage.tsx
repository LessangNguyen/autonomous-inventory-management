import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AgentResponse } from "../api";

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; response: AgentResponse };

const SUGGESTIONS = [
  "Tình hình cửa hàng hôm nay thế nào?",
  "SKU nào sắp hết hàng?",
  "Đề xuất nhập hàng cho tôi",
  "Dự báo nhu cầu SER-001 trong 30 ngày",
  "Doanh thu 30 ngày gần nhất và top sản phẩm",
  "Tạo đơn nhập hàng cho các SKU sắp hết",
];

function RichText({ text }: { text: string }) {
  return (
    <div className="rich">
      {text.split("\n").map((line, index) => {
        const parts = line.split(/\*\*(.+?)\*\*/g);
        return (
          <p key={index} className={line.trim().startsWith("-") ? "bullet" : undefined}>
            {parts.map((part, partIndex) =>
              partIndex % 2 === 1 ? <strong key={partIndex}>{part}</strong> : <span key={partIndex}>{part}</span>,
            )}
          </p>
        );
      })}
    </div>
  );
}

export default function AgentPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showTrace, setShowTrace] = useState<number | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setInput("");
    setError("");
    setMessages((current) => [...current, { role: "user", text: question }]);
    setBusy(true);
    try {
      const response = await api.agentChat(question);
      setMessages((current) => [...current, { role: "assistant", response }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Trợ lý đang bận, thử lại sau.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="agent-layout">
      <div className="card agent-chat">
        <div className="card-head">
          <div>
            <h3>Trợ lý tồn kho</h3>
            <p className="muted">
              Trả lời dựa trên tool được cấp quyền. Hành động ghi dữ liệu chỉ tạo đơn nháp và cần bạn
              phê duyệt.
            </p>
          </div>
        </div>

        <div className="chat-window">
          {messages.length === 0 && (
            <div className="chat-empty">
              <div className="chat-hero">✦</div>
              <h4>Hỏi bất cứ điều gì về tồn kho và nhập hàng</h4>
              <p className="muted">
                Ví dụ: “SKU nào sắp hết?”, “Nên nhập bao nhiêu SER-001?”, “Doanh thu tháng này ra sao?”
              </p>
            </div>
          )}

          {messages.map((message, index) =>
            message.role === "user" ? (
              <div className="bubble user" key={index}>
                {message.text}
              </div>
            ) : (
              <div className="bubble assistant" key={index}>
                <RichText text={message.response.answer} />
                <div className="trace-row">
                  <span className="muted small">
                    {message.response.model} · {message.response.latency_ms}ms ·{" "}
                    {message.response.tool_calls.length} tool
                  </span>
                  {message.response.tool_calls.length > 0 && (
                    <button
                      className="link small"
                      onClick={() => setShowTrace(showTrace === index ? null : index)}
                    >
                      {showTrace === index ? "Ẩn tool call" : "Xem tool call"}
                    </button>
                  )}
                </div>
                {message.response.pending_purchase_order_id && (
                  <div className="alert alert-warning">
                    Đơn nháp #{message.response.pending_purchase_order_id} đang chờ phê duyệt.{" "}
                    <Link to="/orders" className="link">
                      Mở đơn nhập hàng
                    </Link>
                  </div>
                )}
                {showTrace === index && (
                  <div className="trace">
                    {message.response.tool_calls.map((call, callIndex) => (
                      <div key={callIndex} className="trace-item">
                        <code>{call.tool}</code>
                        <span className={call.ok ? "badge success" : "badge danger"}>
                          {call.ok ? "OK" : "Lỗi"}
                        </span>
                        <pre>{JSON.stringify(call.arguments, null, 2)}</pre>
                        <p className="muted small">{call.result_summary}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ),
          )}
          {busy && <div className="bubble assistant typing">Đang kiểm tra dữ liệu…</div>}
          {error && <div className="alert alert-error">{error}</div>}
          <div ref={bottom} />
        </div>

        <div className="chat-input">
          <input
            value={input}
            placeholder="Nhập câu hỏi…"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send(input);
              }
            }}
          />
          <button className="btn btn-primary" onClick={() => send(input)} disabled={busy || !input.trim()}>
            Gửi
          </button>
        </div>
      </div>

      <div className="card agent-side">
        <h4>Gợi ý câu hỏi</h4>
        <div className="stack gap-sm">
          {SUGGESTIONS.map((suggestion) => (
            <button key={suggestion} className="suggestion" onClick={() => send(suggestion)} disabled={busy}>
              {suggestion}
            </button>
          ))}
        </div>
        <div className="divider" />
        <h4>Nguyên tắc an toàn</h4>
        <ul className="safety">
          <li>Chỉ gọi tool trong allowlist</li>
          <li>Không tự gửi đơn cho nhà cung cấp</li>
          <li>Mọi đơn nhập đều ở trạng thái nháp</li>
          <li>Audit log cho mỗi lần chạy</li>
        </ul>
        <p className="muted small">
          Không cấu hình LLM? Trợ lý chạy bằng rule router nội bộ, vẫn trả lời được các câu hỏi chuẩn.
        </p>
      </div>
    </div>
  );
}
