"""
FISIS Open API 수집 파이프라인

메타(권역→통계목록→계정항목→회사) 를 먼저 전수 수집해 카탈로그를 만들고,
그 카탈로그를 근거로 실제 수치를 조회해 raw/ 에 적재한다.

인증키는 환경변수로만 받는다. 스크립트·리포에 절대 하드코딩하지 않는다.
    export FISIS_AUTH_KEY="발급받은인증키"

사용:
    # 1단계: 메타 카탈로그 수집 (여전업권 K/T/N/C + 저축은행 E)
    python tools/fisis_collect.py catalog

    # 2단계: 특정 회사 데이터 조회
    python tools/fisis_collect.py fetch --finance-cd 0010250 --list-no XX000 \
        --term Q --start 202303 --end 202606 --sector capital
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_URL = "http://fisis.fss.or.kr/openapi"
REPO_ROOT = Path(__file__).resolve().parent.parent

# 이 프로젝트에서 관심 있는 권역만
SECTORS = {
    "capital": {
        "label": "여신전문금융업",
        "divs": {
            "K": "리스사",
            "T": "할부금융사",
            "N": "신기술금융사",
            "C": "신용카드사",
        },
    },
    "savings-bank": {
        "label": "상호저축은행",
        "divs": {"E": "상호저축은행"},
    },
}

SML_DIVS = {
    "A": "일반현황",
    "B": "재무현황",
    "C": "주요경영지표",
    "D": "주요영업활동",
    "P": "보도자료통계",
}

REQUEST_INTERVAL_SEC = 0.4  # 일일 허용횟수 고려, 과도한 연속호출 방지

# 만나면 즉시 수집을 중단해야 하는 치명적 상태.
#   020 일일 허용횟수 초과 / 021 허용 IP 아님 / HTTP 429 Too Many Requests
# 이런 상황에서 계속 호출하면 남은 쿼터만 낭비하고 IP 차단 위험이 커진다.
FATAL_ERR_CDS = {"020", "021"}


class FisisFatalError(RuntimeError):
    """수집 전체를 즉시 중단시켜야 하는 오류(쿼터 초과/IP 차단/429)."""


class FisisApiError(RuntimeError):
    """개별 호출 실패(누락 파라미터 등). 해당 항목만 건너뛰고 계속 가능."""


def auth_key() -> str:
    key = os.environ.get("FISIS_AUTH_KEY")
    if not key:
        sys.exit('환경변수 FISIS_AUTH_KEY 미설정. export FISIS_AUTH_KEY="인증키" 후 재실행.')
    return key


def call(endpoint: str, params: dict) -> ET.Element:
    """API 호출 후 XML 루트 반환. err_cd 검사 포함.

    치명적 상태(020/021/HTTP 429)는 FisisFatalError 로 올려 수집을 중단시킨다.
    그 외 err_cd 는 FisisApiError 로 올려 호출부가 해당 항목만 건너뛸 수 있게 한다.
    """
    params = {"lang": "kr", "auth": auth_key(), **params}
    url = f"{BASE_URL}/{endpoint}.xml?{urllib.parse.urlencode(params)}"
    ctx = f"{endpoint} {params.get('lrgDiv') or params.get('partDiv') or params.get('listNo') or ''}".strip()
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise FisisFatalError(f"HTTP 429 Too Many Requests ({ctx}) — 수집 중단") from e
        raise FisisApiError(f"HTTP {e.code} ({ctx})") from e

    # FISIS는 euc-kr 응답 사례가 있어 방어적으로 디코딩
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            text = body.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise FisisApiError(f"응답 디코딩 실패 ({ctx})")

    root = ET.fromstring(text)
    err_cd = root.findtext("err_cd")
    if err_cd != "000":
        msg = f"API 오류 {err_cd}: {root.findtext('err_msg')} ({ctx})"
        if err_cd in FATAL_ERR_CDS:
            raise FisisFatalError(msg + " — 수집 중단")
        raise FisisApiError(msg)

    time.sleep(REQUEST_INTERVAL_SEC)
    return root


def rows(root: ET.Element) -> list[dict]:
    out = []
    for row in root.iterfind("./list/row"):
        out.append({child.tag: (child.text or "").strip() for child in row})
    return out


# ---------------------------------------------------------------- 1단계: 카탈로그

def build_catalog(sector: str):
    """권역별 통계목록 + 계정항목 + 회사목록을 전수 수집해 카탈로그 JSON 생성."""
    cfg = SECTORS[sector]
    catalog = {"sector": sector, "label": cfg["label"], "divisions": {}}
    aborted = None

    try:
        for div_cd, div_nm in cfg["divs"].items():
            print(f"\n=== [{div_cd}] {div_nm} ===")
            entry = {"name": div_nm, "companies": [], "statistics": []}

            # 회사 목록 (FisisFatalError 는 잡지 않고 위로 전파 → 수집 중단)
            try:
                entry["companies"] = rows(call("companySearch", {"partDiv": div_cd}))
                print(f"  회사 {len(entry['companies'])}건")
            except FisisApiError as e:
                print(f"  회사 조회 실패: {e}")

            # 통계표 목록 (소분류별)
            for sml_cd, sml_nm in SML_DIVS.items():
                try:
                    stats = rows(call("statisticsListSearch", {"lrgDiv": div_cd, "smlDiv": sml_cd}))
                except FisisApiError as e:
                    print(f"  [{sml_cd}] {sml_nm} 조회 실패: {e}")
                    continue
                if not stats:
                    continue
                print(f"  [{sml_cd}] {sml_nm}: 통계표 {len(stats)}건")

                # 각 통계표의 계정항목까지 바인딩
                for st in stats:
                    list_no = st.get("list_no")
                    try:
                        st["accounts"] = rows(call("accountListSearch", {"listNo": list_no}))
                    except FisisApiError as e:
                        st["accounts"] = []
                        print(f"      {list_no} 계정항목 실패: {e}")
                    st["sml_div_cd"] = sml_cd
                    print(f"      {list_no} {st.get('list_nm')} (계정 {len(st['accounts'])}개)")
                entry["statistics"].extend(stats)

            catalog["divisions"][div_cd] = entry
    except FisisFatalError as e:
        # 쿼터 초과/IP 차단/429: 여기까지 모은 부분 카탈로그를 저장하고 중단한다.
        aborted = str(e)
        print(f"\n!! 치명적 오류로 수집 중단: {e}")
        print("!! 여기까지 수집한 부분 카탈로그를 저장한다.")
        catalog["aborted"] = aborted

    out_path = REPO_ROOT / sector / "schema" / "fisis_catalog.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n카탈로그 저장: {out_path}")

    _write_catalog_md(sector, catalog)

    if aborted:
        # 호출자(및 셸)가 중단을 인지하도록 비정상 종료
        sys.exit(f"수집이 완료되지 않음(부분 저장됨): {aborted}")


def _write_catalog_md(sector: str, catalog: dict):
    """사람이 읽을 수 있는 카탈로그 요약 md 생성."""
    lines = [f"# FISIS 통계 카탈로그 — {catalog['label']}", "",
             "`fisis_catalog.json`의 사람이 읽는 요약. 자동 생성물이므로 직접 수정하지 말 것.", ""]
    for div_cd, entry in catalog["divisions"].items():
        lines.append(f"## [{div_cd}] {entry['name']}")
        lines.append("")
        lines.append(f"- 등록 회사 수: {len(entry['companies'])}")
        if entry["companies"]:
            lines.append("")
            lines.append("<details><summary>회사 목록</summary>")
            lines.append("")
            lines.append("| finance_cd | finance_nm |")
            lines.append("|---|---|")
            for c in entry["companies"]:
                lines.append(f"| {c.get('finance_cd','')} | {c.get('finance_nm','')} |")
            lines.append("")
            lines.append("</details>")
        lines.append("")
        lines.append("### 통계표")
        lines.append("")
        lines.append("| list_no | 통계명 | 분류 | 계정항목수 |")
        lines.append("|---|---|---|---|")
        for st in entry["statistics"]:
            lines.append(
                f"| {st.get('list_no','')} | {st.get('list_nm','')} | "
                f"{st.get('sml_div_nm', SML_DIVS.get(st.get('sml_div_cd',''),''))} | {len(st.get('accounts',[]))} |"
            )
        lines.append("")

    out = REPO_ROOT / sector / "schema" / "fisis_catalog.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"카탈로그 요약 저장: {out}")


# ---------------------------------------------------------------- 2단계: 수치 조회

def fetch_stats(finance_cd: str, list_no: str, term: str, start: str, end: str,
                sector: str, account_cd: str | None = None):
    params = {
        "financeCd": finance_cd,
        "listNo": list_no,
        "term": term,
        "startBaseMm": start,
        "endBaseMm": end,
    }
    if account_cd:
        params["accountCd"] = account_cd

    root = call("statisticsInfoSearch", params)

    # description 바인딩 (컬럼 의미 + 단위)
    desc = root.find("description")
    columns = {}
    unit = None
    if desc is not None:
        for col in desc.iterfind("column"):
            columns[col.findtext("column_id")] = col.findtext("column_nm")
        unit = desc.findtext("unit")

    data = {
        "query": params | {"sector": sector},
        "columns": columns,
        "unit": unit,
        "rows": rows(root),
    }

    out_dir = REPO_ROOT / sector / "raw" / f"{start}_{end}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{list_no}_{finance_cd}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"저장: {out_path}  (단위: {unit}, {len(data['rows'])}행)")
    print(f"컬럼 바인딩: {columns}")
    return data


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("catalog", help="메타 카탈로그 전수 수집")
    pc.add_argument("--sector", default="capital", choices=list(SECTORS))

    pf = sub.add_parser("fetch", help="통계 수치 조회")
    pf.add_argument("--finance-cd", required=True)
    pf.add_argument("--list-no", required=True)
    pf.add_argument("--account-cd", default=None)
    pf.add_argument("--term", default="Q", choices=["Y", "H", "Q"])
    pf.add_argument("--start", required=True, help="YYYYMM")
    pf.add_argument("--end", required=True, help="YYYYMM")
    pf.add_argument("--sector", default="capital", choices=list(SECTORS))

    a = p.parse_args()
    if a.cmd == "catalog":
        build_catalog(a.sector)
    else:
        fetch_stats(a.finance_cd, a.list_no, a.term, a.start, a.end, a.sector, a.account_cd)
