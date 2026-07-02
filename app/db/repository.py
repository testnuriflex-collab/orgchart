from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Assignment, ChangeLog, Employee, EmploymentEvent, OrgUnit
from app.domain.hr import (
    EmployeeInput,
    EmploymentStatus,
    HierarchySpec,
    ImportAction,
    ImportPreview,
    normalize_employment_status,
)

class OrgUnitNameConflictError(Exception):
    """같은 상위 조직 아래에 이미 동일 이름 조직이 있어 변경/이동할 수 없을 때."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"같은 상위 조직에 '{name}' 이름이 이미 있어 변경할 수 없습니다.")


def _today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


EMPLOYEE_EDITABLE_FIELDS = {
    "employee_no": "사번",
    "name": "이름",
    "email": "이메일",
    "grade": "직급",
    "title": "직책",
    "status": "재직상태",
    "hire_date": "입사일",
    "resign_date": "퇴사일",
}


class HrRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_org_units(self) -> list[OrgUnit]:
        return list(
            self.session.scalars(
                select(OrgUnit).order_by(OrgUnit.parent_id.isnot(None), OrgUnit.display_order, OrgUnit.name)
            )
        )

    def list_employees(self) -> list[Employee]:
        return list(self.session.scalars(select(Employee).order_by(Employee.status, Employee.name)))

    def list_active_assignments(self) -> list[Assignment]:
        stmt: Select[tuple[Assignment]] = (
            select(Assignment)
            .options(joinedload(Assignment.employee), joinedload(Assignment.org_unit))
            .where(Assignment.end_date.is_(None))
        )
        return list(self.session.scalars(stmt))

    def find_employee(
        self, *, employee_no: str | None = None, email: str | None = None, source_uuid: str | None = None
    ) -> Employee | None:
        if source_uuid:
            employee = self.session.get(Employee, source_uuid)
            if employee:
                return employee
        if employee_no:
            employee = self.session.scalar(select(Employee).where(Employee.employee_no == employee_no))
            if employee:
                return employee
        if email:
            return self.session.scalar(select(Employee).where(Employee.email == email))
        return None

    def _ensure_child(self, name: str, parent: OrgUnit | None) -> OrgUnit:
        clean_name = (name or "미지정").strip() or "미지정"
        org = self.session.scalar(
            select(OrgUnit).where(OrgUnit.name == clean_name, OrgUnit.parent_id == (parent.id if parent else None))
        )
        if org:
            return org
        org = OrgUnit(name=clean_name, parent_id=parent.id if parent else None)
        self.session.add(org)
        self.session.flush()
        self.log_change("org_unit", org.id, "create", None, {"name": org.name, "parent_id": org.parent_id})
        return org

    def ensure_org_unit(self, name: str | None, parent_name: str | None = None) -> OrgUnit:
        parent = self.ensure_org_unit(parent_name) if parent_name else None
        return self._ensure_child(name or "미지정", parent)

    def ensure_org_path(self, names: list[str]) -> OrgUnit:
        """상위→하위 이름 목록으로 중첩 조직 경로를 만들고 말단 조직을 반환한다."""
        parent: OrgUnit | None = None
        leaf: OrgUnit | None = None
        for name in names:
            clean = (name or "").strip()
            if not clean:
                continue
            leaf = self._ensure_child(clean, parent)
            parent = leaf
        return leaf if leaf is not None else self._ensure_child("미지정", None)

    def create_or_update_employee(self, employee_input: EmployeeInput) -> Employee:
        employee = self.find_employee(
            employee_no=employee_input.employee_no,
            email=employee_input.email,
            source_uuid=employee_input.source_uuid,
        )
        before = _employee_dict(employee) if employee else None
        if employee is None:
            employee = Employee(
                id=employee_input.source_uuid or None,
                employee_no=employee_input.employee_no,
                name=employee_input.name,
            )
            self.session.add(employee)

        employee.name = employee_input.name
        employee.employee_no = employee_input.employee_no
        employee.email = employee_input.email
        employee.grade = employee_input.grade
        employee.title = employee_input.title
        employee.hire_date = employee_input.hire_date
        employee.resign_date = employee_input.resign_date
        employee.status = normalize_employment_status(employee_input.status, employee_input.resign_date)
        self.session.flush()

        org_unit = self.ensure_org_path(employee_input.org_path_names())
        self.move_employee(employee.id, org_unit.id, actor_action="assign")
        self.log_change("employee", employee.id, "upsert", before, _employee_dict(employee))
        return employee

    def move_employee(self, employee_id: str, org_unit_id: str, actor_action: str = "move") -> None:
        active_assignments = list(
            self.session.scalars(
                select(Assignment).where(
                    Assignment.employee_id == employee_id,
                    Assignment.end_date.is_(None),
                )
            )
        )
        if active_assignments and active_assignments[0].org_unit_id == org_unit_id:
            return
        before = [{"id": item.id, "org_unit_id": item.org_unit_id} for item in active_assignments]
        today = _today_iso()
        for assignment in active_assignments:
            # 과거 배정을 실제 종료일로 마감한다(무의미한 '변경' sentinel 대신 ISO 날짜).
            assignment.end_date = today
        assignment = Assignment(
            employee_id=employee_id, org_unit_id=org_unit_id, start_date=today
        )
        self.session.add(assignment)
        self.session.add(
            EmploymentEvent(
                employee_id=employee_id,
                event_type=actor_action,
                payload=json.dumps({"org_unit_id": org_unit_id}, ensure_ascii=False),
            )
        )
        self.log_change("assignment", employee_id, actor_action, before, {"org_unit_id": org_unit_id})

    def _assert_no_sibling_conflict(
        self, name: str, parent_id: str | None, exclude_id: str | None = None
    ) -> None:
        """같은 상위 조직 아래에 동일 이름 조직이 이미 있으면 예외를 던진다."""
        existing = self.session.scalar(
            select(OrgUnit).where(OrgUnit.name == name, OrgUnit.parent_id == parent_id)
        )
        if existing is not None and existing.id != exclude_id:
            raise OrgUnitNameConflictError(name)

    def rename_org_unit(self, org_unit_id: str, new_name: str) -> None:
        org_unit = self.session.get(OrgUnit, org_unit_id)
        if not org_unit:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_unit_id}")
        clean_name = new_name.strip()
        if not clean_name or clean_name == org_unit.name:
            return
        self._assert_no_sibling_conflict(clean_name, org_unit.parent_id, exclude_id=org_unit.id)
        before = {"name": org_unit.name}
        org_unit.name = clean_name
        self.log_change("org_unit", org_unit.id, "rename", before, {"name": org_unit.name})

    def _is_descendant(self, candidate_id: str, ancestor_id: str) -> bool:
        """candidate_id가 ancestor_id의 자손인지(자기 자신 포함) 확인한다."""
        current = self.session.get(OrgUnit, candidate_id)
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            if current.id == ancestor_id:
                return True
            seen.add(current.id)
            current = self.session.get(OrgUnit, current.parent_id) if current.parent_id else None
        return False

    def reparent_org_unit(self, org_unit_id: str, new_parent_id: str | None) -> bool:
        """조직을 다른 상위 조직 아래로 이동한다. 순환이 생기면 거부한다."""
        org_unit = self.session.get(OrgUnit, org_unit_id)
        if not org_unit:
            raise ValueError(f"조직을 찾을 수 없습니다: {org_unit_id}")
        if new_parent_id == org_unit_id:
            return False
        if new_parent_id and self._is_descendant(new_parent_id, org_unit_id):
            return False
        if org_unit.parent_id == new_parent_id:
            return False
        # 옮겨갈 상위 아래에 같은 이름 조직이 있으면 UNIQUE 제약 위반이 나므로 사전 차단.
        self._assert_no_sibling_conflict(org_unit.name, new_parent_id, exclude_id=org_unit.id)
        before = {"parent_id": org_unit.parent_id}
        org_unit.parent_id = new_parent_id
        self.session.flush()
        self.log_change("org_unit", org_unit.id, "reparent", before, {"parent_id": new_parent_id})
        return True

    def bulk_rename_org_units(
        self, mapping: dict[str, str]
    ) -> tuple[int, list[str], list[tuple[str, str]]]:
        """이름 기준 일괄 치환(예: '인사팀' → '피플팀').

        같은 상위 조직에 이미 새 이름 조직이 있어 UNIQUE 제약을 위반하는 항목은
        건너뛴다. 반환값은 (변경 수, 건너뛴 새 이름 목록, 되돌리기용 (조직id, 이전이름) 목록).
        """
        changed = 0
        conflicts: list[str] = []
        reverts: list[tuple[str, str]] = []
        for old_name, new_name in mapping.items():
            clean_old = (old_name or "").strip()
            clean_new = (new_name or "").strip()
            if not clean_old or not clean_new or clean_old == clean_new:
                continue
            targets = list(self.session.scalars(select(OrgUnit).where(OrgUnit.name == clean_old)))
            for org_unit in targets:
                sibling = self.session.scalar(
                    select(OrgUnit).where(
                        OrgUnit.name == clean_new, OrgUnit.parent_id == org_unit.parent_id
                    )
                )
                if sibling is not None and sibling.id != org_unit.id:
                    conflicts.append(clean_new)
                    continue
                before = {"name": org_unit.name}
                reverts.append((org_unit.id, org_unit.name))
                org_unit.name = clean_new
                self.log_change("org_unit", org_unit.id, "bulk_rename", before, {"name": clean_new})
                changed += 1
        if changed:
            self.session.flush()
        return changed, conflicts, reverts

    def update_employee_fields(self, employee_id: str, fields: dict[str, str | None]) -> bool:
        """표 편집 화면에서 넘어온 직원 필드를 갱신한다."""
        employee = self.session.get(Employee, employee_id)
        if not employee:
            return False
        before = _employee_dict(employee)
        changed = False
        for name, raw_value in fields.items():
            if name not in EMPLOYEE_EDITABLE_FIELDS:
                continue
            value = raw_value.strip() if isinstance(raw_value, str) else raw_value
            value = value or None
            if name == "name" and not value:
                continue
            if getattr(employee, name) != value:
                setattr(employee, name, value)
                changed = True
        if changed:
            employee.status = normalize_employment_status(employee.status, employee.resign_date)
            self.session.flush()
            self.log_change("employee", employee.id, "edit", before, _employee_dict(employee))
        return changed

    def apply_hierarchy_spec(self, spec: HierarchySpec) -> None:
        """'위계' 시트로부터 표시순서·상위 조직을 반영한다."""
        if spec.is_empty():
            return
        by_name: dict[str, list[OrgUnit]] = {}
        for org_unit in self.list_org_units():
            by_name.setdefault(org_unit.name, []).append(org_unit)
        for name, order in spec.order_by_name.items():
            for org_unit in by_name.get(name.strip(), []):
                org_unit.display_order = int(order)
        for name, parent_name in spec.parent_by_name.items():
            parents = by_name.get((parent_name or "").strip(), [])
            parent_id = parents[0].id if parents else None
            for org_unit in by_name.get(name.strip(), []):
                if parent_id and org_unit.id != parent_id:
                    self.reparent_org_unit(org_unit.id, parent_id)
        self.session.flush()

    def mark_exit_candidate(self, employee_id: str, reason: str) -> None:
        employee = self.session.get(Employee, employee_id)
        if not employee:
            return
        before = _employee_dict(employee)
        employee.status = EmploymentStatus.EXIT_CANDIDATE.value
        self.session.add(
            EmploymentEvent(employee_id=employee.id, event_type="exit_candidate", payload=reason)
        )
        self.log_change("employee", employee.id, "exit_candidate", before, _employee_dict(employee))

    def apply_import_preview(
        self,
        preview: ImportPreview,
        approved_exit_candidate_ids: set[str] | None = None,
        hierarchy: HierarchySpec | None = None,
    ) -> None:
        approved_exit_candidate_ids = approved_exit_candidate_ids or set()
        for row in preview.rows:
            if row.action in {ImportAction.ADD, ImportAction.UPDATE}:
                self.create_or_update_employee(row.employee)
        for employee_id in preview.missing_existing_employee_ids:
            if employee_id in approved_exit_candidate_ids:
                self.mark_exit_candidate(employee_id, "최근 인사 파일 import에서 사용자가 퇴사후보로 승인함")
        if hierarchy is not None:
            self.apply_hierarchy_spec(hierarchy)

    def org_tree_payload(self) -> tuple[list[OrgUnit], list[Assignment]]:
        return self.list_org_units(), self.list_active_assignments()

    def log_change(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        before: object,
        after: object,
    ) -> None:
        self.session.add(
            ChangeLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                before=json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
                after=json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
            )
        )


def _employee_dict(employee: Employee | None) -> dict[str, str | None] | None:
    if employee is None:
        return None
    return {
        "id": employee.id,
        "employee_no": employee.employee_no,
        "name": employee.name,
        "email": employee.email,
        "grade": employee.grade,
        "title": employee.title,
        "status": employee.status,
    }
