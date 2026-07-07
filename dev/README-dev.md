# 조직도 Studio — 개발자용 문서 (dev)

> 최종 사용자(구매자)용 실행 안내는 저장소 최상위 `README.md`와
> `Output/` 폴더를 참고하세요. 이 문서는 소스 코드로 직접 실행·개발·
> 재패키징하려는 개발자를 위한 것입니다.

인사정보 파일을 로컬 SQLite 데이터베이스로 통합하고, 자동 조직도 GUI에서 발령/입사/퇴사/조직명 변경을 관리하는 Python 데스크톱 앱입니다.

## Python 설치 없이 실행 (권장 — 완전 독립 실행파일)

최상위 디렉터리의 `OrgChartStudio.app` (macOS) 또는
`START-Windows/OrgChartStudio.exe` (Windows)를
더블클릭하면 됩니다. Python·pip·가상환경 설치가 전혀 필요 없습니다.
빌드 방법은 이 폴더의 `packaging/org-chart-studio.spec`을 참고하세요.

## Python 소스 직접 실행 (개발자·구버전 대안, 더블클릭)

Python이 설치돼 있다면 아래 런처로 소스에서 바로 실행할 수 있습니다(최초 실행 시
가상환경을 자동 구성하므로 수 분 걸릴 수 있습니다).

- **Windows**: `run_windows.bat` 더블클릭
- **macOS**: `run_mac.command` 더블클릭
  - 처음 열 때 "확인되지 않은 개발자" 경고가 뜨면, 파일을 마우스 오른쪽 클릭 → **열기**를 한 번 선택하면 이후에는 바로 실행됩니다.

폴더를 통째로 다른 위치로 옮겨도 그대로 동작합니다.

### 파이썬이 설치되어 있지 않다면

실행 파일이 안내 메시지와 함께 설치 방법을 알려 줍니다. 아래에서 Python 3.12 이상을 먼저 설치하세요.

- 공식 다운로드: <https://www.python.org/downloads/>
- Windows 설치 시 첫 화면의 **"Add python.exe to PATH"** 를 반드시 체크하세요.

설치가 끝나면 다시 실행 파일을 더블클릭하면 됩니다.

