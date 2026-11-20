"""
Đoán vùng vận chuyển (zone) từ địa chỉ khách gõ — dùng chung cho Shipping và Comparison.

Khách gõ tiếng Việt có dấu ("Đà Nẵng", "TP.HCM", "Thừa Thiên Huế"), nên địa chỉ được
chuẩn hóa trước khi so: bỏ dấu, đ → d, bỏ dấu câu, chữ thường. Keyword khớp theo
nguyên từ, để "hn" không khớp bên trong một từ khác. Không dùng embedding: danh sách
tỉnh cố định, tra bảng cho kết quả chắc chắn và kiểm được bằng test.
"""
from __future__ import annotations

import re
import unicodedata

# Tỉnh/thành → zone (bảng giá ở odoo_tools.SHIPPING_TABLE). Keyword viết không dấu.
PROVINCE_ZONE: dict[str, str] = {
    "hcm": "noi_thanh_hcm", "ho chi minh": "noi_thanh_hcm", "tp hcm": "noi_thanh_hcm",
    "sai gon": "noi_thanh_hcm", "saigon": "noi_thanh_hcm",
    "ha noi": "noi_thanh_hn", "hanoi": "noi_thanh_hn", "hn": "noi_thanh_hn",
    "da nang": "mien_trung", "hue": "mien_trung", "quang nam": "mien_trung",
    "quang ngai": "mien_trung", "binh dinh": "mien_trung", "khanh hoa": "mien_trung",
    "nha trang": "mien_trung", "phu yen": "mien_trung",
    "hai phong": "mien_bac", "quang ninh": "mien_bac", "lao cai": "mien_bac",
    "thai nguyen": "mien_bac", "bac giang": "mien_bac", "thanh hoa": "mien_bac",
    "nghe an": "mien_bac", "ha tinh": "mien_bac",
    "can tho": "mien_nam_xa", "an giang": "mien_nam_xa", "kien giang": "mien_nam_xa",
    "ca mau": "mien_nam_xa", "soc trang": "mien_nam_xa", "dong thap": "mien_nam_xa",
    "vung tau": "mien_nam_xa", "ba ria": "mien_nam_xa",
}

DEFAULT_ZONE = "khac"


def normalize(text: str) -> str:
    """'TP.Hồ Chí Minh' → 'tp ho chi minh'."""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(text.split())


_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(PROVINCE_ZONE, key=len, reverse=True)) + r")\b"
)


def resolve_zone(address: str) -> str:
    """Zone của địa chỉ; không nhận ra tỉnh nào → 'khac'."""
    match = _PATTERN.search(normalize(address or ""))
    return PROVINCE_ZONE[match.group(1)] if match else DEFAULT_ZONE
