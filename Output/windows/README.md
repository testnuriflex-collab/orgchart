# Windows 실행파일 안내

이 폴더는 Windows용 `OrgChartStudio.exe` 배포 산출물이 채워지는 자리입니다.

## 왜 여기서 바로 빌드하지 않았나

PyInstaller는 빌드를 실행하는 OS와 같은 OS의 실행파일만 만들 수 있습니다(크로스 컴파일 불가).
이 프로젝트는 macOS에서 작업되었기 때문에, Windows용 `.exe`는 실제 Windows 환경에서
빌드해야 합니다.

## 자동 빌드 방법 (준비 완료)

저장소 루트의 `.github/workflows/build-windows.yml` 워크플로우가 GitHub의 실제
Windows 가상머신(windows-latest)에서 자동으로 빌드하도록 이미 구성되어 있습니다.

1. 이 저장소를 GitHub에 push 합니다(이미 push 권한이 있는 계정 사용).
2. GitHub 저장소의 **Actions** 탭 → **Windows 실행파일 빌드 (build-windows)** 워크플로우가
   push 시 자동 실행됩니다(수동 실행도 가능: `workflow_dispatch`).
3. 빌드가 끝나면 Actions 실행 결과 페이지의 **Artifacts** 섹션에서
   `OrgChartStudio-windows` 를 내려받습니다.
4. 압축을 풀면 `OrgChartStudio/` 폴더 안에 `OrgChartStudio.exe`가 있습니다.
   이 폴더째로 이 `windows/` 디렉터리에 넣으면 배포 준비가 끝납니다.

빌드 파이프라인은 매번: 전체 pytest 실행 → PyInstaller 빌드 → 실행파일 스모크
기동 확인(`ORG_CHART_STUDIO_SMOKE=1`) → 아티팩트 업로드 순서로 자동 검증합니다.

## 로컬에 실제 Windows PC가 있다면

```powershell
cd "dev"
python -m pip install -e ".[dev]"
python -m PyInstaller packaging\org-chart-studio.spec --noconfirm --clean
xcopy /E /I dist\OrgChartStudio "..\..\OrgChartStudio"
```

`dev\dist\OrgChartStudio\OrgChartStudio.exe` 가 생성되고, 최상위 `OrgChartStudio/` 폴더에 복사됩니다.