## 실행 (개발자용)

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m app.main
```

## 입력 파일

지원 형식:

- Excel: `.xlsx`, `.xlsm`, `.xls`
- CSV: `.csv`
- JSON: `.json`

JSON은 `[{...}, {...}]` 배열 또는 `{"employees": [...]}` 형태를 지원합니다.

현실적인 다층 조직 예시는 `sample_inputs/`에 Excel, CSV, JSON 형식으로 포함되어 있습니다.
앱은 표준 양식 파일이면 컬럼 매핑이나 미리보기 확인 없이 자동으로 DB와 조직도를 갱신합니다.
동명이인처럼 자동 병합하면 위험한 충돌만 별도 화면으로 알려줍니다.

## 표준 조직도 템플릿 (명단 + 위계)

가장 빠르게 조직도를 그리는 방법은 앱이 제공하는 표준 2시트 엑셀 템플릿을 쓰는 것입니다.

- **명단 시트**: `소속회사 | 소속조직 | 소속부서 | 이름 | 직책`(+ 직급·사번·이메일·재직상태·입사일·퇴사일). `재직상태`는 재직/휴직/퇴사 드롭다운으로 입력합니다.
- **위계 시트**: `구분 | 이름 | 상위 | 표시순서`. 회사 → 조직 → 부서의 상하관계와 화면 표시 순서를 정합니다. `구분`은 회사/조직/부서 드롭다운입니다.

템플릿은 헤더 서식·틀고정·드롭다운 데이터 유효성이 미리 적용되어 있어, 열자마자 값만 채워 넣으면 됩니다. 파일을 열면 이 두 시트를 자동 인식해 회사→조직→부서→인원 트리로 조직도를 렌더링합니다.

## 주요 기능

- **조직도 자동 렌더링**: 위계 기준으로 카드형 노드를 자동 배치.
- **드래그 소속 이동**: 부서/조직/인원 카드를 끌어 상위 소속을 변경하고 데이터에 반영.
- **표시 토글**: 좌측 트리 체크박스로 회사/조직/부서/개별 인원의 표시를 켜고 끔.
- **엑셀 편집 모드**: 표 화면에서 명단을 직접 수정하고, 부서명 찾아바꾸기(일괄변환) 후 엑셀로 저장.
- **내보내기**: 현재 조직도를 원페이지 PDF 또는 PNG로 저장(대규모는 자동 다중 페이지 타일링).

## 기본 컬럼

앱은 아래 컬럼명을 자동 인식합니다. 다른 이름을 쓰는 파일은 import 화면에서 매핑을 바꿀 수 있도록 설계되어 있습니다.

| 의미 | 기본 컬럼명 |
| --- | --- |
| 사번 | 사번 |
| 이름 | 이름 |
| 이메일 | 이메일 |
| 부서 | 부서 |
| 상위부서 | 상위부서 |
| 직급 | 직급 |
| 직책 | 직책 |
| 입사일 | 입사일 |
| 퇴사일 | 퇴사일 |
| 재직상태 | 재직상태 |

## 폴더 구조

- `app/main.py`: 앱 시작점
- `app/ui`: PySide6 GUI
- `app/chart`: 조직도 레이아웃/그래픽 카드
- `app/domain`: 앱 내부 DTO와 enum
- `app/db`: SQLite/SQLAlchemy 모델과 저장소
- `app/importer`: Excel import/diff/merge
- `app/exporter`: PDF/Excel export
- `resources`: 폰트, 스타일, 디자인 토큰
- `tests`: 핵심 데이터/레이아웃 테스트
- `packaging`: PyInstaller `.spec`, Windows 버전 리소스(`version_info.txt`)
- `.github/workflows`(저장소 루트): Windows exe 자동 빌드 CI

## 독립 실행파일 패키징 (Python 미설치 환경 배포용)

macOS와 Windows 모두 PyInstaller 6.x를 사용한다. PyInstaller는 빌드를 실행한 OS와
같은 OS용 실행파일만 만들 수 있어(크로스 컴파일 불가), macOS 로컬 빌드와 Windows
CI 빌드를 분리했다.

### macOS (로컬에서 직접 빌드)

```bash
cd "dev"
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m PyInstaller packaging/org-chart-studio.spec --noconfirm --clean
```

결과: `dist/OrgChartStudio.app` (더블클릭 실행되는 macOS 앱 번들, 아이콘·버전
메타데이터 포함)과 `dist/START-Windows/`(Windows 폴더 배포판) 두 가지가 생성된다.
빌드 후 `open dist/OrgChartStudio.app`으로 실제 기동을 확인한다.

### Windows (GitHub Actions로 자동 빌드)

저장소 루트의 `.github/workflows/build-windows.yml`이 push 시 `windows-latest`
러너에서 동일한 `.spec`으로 exe를 빌드하고, pytest 전체 실행과 실행파일 스모크
기동(`ORG_CHART_STUDIO_SMOKE=1`) 검증까지 자동으로 수행한 뒤 Actions Artifacts에
`OrgChartStudio-windows`로 업로드한다. 로컬에 Windows 머신이 있다면 위 macOS
명령의 `python -m PyInstaller ...` 줄만 PowerShell에서 그대로 실행해도 된다
(`source .venv/bin/activate` 대신 `.venv\Scripts\activate`).

### 리소스 경로 계약

`app/config.py::project_root()`가 `sys._MEIPASS`(PyInstaller 런타임 번들 경로)를
우선 사용하도록 이미 구현되어 있어, 소스 실행과 번들 실행 모두에서
`resources/`, `alembic.ini`, `app/db/migrations`가 동일한 상대 경로로 해석된다.
새 리소스 파일을 추가할 때는 `packaging/org-chart-studio.spec`의 `datas=[...]`에도
함께 등록해야 번들에 포함된다.
