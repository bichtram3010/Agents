"use client";

/**
 * Header cho CopilotPopup: tiêu đề + nút đóng + gợi ý bấm nhanh.
 * Gợi ý là danh sách cố định (không gọi LLM để sinh gợi ý, tiết kiệm lượt gọi),
 * chỉ hiện khi cuộc trò chuyện chưa có tin nhắn nào.
 */
import { useChatContext } from "@copilotkit/react-ui";
import { useCopilotChat } from "@copilotkit/react-core";
import { Role, TextMessage } from "@copilotkit/runtime-client-gql";

const SUGGESTIONS = [
  { icon: "🧴", label: "Tư vấn da dầu", text: "Da mình bị dầu, nên dùng kem chống nắng nào?" },
  { icon: "🚚", label: "Phí ship", text: "Phí ship về Hà Nội đơn 400k là bao nhiêu?" },
  { icon: "🏷️", label: "So sánh 3 shop", text: "So sánh giá son lì COS-MK-022 giữa các shop" },
  { icon: "📦", label: "Sắp hết hàng", text: "Sản phẩm nào sắp hết hàng?" },
];

export default function ChatHeader() {
  const { labels, setOpen } = useChatContext();
  const { visibleMessages, appendMessage, isLoading } = useCopilotChat();
  const fresh = visibleMessages.length === 0;

  const ask = (text: string) =>
    appendMessage(new TextMessage({ role: Role.User, content: text }));

  return (
    <div className="ck-header">
      <div className="ck-header-bar">
        <div className="ck-header-title">
          <span className="ck-avatar" aria-hidden>✨</span>
          <div>
            <div className="ck-title">{labels.title}</div>
            <div className="ck-subtitle">Tư vấn · Tồn kho · Phí ship · Báo giá</div>
          </div>
        </div>
        <button className="ck-close" aria-label="Đóng" onClick={() => setOpen(false)}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {fresh && (
        <div className="ck-suggestions">
          {SUGGESTIONS.map((s) => (
            <button key={s.label} className="ck-chip" disabled={isLoading} onClick={() => ask(s.text)}
                    title={s.text}>
              <span aria-hidden>{s.icon}</span> {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
