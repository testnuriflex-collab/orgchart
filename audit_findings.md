# 조직도 Studio — 적대적 사용자 감사 결과 (UAG_FAIL)

- 감사 관점: 인사담당자(비개발자) A-to-Z 가혹 사용·공격
- 감사일: 2026-07-02
- 회귀 기준선: `ruff` 통과, `pytest 57 passed` (아래 결함은 모두 테스트 커버리지 밖에서 실제 재현됨)
- 검증 방식: 앱/repository/레이아웃/내보내기를 headless(offscreen)로 실제 실행하여 증거 확보. 코드는 수정하지 않음(심사 전용).
- 확정 결함: 총 11건 (치명 2 · 높음 2 · 중간 5 · 낮음 2)

---

## 치명 (Critical)

### C1. 비개발자 실행 관문 자체가 없음 — Windows 실행 불가
- **재현 조건**: 인사담당자가 Windows PC(또는 파이썬 미설치 환경)에서 앱을 켜려 함.
- **실제 증상(증거)**:
  - 저장소 전체에 `.bat`/`.command`/`.sh` 원클릭 런처가 0개(`find`로 확인).
  - `dist/` 산출물은 `Mach-O 64-bit executable arm64`(macOS Apple Silicon 전용) 하나뿐, Windows `.exe` 없음.
  - `README.md:5-14`는 `python -m venv`, `pip install -e ".[dev]"`, `python -m app.main` 등 개발자 명령만 제시. 파이썬 미설치 비개발자는 실행 경로 전무.
  - macOS arm64 바이너리조차 README 미언급·미서명(Gatekeeper 차단 예상)·Intel Mac 불가.
- **파일:라인**: `README.md:14`("Windows exe 패키징은 다음 단계에서 …spec 기반으로 진행합니다"), 런처 파일 부재.
- **수정 방향**: Windows용 서명된 원클릭 설치본(PyInstaller onefile + 인스톨러) + macOS `.app`(arm64/universal, 서명·공증) 배포. README에 "파이썬 없이 실행" 절 추가. 배포물 없이는 타겟 사용자의 실행 가능률 0%.

### C2. 동일 사번, 서로 다른 직원 → 조용한 덮어쓰기(데이터 유실)
- **재현 조건**: 하나의 엑셀에 `사번=E100` 두 행(예: 김철수/영업팀, 이영희/마케팅팀 — 서로 다른 사람이 같은 사번).
- **실제 증상(증거)**:
  - preview는 두 행 모두 "추가"로 표시한 뒤 적용.
  - 적용 후 DB 직원 = `['이영희']` 1명. 김철수 레코드가 경고 없이 소멸(데이터 유실).
  - 앱의 충돌 감지는 "동명이인(같은 이름)"에만 작동하고, 훨씬 위험한 사번 충돌은 `create_or_update_employee`가 `find_employee(employee_no=...)`로 기존 레코드를 찾아 그대로 덮어씀.
- **파일:라인**: `app/importer/excel_importer.py:110-148`(preview에 파일 내 사번 중복 미검출), `app/db/repository.py:97-118`(`create_or_update_employee` → 기존 레코드 덮어쓰기).
- **수정 방향**: preview 단계에서 파일 내 사번 중복을 CONFLICT로 승격. 서로 다른 이름이 동일 사번을 가지면 자동 병합을 차단하고 사용자에게 알림.

---

## 높음 (High)

### H1. 부서명 충돌 시 IntegrityError 미방어 — 일괄변환/조직명변경/조직 드래그 3경로
- **재현 조건**(실측 3케이스 모두 `UNIQUE constraint failed: org_units.name, org_units.parent_id` 발생):
  1. 일괄변환 "인사팀→피플팀"인데 같은 상위 조직에 이미 "피플팀"이 존재.
  2. 우측 패널 "조직명 저장"으로 형제 조직과 같은 이름을 입력.
  3. 조직 카드를 이미 동일명 자식이 있는 상위 조직으로 드래그(reparent).
