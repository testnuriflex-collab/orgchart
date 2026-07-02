# 조직도 Studio 디자인 시스템

인사 업무용 데스크톱 도구를 위한 단일 라이트 테마 디자인 시스템. 토큰 원본은
`app/ui/styles.py`의 `TOKENS`이며, 이 문서는 그 요약이다.

## 색 토큰

표면
- `appBg`: `#EDEFF3` (최하단 배경 — 패널이 카드처럼 떠 보이게)
- `panel`: `#FFFFFF`
- `panelSoft`: `#F6F8FA`
- `canvas`: `#F1F3F6` (조직도 캔버스)

잉크(텍스트)
- `ink`: `#1B1F27` / `body`: `#3D434F` / `muted`: `#6B7280` / `subtle`: `#9AA1AC`

라인
- `hairline`: `#E4E7EC` / `hairlineStrong`: `#D3D8DF`

브랜드 액센트(단일 액센트 — 프로페셔널 블루, WCAG AA)
- `accent`: `#1D4ED8` / `accentHover`: `#2563EB` / `accentActive`: `#1B44B8` / `accentSoft`: `#E7EEFD`

상태
- `success`(재직 등 긍정 상태, 블루 통일): `#1D4ED8` / `warning`: `#B26A00` / `danger`: `#C0392B`

조직도 레벨 색
- 회사(root): 딥 네이비 `#12294A` / 본부(division): 블루 `#1D4ED8` / 팀(team): 슬레이트 `#64748B`

## 타이포그래피

`Paperlogy`를 우선 사용하고 `Apple SD Gothic Neo`, `Malgun Gothic`, 플랫폼 sans-serif로
폴백한다. 스케일: 앱 타이틀 15/700, 본문 13, 캡션 11.

## 간격·형태

- 8px 간격 그리드. 패널 패딩 16, 요소 간격 8~14.
- 라운드: `rSm` 8 / `rMd` 12 / `rLg` 16.
- 카드 미세 드롭섀도: blur 11~22, y-offset 2~5, `rgba(17,22,33,0.18)`.

## 레이아웃

- 상단 앱 헤더바: 좌측 아이덴티티(액센트 점 + "조직도 Studio"), 우측 그룹화된
  아이콘 툴바(파일 · 편집 · 내보내기 · 보기, 그룹 사이 구분선). 라벨은 툴팁으로.
- 좌측: 검색 + 조직 목록 패널 카드.
- 중앙: 조직도 캔버스 ⇄ 명단 표 편집(스택 전환).
- 우측: 표시 항목 토글 + 속성 폼(라벨-값) + 조직명 편집 그룹.

## 컴포넌트

- 아이콘: `qtawesome`(Font Awesome 5 solid) 단일 세트. 미설치 시 Qt 표준 아이콘 폴백.
- 조직 카드 레벨 색: 회사=딥 네이비, 본부=블루 바, 팀=슬레이트 바.
- 조직도 인터랙션: 마우스 휠(보조키 불필요)로 커서 기준 줌(0.1x~3x), 빈 공간 드래그로 패닝.
  첫 화면은 가독 배율로 카드 틈에 맞춰 정렬(잘린 카드 0).
- 입력: 흰 채움, hairlineStrong 1px, 포커스 시 액센트 1.5px.
- 리스트/표: hover=panelSoft, 선택=accentSoft + accent 텍스트.
