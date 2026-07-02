from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.db.repository import HrRepository


def export_database_to_excel(session: Session, target_path: Path) -> None:
    repository = HrRepository(session)
    employees = repository.list_employees()
    assignments = repository.list_active_assignments()
    org_units = repository.list_org_units()
    assignment_by_employee = {assignment.employee_id: assignment for assignment in assignments}

    employee_rows = []
    for employee in employees:
        assignment = assignment_by_employee.get(employee.id)
        org = assignment.org_unit if assignment else None
        parent = org.parent if org and org.parent else None
        employee_rows.append(
            {
                "_org_chart_uuid": employee.id,
                "사번": employee.employee_no,
                "이름": employee.name,
                "이메일": employee.email,
                "부서": org.name if org else None,
                "상위부서": parent.name if parent else None,
                "직급": employee.grade,
                "직책": employee.title,
                "입사일": employee.hire_date,
                "퇴사일": employee.resign_date,
                "재직상태": employee.status,
            }
        )

    org_rows = [
        {
            "조직UUID": org.id,
            "조직명": org.name,
            "상위조직UUID": org.parent_id,
            "표시순서": org.display_order,
        }
        for org in org_units
    ]

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
        pd.DataFrame(employee_rows).to_excel(writer, sheet_name="인사DB", index=False)
        pd.DataFrame(org_rows).to_excel(writer, sheet_name="조직", index=False)

