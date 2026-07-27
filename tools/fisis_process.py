"""FISIS raw → processed 가공 (캐피탈 동종사 비교)

raw/ 의 append-only JSON을 읽어 표양식 표준(shared/table_format.md)에 맞춘
processed/*.csv 를 생성한다. raw 는 절대 수정하지 않는다.

시점 매핑 (분기말):
    FY23=202312  FY24=202412  FY25=202512  25.6월=202506  26최신월=202603(202606 미공시)
    Gap = 26최신 - 25.6월

비율 지표: FISIS 공시비율(%)을 그대로 사용(직접 재계산 불가) → Gap은 %p 1열.
금액 지표: 원 단위 → 십억원(÷1e9). Gap은 금액+% 2열.
값이 없으면 "없음" 표기(임의 생성 금지). 음수는 △.

사용:
    python tools/fisis_process.py --sector capital
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_SUBDIR = "202303_202606"

# 시점 → base_month
PERIODS = [
    ("FY23", "202312"),
    ("FY24", "202412"),
    ("FY25", "202512"),
    ("25.6월", "202506"),
    ("26최신월", "202603"),  # 202606 미공시 → 26.1Q 사용
]
GAP_BASE = "202506"   # 25.6월
GAP_LATEST = "202603" # 26최신월

# KB(자사) 최상단, 이후는 자산규모 내림차순으로 런타임 정렬
COMPANIES = {
    "0010250": ("KB캐피탈", "SK"),
    "0010238": ("신한캐피탈", "SK"),
    "0010271": ("현대캐피탈", "ST"),
    "0010268": ("하나캐피탈", "ST"),
    "0010255": ("우리금융캐피탈", "ST"),
    "0013202": ("메리츠캐피탈", "ST"),
}
SELF_CD = "0010250"

BILLION = 1_000_000_000  # 원 → 십억원


def load(sector: str, prefix: str, num: str, cd: str) -> dict:
    """{account_cd: {base_month: value_str}} 로 raw 로드."""
    path = REPO_ROOT / sector / "raw" / RAW_SUBDIR / f"{prefix}{num}_{cd}.json"
    if not path.exists():
        return {}
    d = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for r in d["rows"]:
        out.setdefault(r["account_cd"], {})[r["base_month"]] = r.get("a")
    return out


def fmt_ratio(v):
    if v is None or v == "":
        return "없음"
    f = float(v)
    return ("△" + f"{abs(f):g}") if f < 0 else f"{f:g}"


def fmt_amt_billion(v):
    if v is None or v == "":
        return "없음"
    f = float(v) / BILLION
    return ("△" + f"{abs(f):,.1f}") if f < 0 else f"{f:,.1f}"


def gap_pp(base, latest):
    if base in (None, "") or latest in (None, ""):
        return "없음"
    d = float(latest) - float(base)
    return ("△" + f"{abs(d):.2f}") if d < 0 else f"{d:.2f}"


def gap_amt(base, latest):
    """금액 Gap: (Gap금액[십억], Gap%)

    기준값(25.6월)이 0 이하이면 증감률(%)은 수학적으로 의미가 없으므로 'N/A' 표기.
    """
    if base in (None, "") or latest in (None, ""):
        return "없음", "없음"
    b, l = float(base) / BILLION, float(latest) / BILLION
    diff = l - b
    g_amt = ("△" + f"{abs(diff):,.1f}") if diff < 0 else f"{diff:,.1f}"
    if b <= 0:
        g_pct = "N/A(기준≤0)"
    else:
        pct = diff / b * 100
        g_pct = ("△" + f"{abs(pct):.1f}") if pct < 0 else f"{pct:.1f}"
    return g_amt, g_pct


def order_companies(sector: str):
    """KB 최상단 → 총자산(평잔, SK/ST009 account A) 202603 내림차순."""
    size = {}
    for cd, (nm, pfx) in COMPANIES.items():
        acc = load(sector, pfx, "009", cd)
        v = acc.get("A", {}).get(GAP_LATEST)
        size[cd] = float(v) if v else -1
    others = [cd for cd in COMPANIES if cd != SELF_CD]
    others.sort(key=lambda c: size[c], reverse=True)
    return [SELF_CD] + others


def build_ratio_csv(sector: str, order, out_path: Path, spec):
    """spec: list of (prefix_num, account_cd, 항목명, 비고)"""
    header = ["회사명", "financeCd", "항목", *[p[0] for p in PERIODS], "Gap(%p)", "비고"]
    rows = []
    for cd in order:
        nm, pfx = COMPANIES[cd]
        for num, acct, label, note in spec:
            acc = load(sector, pfx, num, cd)
            series = acc.get(acct, {})
            vals = [fmt_ratio(series.get(bm)) for _, bm in PERIODS]
            g = gap_pp(series.get(GAP_BASE), series.get(GAP_LATEST))
            rows.append([nm, cd, label, *vals, g, note])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"저장: {out_path} ({len(rows)}행)")


def build_amount_csv(sector: str, order, out_path: Path, spec):
    header = ["회사명", "financeCd", "항목", *[p[0] for p in PERIODS], "Gap금액", "Gap%", "비고"]
    rows = []
    for cd in order:
        nm, pfx = COMPANIES[cd]
        for num, acct, label, note in spec:
            acc = load(sector, pfx, num, cd)
            series = acc.get(acct, {})
            vals = [fmt_amt_billion(series.get(bm)) for _, bm in PERIODS]
            g_amt, g_pct = gap_amt(series.get(GAP_BASE), series.get(GAP_LATEST))
            rows.append([nm, cd, label, *vals, g_amt, g_pct, note])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"저장: {out_path} ({len(rows)}행)")


def main(sector: str):
    order = order_companies(sector)
    print("회사 순서(KB→자산규모순):", [COMPANIES[c][0] for c in order])

    # 수익성 — 공시비율(%)
    build_ratio_csv(
        sector, order,
        REPO_ROOT / sector / "processed" / "수익성" / "수익성_공시비율.csv",
        [
            ("009", "F", "ROA(공시,%)", "총자산순이익률, FISIS 공시비율(연환산)"),
            ("009", "J", "ROE(공시,%)", "자기자본순이익률, FISIS 공시비율(연환산)"),
        ],
    )
    # 수익성 — 규모 참고(십억원)
    build_amount_csv(
        sector, order,
        REPO_ROOT / sector / "processed" / "수익성" / "규모참고_십억원.csv",
        [
            ("009", "A", "총자산 평잔(십억원)", "저량/평잔"),
            ("009", "I", "자본 평잔(십억원)", "저량/평잔"),
            ("009", "E", "당기순이익(십억원)", "FISIS 공시(연환산 기준) — 분기 단독 아님, 각주 필수"),
        ],
    )

    # 건전성 — 공시비율(%)
    build_ratio_csv(
        sector, order,
        REPO_ROOT / sector / "processed" / "건전성" / "건전성_공시비율.csv",
        [
            ("008", "D", "고정이하여신비율(공시,%)", "여신건전성표"),
            ("117", "B", "연체채권비율(공시,%)", "연체채권비율표"),
            ("008", "F", "대손충당금적립률(총여신대비,공시,%)", "확정: 총여신 대비 기준(SK/ST008 account F)"),
        ],
    )
    # 건전성 — 규모 참고(십억원)
    build_amount_csv(
        sector, order,
        REPO_ROOT / sector / "processed" / "건전성" / "규모참고_십억원.csv",
        [
            ("008", "A", "건전성분류 총채권(십억원)", "저량/기말"),
            ("008", "A4", "고정이하여신(십억원)", "저량/기말"),
            ("008", "C", "대손충당금 실적립액(십억원)", "저량/기말"),
        ],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sector", default="capital")
    a = p.parse_args()
    main(a.sector)
