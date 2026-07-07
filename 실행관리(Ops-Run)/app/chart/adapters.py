from __future__ import annotations

from app.chart.layout import EmployeeNode, OrgNode
from app.db.models import Assignment, OrgUnit


def to_layout_nodes(org_units: list[OrgUnit], assignments: list[Assignment]) -> list[OrgNode]:
    employees_by_org: dict[str, list[EmployeeNode]] = {org.id: [] for org in org_units}
    for assignment in assignments:
        employee = assignment.employee
        employees_by_org.setdefault(assignment.org_unit_id, []).append(
            EmployeeNode(
                id=employee.id,
                name=employee.name,
                grade=employee.grade,
                title=employee.title,
                status=employee.status,
                employee_no=employee.employee_no,
                email=employee.email,
            )
        )
    return [
        OrgNode(
            id=org.id,
            name=org.name,
            parent_id=org.parent_id,
            display_order=org.display_order,
            employees=tuple(employees_by_org.get(org.id, [])),
        )
        for org in org_units
    ]
