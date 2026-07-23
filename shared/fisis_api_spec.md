# FISIS Open API 메타 스펙

출처: https://fisis.fss.or.kr/page/api-spec.jsp (2026.07 확인)

## 1. 4종 API 요약

| API | 엔드포인트 | 용도 | 필수 파라미터 |
|---|---|---|---|
| 통계정보 | `statisticsInfoSearch.{xml\|json\|xls}` | **실제 수치 조회** | auth, financeCd, listNo, lang, term, startBaseMm, endBaseMm |
| 금융회사 | `companySearch.{xml\|json\|xls}` | financeCd 확보 | auth, partDiv, lang |
| 통계목록 | `statisticsListSearch.{xml\|json\|xls}` | listNo 확보 | auth, lrgDiv, lang |
| 계정항목 | `accountListSearch.{xml\|json\|xls}` | accountCd 확보 | auth, listNo, lang |

Base URL: `http://fisis.fss.or.kr/openapi/`

**수집 순서 (의존관계)**
```
statisticsListSearch (lrgDiv) → listNo
        ↓
accountListSearch (listNo) → accountCd
        ↓
companySearch (partDiv) → financeCd
        ↓
statisticsInfoSearch (financeCd + listNo + accountCd + 기간) → 실제 수치
```

## 2. 금융권역 코드표 (companySearch의 partDiv)

| 명칭 | 코드 | 명칭 | 코드 |
|---|---|---|---|
| 국내은행 | A | 외은지점 | J |
| 생명보험 | H | 손해보험 | I |
| 투자매매중개업자Ⅰ | F | 투자매매중개업자Ⅱ | W |
| 집합투자업자 | G | 투자자문일임업자 | X |
| 종합금융회사 | D | **신용카드사** | **C** |
| **리스사** | **K** | **할부금융사** | **T** |
| **신기술금융사** | **N** | **상호저축은행** | **E** |
| 신용협동조합 | O | 농업협동조합 | Q |
| 수산업협동조합 | P | 산림조합 | S |
| 부동산신탁 | M | 금융지주회사 | L |
| 공통(신탁) | B | 공통(파생상품) | R |

**중요 — 여전업권은 단일 권역이 아님**
KB캐피탈이 속한 여신전문금융업은 FISIS에서 **리스사(K) / 할부금융사(T) / 신기술금융사(N) / 신용카드사(C)** 로 분리되어 있음.
KB캐피탈은 등록 업종에 따라 K 또는 T에 속할 것으로 예상되나 **실제 companySearch 호출로 확인 필요**.
→ 경쟁사 비교 시 권역이 갈리면 동일 통계표(listNo)를 쓸 수 없으므로, **먼저 K·T·N 전수 조회로 비교대상 회사가 어느 권역에 있는지 확정**해야 함.

## 3. 통계표 분류 코드 (statisticsListSearch의 lrgDiv + smlDiv)

여전업권·저축은행 관련 권역만 발췌:

| 권역 | lrgDiv | 일반현황 | 재무현황 | 주요경영지표 | 주요영업활동 | 보도자료통계 |
|---|---|---|---|---|---|---|
| 신용카드사 | C | A | B | C | D | P |
| 리스사 | K | A | B | C | D | P |
| 할부금융사 | T | A | B | C | D | P |
| 신기술금융사 | N | A | B | C | D | P |
| 상호저축은행 | E | A | B | C | — | P |
| 금융지주회사 | L | A | B | C | — | P |

**프리뷰 활용 매핑(예상)**
- 수익성(ROA·ROE·NIM) → `smlDiv=C` (주요경영지표)
- 건전성(NPL·연체율·충당금) → `smlDiv=C` 또는 `smlDiv=B` (재무현황)
- 자산·부채 규모 → `smlDiv=B` (재무현황)
- 영업 실적(취급액 등) → `smlDiv=D` (주요영업활동)
→ 실제 list_nm을 받아본 뒤 확정.

## 4. 통계정보 API 응답 구조

```xml
<result>
  <err_cd>000</err_cd>
  <err_msg>정상</err_msg>
  <total_count>1</total_count>
  <description>
    <column><column_id>a</column_id><column_nm>임직원수</column_nm></column>
    <date_of_settlement>12/31</date_of_settlement>
    <unit>명</unit>              ← 단위 정보가 여기 있음. 십억원 환산 시 필수 확인
  </description>
  <list>
    <row>
      <base_month>201306</base_month>
      <finance_cd>0010927</finance_cd>
      <finance_nm>국민은행</finance_nm>
      <account_cd>A11</account_cd>
      <account_nm>상임임원</account_nm>
      <a>46</a>                   ← 컬럼값. column_id와 매칭(a,b,c,d)
    </row>
  </list>
</result>
```

**바인딩 규칙**
- `description/column`의 `column_id`↔`column_nm` 매핑으로 `<a>`,`<b>`,`<c>`,`<d>` 값의 의미를 해석
- `description/unit`을 반드시 읽어서 십억원 환산 계수 결정(억원이면 ÷10, 백만원이면 ÷1000 등)
- `account_cd`/`account_nm`으로 행 라벨 구성

## 5. 호출 제약

| 항목 | 제약 |
|---|---|
| 검색 기간 | **최대 40분기** (초과 시 err_cd 103) |
| term | Y(연도) / H(반기) / Q(분기) — **월(M) 없음** |
| 인증키 | 32자리 |
| 일일 호출 | 비영리는 일일 허용횟수 제한(초과 시 err_cd 020) |
| IP 제한 | 영리 목적은 신청 IP 외 호출 차단(err_cd 021) |
| 언어 | kr / en 만 허용 |

**프리뷰 표준 표양식과의 충돌 주의**
프로젝트 표준 시계열은 `FY23·FY24·FY25·25.6월·26년 최신월`인데, FISIS는 **월 단위 조회 불가(Q가 최소 단위)**.
→ 25.6월 = 2025 2분기(202506), 26년 최신월은 분기말(202603 또는 202606)로만 대응 가능.
→ 26.4월·26.5월 같은 비분기말 시점은 FISIS로 커버 불가 → 내부 자료로만 보완. 표에 각주 필수.

## 6. 에러 코드

| 코드 | 의미 |
|---|---|
| 000 | 정상 |
| 010/011/012/013 | 미등록/중지/삭제/샘플 인증키 |
| 020 | 일일 허용횟수 초과 |
| 021 | 허용 IP 아님 |
| 022 | 허용 언어 아님 |
| 100 | 요청변수 누락 |
| 101 | 부적절한 요청변수값 |
| 102 | 시작일 > 종료일 |
| 103 | 검색기간 40분기 초과 |
| 900 | 내부 시스템 에러 |

**주의**: `err_cd=000` + `total_count=0`은 에러가 아니라 **해당 조건에 데이터 없음**을 의미.
(실제 사례: partDiv=A + financeCd=0010250 → 000/0건. 권역 불일치로 추정)
