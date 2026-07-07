# macOS 실행파일

`OrgChartStudio.app`을 더블클릭하면 실행됩니다(Python 설치 불필요).

앱 바이너리 자체는 용량이 커서(약 150MB) git 저장소에는 포함하지 않았습니다
(`.gitignore` 참고). 다시 만들려면:

```bash
cd "../../실행관리(Ops-Run)"
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m PyInstaller packaging/org-chart-studio.spec --noconfirm --clean
cp -R dist/OrgChartStudio.app "../결과물(Output)/mac/OrgChartStudio.app"
```
