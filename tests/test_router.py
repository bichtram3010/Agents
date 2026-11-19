"""Keyword pre-router: the README's own test questions must reach the right agent."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Load router.py by path: importing backend.agents would build every Agno agent.
_ROUTER = Path(__file__).resolve().parents[1] / "backend" / "agents" / "router.py"
_spec = importlib.util.spec_from_file_location("router_under_test", _ROUTER)
router = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(router)


README_QUESTIONS = [
    # Consultant + RAG
    ("Da mình hay bóng nhờn, lỗ chân lông to — dùng gì?", "consultant"),
    ("Sắp đi quân sự 2 tuần, tư vấn kem chống nắng cho sinh viên", "consultant"),
    ("Outfit phỏng vấn cho nữ 22 tuổi, tone trầm", "consultant"),
    ("Da mụn ẩn, ngân sách 1 triệu, routine buổi sáng", "consultant"),
    # Products and stock
    ("Liệt kê tất cả sản phẩm skincare dưới 500k", "product_stock"),
    ("SKU nào tồn kho dưới 30?", "product_stock"),
    ("Top 5 sản phẩm giá cao nhất", "analytics"),
    # Orders and sales
    ("Tạo báo giá cho khách Nguyễn Văn A, SĐT 0901234567, 2 áo thun FSH-TS-001", "sales"),
    ("Doanh thu các đơn đã xác nhận", "analytics"),
    ("Tìm khách hàng tên Trâm", "sales"),
    # Shipping
    ("Phí ship về Đà Nẵng đơn 300k", "shipping"),
    ("Hỏa tốc về Quận 1 HCM giá bao nhiêu?", "shipping"),
    ("Mua 600k có miễn ship không?", "shipping"),
    # Multi-shop comparison
    ("So sánh giá kem chống nắng COS-SK-021 giữa các shop", "comparison"),
    ("Shop nào đang bán phá giá?", "comparison"),
    ("Phí ship về Hà Nội từ 3 shop, đơn 400k", "comparison"),
    ("Mua son lì ở đâu tốt nhất, giao về HCM?", "comparison"),
    ("Tổng quan thị trường skincare — shop nào giá tốt nhất?", "comparison"),
]


@pytest.mark.parametrize("question,agent", README_QUESTIONS)
def test_readme_questions_route_to_expected_agent(question, agent):
    assert router.pre_route(question) == agent


@pytest.mark.parametrize("question,agent", [
    # Whole words only: "áo" must not match inside "báo", "top" not inside "croptop"
    ("Áo croptop giá bao nhiêu?", "product_stock"),
    ("Thống kê đơn hàng theo danh mục", "analytics"),
    ("Xem đơn hàng tuần này", "sales"),
    ("Doanh thu tuần này", "analytics"),
])
def test_edge_cases(question, agent):
    assert router.pre_route(question) == agent


def test_unclear_question_falls_back_to_supervisor():
    assert router.pre_route("Xin chào") is None


# ── Follow-up questions keep the previous agent (idea from agent-squad's classifier) ──

def test_follow_up_with_generic_word_stays_with_previous_agent():
    # "giá" alone would send this to ProductStock, but it refers to what Consultant suggested
    assert router.pre_route("Cái đó giá bao nhiêu?", last_agent="consultant") == "consultant"


def test_follow_up_without_keyword_stays_with_previous_agent():
    assert router.pre_route("Còn loại nào rẻ hơn không?", last_agent="consultant") == "consultant"


def test_clear_new_intent_beats_previous_agent():
    assert router.pre_route("Vậy còn ship về Huế thì sao?", last_agent="consultant") == "shipping"
    assert router.pre_route("Cái đó còn hàng không?", last_agent="consultant") == "product_stock"


def test_no_previous_agent_behaves_as_before():
    assert router.pre_route("Cái đó giá bao nhiêu?") == "product_stock"
    assert router.pre_route("Còn loại nào rẻ hơn không?") is None


def test_non_follow_up_small_talk_is_not_sticky():
    assert router.pre_route("Xin chào", last_agent="shipping") is None


# ── Accuracy on the eval set (evals/router_cases.csv) ─────────────────────────

def test_router_eval_accuracy():
    from backend.scripts.eval_router import evaluate, load_cases

    report = evaluate(load_cases())
    assert report["accuracy"] >= 0.9, report["failures"]
