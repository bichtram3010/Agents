"""
Đo độ chính xác của keyword pre-router trên evals/router_cases.csv.

Mỗi dòng: question, expected (tên agent, hoặc "-" = để Supervisor quyết định),
last_agent (agent của lượt trước, để trống nếu là câu đầu).

Chạy từ thư mục gốc:
    python -m backend.scripts.eval_router            # in tỉ lệ đúng + các câu sai
    python -m backend.scripts.eval_router --min 0.9  # exit 1 nếu dưới ngưỡng
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
CASES = _ROOT / "evals" / "router_cases.csv"


def _load_router():
    # Nạp router.py theo đường dẫn: import backend.agents sẽ dựng mọi agent Agno.
    path = _ROOT / "backend" / "agents" / "router.py"
    spec = importlib.util.spec_from_file_location("router_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_cases(path: Path = CASES) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return [
            {
                "question": row["question"],
                "expected": None if row["expected"] == "-" else row["expected"],
                "last_agent": row["last_agent"] or None,
            }
            for row in csv.DictReader(f)
        ]


def evaluate(cases: list[dict]) -> dict:
    router = _load_router()
    per_agent: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [đúng, tổng]
    failures = []
    for case in cases:
        got = router.pre_route(case["question"], last_agent=case["last_agent"])
        key = case["expected"] or "supervisor"
        per_agent[key][1] += 1
        if got == case["expected"]:
            per_agent[key][0] += 1
        else:
            failures.append({**case, "got": got})
    correct = sum(ok for ok, _ in per_agent.values())
    return {
        "total": len(cases),
        "correct": correct,
        "accuracy": correct / len(cases) if cases else 0.0,
        "per_agent": dict(per_agent),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--min", type=float, default=None, help="ngưỡng accuracy tối thiểu")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252

    report = evaluate(load_cases())
    print(f"Router accuracy: {report['correct']}/{report['total']} = {report['accuracy']:.1%}")
    for agent, (ok, total) in sorted(report["per_agent"].items()):
        print(f"  {agent:<14} {ok}/{total}")
    for f in report["failures"]:
        prev = f" (sau {f['last_agent']})" if f["last_agent"] else ""
        print(f"  SAI: {f['question']!r}{prev} → {f['got']}, mong đợi {f['expected']}")

    if args.min is not None and report["accuracy"] < args.min:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