- **실제 증상(증거)**:
  - 세 경로 모두 `session.commit()` 또는 `reparent`의 `flush()`가 IntegrityError를 던짐.
  - 해당 슬롯에 try/except가 없어 오류 안내 다이얼로그 없이 작업이 조용히 무반영되거나, PySide 예외 처리 설정에 따라 프로세스가 종료될 수 있음.
  - DB는 세션 종료 시 롤백되어 데이터 손상은 없으나, 사용자는 "왜 안 바뀌었는지" 알 수 없음.
  - 대조적으로 import/export/save_roster 경로는 try/except로 방어되어 있음(일관성 결여).
- **파일:라인**: `app/ui/main_window.py:610-615`(`bulk_convert`), `696-701`(`rename_org_unit`), `680-689`(`reparent_org_unit`) — 모두 try/except 부재. `app/db/repository.py:183`(reparent 내부 `flush()`), `models.py:57`(UniqueConstraint).
- **수정 방향**: 세 슬롯을 try/except로 감싸 "같은 상위에 동일 이름 조직이 있어 변경할 수 없습니다" 안내. 또는 rename/bulk_rename/reparent 실행 전 형제 이름 충돌을 사전 검증.

### H2. 500명 규모 원페이지 PDF/PNG 판독 불가 — 핵심 기능 실사용 실패
- **재현 조건**: 50팀 × 10명 = 500명(태스크가 명시한 규모) 조직도를 원페이지 PDF/PNG로 내보내기.
- **실제 증상(증거)**:
  - scene 콘텐츠 = 16233 × 979px (가로세로 비율 16.6:1).
  - A3 가로 KeepAspectRatio 원페이지 렌더 시 가로맞춤 스케일 1 scene-px = 0.0249mm.
  - → 카드폭 260px = 6.5mm, 이름 폰트 13px = **약 0.9pt**. "한 페이지에 다 들어간다"는 사실이나 글자가 물리적으로 판독 불가.
  - 핵심 산출물(원페이지 PDF)이 실사용 규모에서 무용지물.
- **파일:라인**: `app/exporter/pdf_exporter.py:35`(A3 고정), `:36-41`(가로/세로 자동), `:50`(단일 페이지 KeepAspectRatio). 배치가 넓게만 퍼지는 원인: `app/chart/layout.py`(수평 확장 배치).
- **수정 방향**: 콘텐츠가 임계 비율/크기를 초과하면 다중 페이지 타일링 또는 최소 가독 폰트 크기 보장, 세로 분할 레이아웃 옵션 제공.

---

## 중간 (Medium)

### M1. 재export 실패 조용한 삼킴 → DB/Excel 불일치 무경고
- **재현 조건**: Excel로 한 번 내보낸 뒤 그 파일을 Excel에서 연 채(파일 잠금) 표편집 저장/일괄변환/드래그 이동을 수행.
- **실제 증상(증거)**: `_reexport_excel_if_tracked`가 예외를 삼키고 `_last_excel_path=None`으로 리셋 → 이후 편집이 더는 재export되지 않음. 사용자는 내보낸 Excel이 최신이라 믿지만 조용히 낡은 상태로 방치됨.
- **파일:라인**: `app/ui/main_window.py:585-592`(`except Exception: self._last_excel_path = None`).
- **수정 방향**: 재export 실패 시 상태바/다이얼로그로 경고하고, 추적이 해제되었음을 사용자에게 통지.

### M2. 커밋된 작업 undo 불가
- **재현 조건**: 직원 드래그 이동 · 조직명 변경 · 부서 일괄변환을 실행한 뒤 되돌리려 함.
- **실제 증상(증거)**: undo 기능 없음(`grep undo|QUndo|되돌` 결과 "되돌리기"는 표편집의 DB 재로드 버튼뿐). `ChangeLog`에 before/after는 쌓이나 이를 되돌리는 경로가 없음. 이동에는 확인 다이얼로그가 있어 일부 완화되나, 일괄변환은 대량·비가역.
- **파일:라인**: `app/ui/main_window.py:267`("되돌리기" = `load_roster` 재로드), undo 스택 부재. 이력 적재는 `app/db/repository.py:276-292`(`log_change`)이나 소비 경로 없음.
- **수정 방향**: ChangeLog 기반 최소 1단계 undo, 또는 일괄변환 실행 전 스냅샷/확인 강화.

