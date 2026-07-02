from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.importer.sample_files import SAMPLE_ROWS, write_org_template, write_sample_input_files


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SAMPLE_INPUT_DIR = Path(__file__).resolve().parents[1] / "sample_inputs"


def write_samples() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    write_sample_input_files(SAMPLE_INPUT_DIR)
    # 표준 2 시트 템플릿(명단·위계): 채워진 예시 + 빈 양식
    write_org_template(SAMPLE_INPUT_DIR / "조직도_표준템플릿.xlsx")
    write_org_template(SAMPLE_INPUT_DIR / "조직도_빈템플릿.xlsx", with_samples=False)
    base_rows = [dict(row) for row in SAMPLE_ROWS]
    pd.DataFrame(base_rows).to_excel(FIXTURE_DIR / "01_initial_hr.xlsx", index=False)

    updated_rows = [dict(row) for row in base_rows if row["사번"] != "OPS001"]
    for row in updated_rows:
        if row["사번"] == "ENG002":
            row["부서"] = "AI응용팀"
            row["직책"] = "Backend · AI Platform"
    updated_rows.append(
        {
            "사번": "ENG005",
            "이름": "신도하",
            "이메일": "doha.shin@example.com",
            "부서": "AI응용팀",
            "상위부서": "제품본부",
            "직급": "사원",
            "직책": "Junior AI Engineer",
            "입사일": "2026-06-01",
            "퇴사일": "",
            "재직상태": "재직",
            "근무지": "서울",
            "고용형태": "정규직",
            "매니저사번": "ENG004",
            "스킬": "Python, 검색, 평가",
            "비고": "반복 import 신규 입사자",
        }
    )
    pd.DataFrame(updated_rows).to_excel(FIXTURE_DIR / "02_changed_hr.xlsx", index=False)

    conflict_rows = [dict(row) for row in base_rows] + [
        {
            "사번": "",
            "이름": "정민서",
            "이메일": "minseo.contractor@example.com",
            "부서": "세일즈팀",
            "상위부서": "사업본부",
            "직급": "매니저",
            "직책": "Sales Advisor",
            "입사일": "2026-03-01",
            "퇴사일": "",
            "재직상태": "재직",
            "근무지": "서울",
            "고용형태": "외부자문",
            "매니저사번": "SALES001",
            "스킬": "세일즈 코칭",
            "비고": "이름만 같고 사번이 없는 충돌 검증용",
        }
    ]
    pd.DataFrame(conflict_rows).to_excel(FIXTURE_DIR / "03_conflict_hr.xlsx", index=False)


if __name__ == "__main__":
    write_samples()
