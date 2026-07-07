# macOS 실행파일 (구 위치)

**참고**: 실행파일은 최상위 디렉터리(`../../start_mac/OrgChartStudio.app`)로 이동되었습니다.

`../../start_mac/OrgChartStudio.app`을 더블클릭하면 실행됩니다(Python 설치 불필요).

재빌드가 필요하면:
```bash
cd "../../dev"
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m PyInstaller packaging/org-chart-studio.spec --noconfirm --clean
cp -R dist/OrgChartStudio.app "../../start_mac/OrgChartStudio.app"
```
