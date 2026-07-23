# finance-peer-fisis

금융감독원 금융통계정보시스템(FISIS) Open API에서 받은 **공개 통계**를 축적하는 리포.
KB캐피탈·KB저축은행 경영성과 프리뷰 작성 시 동종사 대비 위치를 확인하기 위한 참고 데이터셋.

**이 리포에는 FISIS 공개 통계만 저장한다. KB 내부 경영정보(프리뷰 원자료, CFO 지시사항 등)는 절대 포함하지 않는다.**

## 구조

```
finance-peer-fisis/
├── capital/            ← 여전업권(캐피탈사) 데이터
│   ├── raw/             원본 API 응답(JSON/XML) 보관 — append-only
│   ├── processed/        표준 표 양식(FY23~26최신월+Gap)으로 가공된 CSV
│   │   ├── 수익성/
│   │   └── 건전성/
│   └── schema/
│       └── dataset_definition.md   ← 비교대상 회사·계정항목 정의
├── savings-bank/        ← 저축은행권 데이터
│   ├── raw/
│   ├── processed/
│   │   ├── 수익성/
│   │   ├── 건전성/
│   │   └── 자금조달/
│   └── schema/
│       └── dataset_definition.md
└── shared/
    └── table_format.md   ← 「표양식_표준.md」 규칙 (두 섹터 공통)
```

## 사용 흐름

1. FISIS 인증키로 필요 통계표 조회 (분기/월 단위)
2. `raw/{연도분기}/` 밑에 원본 그대로 커밋 (감사 추적용, 수정 안 함)
3. `processed/{카테고리}/` 밑에 표준 표 양식으로 가공한 CSV 갱신
4. 커밋 메시지: `data: {섹터} {연도분기} {카테고리} 갱신`
