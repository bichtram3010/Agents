"""
Đo guardrail đầu vào trên evals/injection_cases.csv (text, label = attack | benign)
cộng toàn bộ câu trong evals/router_cases.csv (coi là câu bình thường).
Không gọi LLM.

Chạy từ thư mục gốc:
    python -m backend.scripts.eval_guardrails
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.guardrails import check_input  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
INJECTION_CASES = _ROOT / "evals" / "injection_cases.csv"
ROUTER_CASES = _ROOT / "evals" / "router_cases.csv"


def load_cases() -> list[dict]:
    with INJECTION_CASES.open(encoding="utf-8", newline="") as f:
        cases = [{"text": r["text"], "label": r["label"]} for r in csv.DictReader(f)]
    with ROUTER_CASES.open(encoding="utf-8", newline="") as f:
        cases += [{"text": r["question"], "label": "benign"} for r in csv.DictReader(f)]
    return cases


def evaluate(cases: list[dict]) -> dict:
    attacks = [c for c in cases if c["label"] == "attack"]
    benign = [c for c in cases if c["label"] == "benign"]
    missed = [c["text"] for c in attacks if not check_input(c["text"]).blocked]
    false_pos = [(c["text"], check_input(c["text"]).reason) for c in benign if check_input(c["text"]).blocked]
    return {
        "attacks": len(attacks),
        "blocked": len(attacks) - len(missed),
        "benign": len(benign),
        "false_positives": false_pos,
        "missed": missed,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    r = evaluate(load_cases())
    print(f"Chặn tấn công : {r['blocked']}/{r['attacks']} = {r['blocked'] / r['attacks']:.1%}")
    print(f"Chặn nhầm     : {len(r['false_positives'])}/{r['benign']} câu bình thường")
    for text in r["missed"]:
        print(f"  LỌT : {text!r}")
    for text, reason in r["false_positives"]:
        print(f"  NHẦM: {text!r} ({reason})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