### M3. 표편집 컬럼 매핑 오류 — 2단계 조직에서 회사명이 '소속조직' 칸으로
- **재현 조건**: 표준 템플릿의 CEO 정민서(소속회사=(주)오르그스튜디오, 소속조직 공백, 소속부서=대표이사실)를 표편집 화면에서 로드.
- **실제 증상(증거)**: 로드 결과 `소속회사=''`, `소속조직='(주)오르그스튜디오'`, `소속부서='대표이사실'`. 회사명이 조직 칸으로 밀려 표시됨. 사용자가 이를 보고 비어 있는 소속회사를 채우면 허위 3단계 조직이 생성됨.
- **파일:라인**: `app/ui/main_window.py:513-515`(`company = path[0] if len(path)>=3`, `division = path[-2]`, `department = path[-1]`) — 위계 깊이가 아니라 경로 길이로 매핑해 2단계 경로에서 어긋남.
- **수정 방향**: 경로 길이별 company/division/department 매핑을 실제 위계 깊이 기준으로 정정.

### M4. 이름 누락 행 조용한 스킵
- **재현 조건**: 이름 셀이 공백인 행이 섞인 파일 import.
- **실제 증상(증거)**: 이름 공백 행 포함 2행 파일에서 `read_rows` 반환 1건(무명 행이 소리 없이 탈락). 사용자에게 몇 명이 누락됐는지 경고·카운트 없음.
- **파일:라인**: `app/importer/excel_importer.py:92-93`(`if not values["name"]: continue`).
- **수정 방향**: 스킵된 행 수를 preview/완료 메시지에 명시.

### M5. 발령 이력이 무의미한 sentinel 값
- **재현 조건**: 직원 이동(드래그/표편집) 후 발령 이력·기간을 조회하려 함.
- **실제 증상(증거)**: `move_employee`가 과거 배정 종료를 `end_date="변경"`이라는 문자열로 마킹하고, `start_date`는 항상 미기록. 활성 판정(`end_date is None`)에는 동작하나 실제 발령 날짜/기간 이력은 조회 불가(허구의 이력).
- **파일:라인**: `app/db/repository.py:139-140`(`assignment.end_date = "변경"`), 모델 `app/db/models.py:66-67`(`start_date`/`end_date`가 String, 미사용).
- **수정 방향**: 실제 날짜(ISO 8601)를 start_date/end_date에 기록.

---

## 낮음 (Low)

### L1. 초장문 부서명 카드 텍스트 잘림
- **재현 조건**: 매우 긴 부서명(수십 자) 조직.
- **실제 증상(증거)**: 카드폭이 고정 260px(`CARD_WIDTH`)이고 카드 높이도 고정이라 긴 이름이 말줄임(…) 없이 잘림. 레이아웃 산출 결과 org 카드 width는 항상 260 고정.
- **파일:라인**: `app/chart/layout.py:39`(`CARD_WIDTH = 260`), `app/ui/chart_view.py:263-267`(`setTextWidth(box.width - 32)` 고정, ellipsis 없음).
- **수정 방향**: 이름 길이에 따른 폰트 축소/말줄임 처리 또는 카드폭 가변화.

### L2. `subtree_width` O(n²) 재귀 재계산
- **재현 조건**: 극단적으로 깊은 조직 체인.
- **실제 증상(증거)**: 노드마다 하위 전체를 재귀로 재계산 → 체인 200단계 7.7ms, 600단계 70ms(3배 노드에 9배 시간, O(n²) 확인). 실사용 조직 규모(수십~수백 노드)에서는 무해하나 비효율.
- **파일:라인**: `app/chart/layout.py:130-135`(`subtree_width` 메모이제이션 없음), 호출부 `:145`, `:252`, `:259`, `:286`.
- **수정 방향**: `subtree_width` 결과를 노드 id 기준으로 메모이제이션.

---

## 검증 아티팩트
- 재현 스크립트(임시, 심사용): `/private/tmp/claude-501/repro1.py` ~ `repro5.py`
  - repro1: H1 3경로 IntegrityError 재현
  - repro2: 재import 멱등성(정상), 표편집 컬럼 매핑(M3), 위계 빈 시트/빈 행 처리
  - repro3: 레이아웃 성능(L2)
  - repro4: 500명 PDF/PNG 실렌더 스케일(H2), 전필드 OFF, 초장문(L1)
  - repro5: 동일 사번 데이터 유실(C2), 이름 누락 스킵(M4), undo 부재(M2)
