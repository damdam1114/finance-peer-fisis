# finance-peer-fisis

금융감독원 금융통계정보시스템(FISIS) Open API에서 받은 **공개 통계**를 축적하는 리포.
KB캐피탈·KB저축은행 경영성과 프리뷰 작성 시 동종사 대비 위치를 확인하기 위한 참고 데이터셋.

> **이 리포에는 FISIS 공개 통계만 저장한다.**
> KB 내부 경영정보(프리뷰 원자료, CFO 지시사항, 상품별 수익성 등)는 절대 포함하지 않는다.
> **인증키·토큰 등 자격증명도 커밋하지 않는다** (환경변수로만 주입).

## 구조

```
finance-peer-fisis/
├── shared/
│   ├── fisis_api_spec.md      ← API 4종 메타 스펙·권역코드·제약사항
│   └── table_format.md        ← 표 양식 표준(두 섹터 공통)
├── tools/
│   └── fisis_collect.py       ← 메타 카탈로그 수집 + 수치 조회 파이프라인
├── capital/                   ← 여전업권(리스사K·할부금융사T·신기술N·카드C)
│   ├── raw/                    원본 API 응답 JSON — append-only
│   ├── processed/{수익성,건전성}/
│   └── schema/
│       ├── dataset_definition.md
│       ├── fisis_catalog.json  ← 자동생성(카탈로그 수집 시)
│       └── fisis_catalog.md    ← 자동생성 요약
└── savings-bank/              ← 상호저축은행(E)
    ├── raw/  processed/{수익성,건전성,자금조달}/  schema/
```

## 사용법

```bash
export FISIS_AUTH_KEY="발급받은인증키"     # 커밋 금지

# 1단계: 메타 카탈로그 전수 수집 (권역별 회사목록 + 통계표 + 계정항목)
python tools/fisis_collect.py catalog --sector capital
python tools/fisis_collect.py catalog --sector savings-bank

# 2단계: 카탈로그에서 확인한 코드로 실제 수치 조회
python tools/fisis_collect.py fetch \
    --finance-cd {회사코드} --list-no {통계코드} \
    --term Q --start 202303 --end 202606 --sector capital
```

카탈로그를 먼저 돌려야 하는 이유: `financeCd`·`listNo`·`accountCd`를 추측할 수 없고,
**여전업권이 4개 권역으로 분리**되어 있어 KB캐피탈과 경쟁사가 같은 권역에 있는지부터 확인해야 하기 때문.

## 커밋 규칙

- `raw/`는 append-only(과거본 보존, 수정 금지) — 감사 추적용
- `processed/`만 갱신
- 커밋 메시지: `data: {섹터} {기간} {카테고리} 갱신`

## 알려진 제약

| 제약 | 영향 |
|---|---|
| 월 단위 조회 불가(Y/H/Q만) | 26.4·26.5월 등 비분기말 시점은 FISIS로 커버 불가 |
| 검색기간 최대 40분기 | FY23~현재는 문제없음 |
| 일일 호출횟수 제한 | 카탈로그 전수 수집은 하루에 나눠 실행 권장 |
| 영리 목적 시 IP 고정 | 신청 IP 외에서 호출 시 err_cd 021 |

상세는 `shared/fisis_api_spec.md` 참조.
