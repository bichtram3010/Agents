"""
Guardrail chống prompt injection cho chatbot khách hàng.

- check_input(text): câu khách gõ có phải tấn công không (đòi bỏ quy tắc, đòi lộ
  system prompt / key, giả vai admin / chế độ không giới hạn, token chat-template,
  đòi xuất hàng loạt thông tin khách). Chặn TRƯỚC khi câu vào session, cache hay LLM.
- check_output(text): câu trả lời có lộ nội bộ không (API key, tên biến môi trường,
  đoạn system prompt của agent).

Chỉ dùng regex trên văn bản đã chuẩn hóa (bỏ dấu, chữ thường): rẻ, không tốn lượt
LLM, kết quả cố định. Đổi lại sẽ lọt câu tấn công diễn đạt lạ. Đo bằng
`python -m backend.scripts.eval_guardrails` trên evals/injection_cases.csv.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .tools.shipping_zones import normalize

REFUSAL_MESSAGE = (
    "Xin lỗi, mình chỉ hỗ trợ tư vấn sản phẩm, tồn kho, phí ship và báo giá của shop. "
    "Yêu cầu này nằm ngoài phạm vi nên mình không thực hiện được."
)
LEAK_MESSAGE = "Xin lỗi, mình không thể chia sẻ thông tin nội bộ của hệ thống."


@dataclass(frozen=True)
class Verdict:
    blocked: bool
    reason: str = ""


# ── Đầu vào: khớp trên văn bản đã normalize() (không dấu, chữ thường, bỏ dấu câu) ──
_INPUT_RULES: list[tuple[str, re.Pattern]] = [
    ("override_rules", re.compile(
        r"\b(ignore|disregard|forget|override|bypass|skip)\b.{0,40}"
        r"\b(instructions?|rules?|prompts?|guidelines?|directions?|guardrails?)\b")),
    ("override_rules", re.compile(
        r"\b(bo qua|quen|phot lo|vo hieu hoa|khong can tuan theo|dung tuan theo)\b.{0,40}"
        r"\b(huong dan|quy tac|chi dan|chi thi|rang buoc|prompt|luat)\b")),
    ("prompt_leak", re.compile(
        r"\b(reveal|show|print|repeat|output|display|tell me|give me|what (is|are)|translate)\b.{0,40}"
        r"\b(system prompt|(your|the) (instructions|prompt|rules)|initial prompt|hidden prompt|text above)\b")),
    ("prompt_leak", re.compile(
        r"\b(in ra|hien thi|cho (toi|minh|em|tao) (xem|biet)|tiet lo|nhac lai|lap lai|dich|doc)\b.{0,40}"
        r"\b(system prompt|prompt|huong dan (he thong|goc|ban dau|cua ban)|chi thi (he thong|goc)|"
        r"cau lenh he thong|quy tac (cua ban|he thong|noi bo))\b")),
    ("role_play", re.compile(
        r"\b(you are now|act as|pretend (to be|you are)|roleplay as|from now on)\b.{0,50}"
        r"\b(dan|jailbreak|unrestricted|no (rules|limits|restrictions)|developer mode|evil|admin|root)\b")),
    ("role_play", re.compile(
        r"\b(gia vo|dong vai|tu gio|bay gio|tu bay gio)\b.{0,40}"
        r"\b(khong (con )?(gioi han|rang buoc|quy tac|kiem duyet)|dan|admin|quan tri vien|developer|hacker|che do)\b")),
    ("role_play", re.compile(r"\b(developer mode|jailbreak|dan mode|che do (developer|debug|dev|god|khong gioi han))\b")),
    ("privilege", re.compile(
        r"\b(toi|minh|tao|em|i am|i m)\b.{0,6}\b(la )?(admin|quan tri vien|developer|nha phat trien|"
        r"chu shop|ky su he thong|system administrator)\b.{0,60}"
        r"\b(xac nhan|doi|sua|xoa|cap quyen|mo khoa|tiet lo|cho xem|confirm|change|delete|grant|unlock)\b")),
    # Tên biến môi trường thật của hệ thống: khách bình thường không bao giờ gõ
    ("secret_request", re.compile(
        r"\b(woku_api_key|odoo_password|admin_api_key|groq_api_key|langfuse_\w+|odoo_username)\b")),
    ("secret_request", re.compile(
        r"\b(api ?keys?|khoa api|secret|token|bien moi truong|environment variables?|env vars?|"
        r"file env|env file)\b.{0,40}"
        r"\b(la gi|cua ban|cua he thong|bao nhieu|cho|gui|in|hien|show|give|print|what)\b|"
        r"\b(cho|gui|in ra|hien thi|tiet lo|show|give|print|reveal|what is|what s)\b.{0,40}"
        r"\b(api ?keys?|khoa api|mat khau (admin|he thong|odoo|database|quan tri)|secret|token|"
        r"bien moi truong|environment variables?|file env|env file)\b")),
    ("bulk_pii", re.compile(
        r"\b(liet ke|danh sach|tat ca|xuat|dump|toan bo|export|list all|all)\b.{0,40}"
        r"\b(so dien thoai|sdt|email|dia chi|thong tin|phone numbers?|emails?|addresses)\b.{0,20}"
        r"\b(khach|khach hang|nguoi mua|customers?)\b")),
    ("bulk_pii", re.compile(
        r"\b(export|list|dump|give me)\b.{0,20}\b(all )?customers? (emails?|phone numbers?|phones|addresses|data)\b")),
    ("bulk_pii", re.compile(r"\b(tat ca|toan bo|danh sach) (cac )?khach hang\b")),
]

# ── Đầu vào: khớp trên văn bản gốc (token chat-template, tiêm vai "system") ──
_RAW_RULES: list[tuple[str, re.Pattern]] = [
    ("template_token", re.compile(
        r"<\|(im_start|im_end|system|endoftext|eot_id|start_header_id)\|>|\[/?INST\]|<</?SYS>>",
        re.IGNORECASE)),
    ("template_token", re.compile(r"(^|\n)\s*(#{2,}\s*)?(system|assistant)\s*:", re.IGNORECASE)),
]

# ── Đầu ra: lộ key / biến môi trường / đoạn system prompt của agent ──
_OUTPUT_RULES: list[tuple[str, re.Pattern]] = [
    ("api_key", re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9]{16,}|pk-lf-[A-Za-z0-9-]{8,})")),
    ("env_name", re.compile(r"\b(WOKU_API_KEY|ODOO_PASSWORD|ADMIN_API_KEY|GROQ_API_KEY|LANGFUSE_SECRET_KEY)\b")),
    # Câu đặc trưng trong instructions của agent, viết ở dạng đã normalize()
    ("system_prompt", re.compile(
        r"quy trinh 4 buoc bat buoc|hieu slang scenario tieng viet|route ngan gon den dung agent|"
        r"ban tra cuu san pham va kho hang dung dung tool|decode truoc khi tu van")),
]


def check_input(text: str) -> Verdict:
    raw = text or ""
    for reason, pattern in _RAW_RULES:
        if pattern.search(raw):
            return Verdict(True, reason)
    norm = normalize(raw)
    for reason, pattern in _INPUT_RULES:
        if pattern.search(norm):
            return Verdict(True, reason)
    return Verdict(False)


def check_output(text: str) -> Verdict:
    raw = text or ""
    for reason, pattern in _OUTPUT_RULES:
        target = raw if reason != "system_prompt" else normalize(raw)
        if pattern.search(target):
            return Verdict(True, reason)
    return Verdict(False)
