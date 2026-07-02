# 조직도 Studio

인사정보 파일을 로컬 SQLite 데이터베이스로 통합하고, 자동 조직도 GUI에서 발령/입사/퇴사/조직명 변경을 관리하는 Python 데스크톱 앱입니다.

## 비개발자용 실행 (더블클릭)

파이썬을 몰라도 됩니다. 폴더 안의 실행 파일을 더블클릭하세요.

- **Windows**: `실행_Windows.bat` 더블클릭
- **macOS**: `실행_Mac.command` 더블클릭
  - 처음 열 때 "확인되지 않은 개발자" 경고가 뜨면, 파일을 마우스 오른쪽 클릭 → **열기**를 한 번 선택하면 이후에는 바로 실행됩니다.

최초 실행 시 필요한 구성요소를 자동으로 설치하므로 수 분 걸릴 수 있고, 이후에는 바로 실행됩니다.
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
