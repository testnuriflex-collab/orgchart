from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session

from app.db.models import Assignment, Employee, OrgUnit
from app.db.repository import HrRepository
from app.domain.hr import (
    EmployeeInput,
    HierarchySpec,
    ImportAction,
    ImportPreview,
    ImportRowResult,
    normalize_employment_status,
)

# 필드 → 허용 컬럼명(별칭). 표준 템플릿(소속회사/소속조직/소속부서)과
# 기존 양식(부서/상위부서)을 모두 인식한다. 앞에 있는 별칭이 우선.
FIELD_ALIASES: dict[str, list[str]] = {
    "employee_no": ["사번"],
    "name": ["이름", "성명"],
    "email": ["이메일", "메일"],
    "company": ["소속회사", "회사"],
    "division": ["소속조직", "조직", "본부"],
    "department": ["소속부서", "부서", "팀"],
    "parent_department": ["상위부서"],
    "grade": ["직급"],
    "title": ["직책", "직위"],
    "hire_date": ["입사일"],
    "resign_date": ["퇴사일"],
    "status": ["재직상태", "상태"],
    "source_uuid": ["_org_chart_uuid"],
}

# 기존 호환용 단순 매핑(외부에서 참조할 수 있어 유지).
DEFAULT_COLUMN_MAP = {field: aliases[0] for field, aliases in FIELD_ALIASES.items()}

# 필수 논리 필드 → 사용자에게 보여줄 대표 라벨.
REQUIRED_FIELDS = {
    "name": "이름",
    "department": "부서",
    "status": "재직상태",
}

PEOPLE_SHEET_NAME = "명단"
HIERARCHY_SHEET_NAME = "위계"

HIERARCHY_NAME_ALIASES = ["이름", "조직명", "명칭", "부서"]
HIERARCHY_PARENT_ALIASES = ["상위", "상위조직", "상위부서", "부모"]
HIERARCHY_ORDER_ALIASES = ["표시순서", "순서", "정렬", "우선순위"]

SUPPORTED_INPUT_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv", ".json"}
EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
INPUT_FILE_FILTER = "인사정보 파일 (*.xlsx *.xlsm *.xls *.csv *.json);;Excel (*.xlsx *.xlsm *.xls);;CSV (*.csv);;JSON (*.json)"


def _resolve_value(raw_row: object, aliases: list[str]) -> str | None:
    for column_name in aliases:
        if column_name in raw_row:
            cleaned = _clean_cell(raw_row.get(column_name, ""))
            if cleaned is not None:
                return cleaned
    return None


class ExcelImporter:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = HrRepository(session)

    def read_rows(
        self,
        path: Path,
        column_map: dict[str, str] | None = None,
        sheet_name: str | int | None = None,
    ) -> list[EmployeeInput]:
        rows, _ = self._read_rows_with_skipped(path, column_map, sheet_name)
        return rows

    def _read_rows_with_skipped(
        self,
        path: Path,
        column_map: dict[str, str] | None = None,
        sheet_name: str | int | None = None,
    ) -> tuple[list[EmployeeInput], int]:
        """명단 행을 읽고, 데이터는 있으나 이름이 비어 탈락한 행 수를 함께 반환한다."""
        extra_aliases = column_map or {}
        target_sheet = sheet_name if sheet_name is not None else people_sheet_name(path)
        frame = read_people_frame(path, sheet_name=target_sheet)
        rows: list[EmployeeInput] = []
        skipped_no_name = 0
        for _, raw_row in frame.iterrows():
            values: dict[str, str | None] = {}
            for field, aliases in FIELD_ALIASES.items():
                merged = [extra_aliases[field]] + aliases if field in extra_aliases else aliases
                values[field] = _resolve_value(raw_row, merged)
            if not values["name"]:
                # 완전히 빈 행은 무시하고, 다른 데이터가 있는데 이름만 빈 행만 집계한다.
                if any(value for value in values.values()):
                    skipped_no_name += 1
                continue
            rows.append(EmployeeInput(**values))
        return rows, skipped_no_name

    def read_hierarchy(self, path: Path) -> HierarchySpec:
        return read_hierarchy_spec(path)

    def preview(
        self,
        path: Path,
        column_map: dict[str, str] | None = None,
        sheet_name: str | int | None = None,
    ) -> ImportPreview:
        inputs, skipped_no_name = self._read_rows_with_skipped(path, column_map, sheet_name)
        seen_employee_ids: set[str] = set()
        results: list[ImportRowResult] = []
        # 파일 내부에서 같은 사번을 서로 다른 직원이 공유하면 조용한 덮어쓰기(데이터 유실)
        # 위험이 있으므로 CONFLICT로 승격해 자동 병합을 차단한다.
        conflicting_employee_nos = _conflicting_employee_nos(inputs)

        for index, employee_input in enumerate(inputs, start=2):
            if (
                employee_input.employee_no
                and employee_input.employee_no in conflicting_employee_nos
            ):
                results.append(
                    ImportRowResult(
                        action=ImportAction.CONFLICT,
                        row_number=index,
                        employee=employee_input,
                        reason=(
                            f"같은 사번({employee_input.employee_no})이 이름이 다른 여러 직원에게 "
                            "중복되어 있습니다. 사번을 정정한 뒤 다시 가져와 주세요."
                        ),
                    )
                )
                continue
            matched = self.repository.find_employee(
                employee_no=employee_input.employee_no,
                email=employee_input.email,
                source_uuid=employee_input.source_uuid,
            )
            if matched:
                seen_employee_ids.add(matched.id)
                changes = _diff_employee(
                    matched,
                    employee_input,
                    _active_assignment_for_employee(self.session, matched.id),
                )
                action = ImportAction.UPDATE if changes else ImportAction.UNCHANGED
                results.append(
                    ImportRowResult(
                        action=action,
                        row_number=index,
                        employee=employee_input,
                        reason="기존 직원과 매칭됨" if changes else "변경 없음",
                        matched_employee_id=matched.id,
                        changes=changes,
                    )
                )
            else:
                ambiguous = _has_name_collision(self.session, employee_input.name)
                results.append(
                    ImportRowResult(
                        action=ImportAction.CONFLICT if ambiguous else ImportAction.ADD,
                        row_number=index,
                        employee=employee_input,
                        reason=(
                            "동명이인이 있어 자동으로 가져올 수 없습니다. "
                            "사번이나 이메일을 입력해 다시 가져와 주세요."
                        )
                        if ambiguous
                        else "신규 직원",
                    )
                )

        existing_ids = {employee.id for employee in self.repository.list_employees()}
        missing_ids = sorted(existing_ids - seen_employee_ids)
        return ImportPreview(
            rows=results,
            missing_existing_employee_ids=missing_ids,
            skipped_no_name_count=skipped_no_name,
        )

    def read_columns(self, path: Path) -> list[str]:
        sheet = people_sheet_name(path)
        return list(read_people_frame(path, sheet_name=sheet, nrows=0).columns.astype(str))

    def validate_fixed_template(self, path: Path) -> list[str]:
        columns = set(self.read_columns(path))
        missing: list[str] = []
        for field, label in REQUIRED_FIELDS.items():
            if not any(alias in columns for alias in FIELD_ALIASES[field]):
                missing.append(label)
        return sorted(missing)


PeopleFileImporter = ExcelImporter


def _excel_sheet_names(path: Path) -> list[str]:
    if path.suffix.lower() not in EXCEL_SUFFIXES:
        return []
    try:
        with pd.ExcelFile(path) as workbook:
            return [str(name) for name in workbook.sheet_names]
    except Exception:
        return []


def people_sheet_name(path: Path) -> str | int:
    """직원 명단이 담긴 시트 이름을 고른다. '명단' 시트가 있으면 그것을, 없으면 첫 시트."""
    names = _excel_sheet_names(path)
    if PEOPLE_SHEET_NAME in names:
        return PEOPLE_SHEET_NAME
    return 0


def read_hierarchy_spec(path: Path) -> HierarchySpec:
    """'위계' 시트를 읽어 표시순서·상위 조직 정의를 만든다. 없으면 빈 스펙."""
    if HIERARCHY_SHEET_NAME not in _excel_sheet_names(path):
        return HierarchySpec()
    frame = read_people_frame(path, sheet_name=HIERARCHY_SHEET_NAME)
    order_by_name: dict[str, int] = {}
    parent_by_name: dict[str, str] = {}
    for position, (_, raw_row) in enumerate(frame.iterrows()):
        name = _resolve_value(raw_row, HIERARCHY_NAME_ALIASES)
        if not name:
            continue
        parent = _resolve_value(raw_row, HIERARCHY_PARENT_ALIASES)
        if parent:
            parent_by_name[name] = parent
        order_text = _resolve_value(raw_row, HIERARCHY_ORDER_ALIASES)
        order_by_name[name] = _to_int(order_text, position)
    return HierarchySpec(order_by_name=order_by_name, parent_by_name=parent_by_name)


def _to_int(value: str | None, fallback: int) -> int:
    if value is None:
        return fallback
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def read_people_frame(
    path: Path,
    sheet_name: str | int = 0,
    nrows: int | None = None,
) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_INPUT_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_INPUT_SUFFIXES))
        raise ValueError(f"지원하지 않는 파일 형식입니다: {suffix or '확장자 없음'} ({supported})")
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(
            path,
            sheet_name=sheet_name,
            dtype=str,
            keep_default_na=False,
            nrows=nrows,
        ).fillna("")
    if suffix == ".csv":
        return _read_csv_frame(path, nrows=nrows).fillna("")
    return _read_json_frame(path, nrows=nrows).fillna("")


def _read_csv_frame(path: Path, nrows: int | None = None) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            nrows=nrows,
            encoding="utf-8-sig",
        )
    except UnicodeDecodeError:
        return pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            nrows=nrows,
            encoding="cp949",
        )


def _read_json_frame(path: Path, nrows: int | None = None) -> pd.DataFrame:
    with path.open("r", encoding="utf-8-sig") as file:
        payload: Any = json.load(file)
    if isinstance(payload, dict):
        for key in ("employees", "rows", "data", "인사정보"):
            if key in payload:
                payload = payload[key]
                break
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ValueError(
            "JSON은 직원 객체 배열이거나 employees/rows/data 키를 가진 객체여야 합니다."
        )
    frame = pd.DataFrame(payload, dtype=str)
    if nrows is not None:
        return frame.head(nrows)
    return frame


def _clean_cell(value: object) -> str | None:
    text = str(value).strip()
    return text or None


def _active_assignment_for_employee(session: Session, employee_id: str) -> Assignment | None:
    return session.scalar(
        select(Assignment)
        .options(joinedload(Assignment.org_unit).joinedload(OrgUnit.parent))
        .where(Assignment.employee_id == employee_id, Assignment.end_date.is_(None))
    )


def _org_ancestor_names(org: OrgUnit | None) -> list[str]:
    """말단 조직에서 최상위까지의 이름을 상위→하위 순서로 반환한다."""
    names: list[str] = []
    seen: set[str] = set()
    current = org
    while current is not None and current.id not in seen:
        names.append(current.name)
        seen.add(current.id)
        current = current.parent
    return list(reversed(names))


def _diff_employee(
    employee: Employee,
    employee_input: EmployeeInput,
    assignment: Assignment | None,
) -> dict[str, tuple[str | None, str | None]]:
    org = assignment.org_unit if assignment else None
    current_path = _org_ancestor_names(org)
    input_path = employee_input.org_path_names()

    def level(path: list[str], from_end: int) -> str | None:
        return path[-from_end] if len(path) >= from_end else None

    fields = {
        "employee_no": employee_input.employee_no,
        "name": employee_input.name,
        "email": employee_input.email,
        "department": level(input_path, 1),
        "parent_department": level(input_path, 2),
        "company": level(input_path, 3),
        "grade": employee_input.grade,
        "title": employee_input.title,
        "hire_date": employee_input.hire_date,
        "resign_date": employee_input.resign_date,
        "status": normalize_employment_status(employee_input.status, employee_input.resign_date),
    }
    current_values = {
        "employee_no": employee.employee_no,
        "name": employee.name,
        "email": employee.email,
        "department": level(current_path, 1),
        "parent_department": level(current_path, 2),
        "company": level(current_path, 3),
        "grade": employee.grade,
        "title": employee.title,
        "hire_date": employee.hire_date,
        "resign_date": employee.resign_date,
        "status": employee.status,
    }
    changes: dict[str, tuple[str | None, str | None]] = {}
    for field, new_value in fields.items():
        if current_values[field] != new_value:
            changes[field] = (current_values[field], new_value)
    return changes


def _conflicting_employee_nos(inputs: list[EmployeeInput]) -> set[str]:
    """같은 사번을 이름이 서로 다른 직원들이 공유하는 사번 집합을 반환한다.

    같은 사번 + 같은 이름(단순 중복 행)은 upsert가 멱등이라 충돌이 아니고,
    같은 사번인데 이름이 2개 이상이면 자동 병합 시 한쪽이 조용히 소멸하므로 충돌이다.
    """
    names_by_no: dict[str, set[str]] = {}
    for item in inputs:
        if item.employee_no:
            names_by_no.setdefault(item.employee_no, set()).add((item.name or "").strip())
    return {no for no, names in names_by_no.items() if len(names) > 1}


def _has_name_collision(session: Session, name: str) -> bool:
    from sqlalchemy import select

    return session.scalar(select(Employee).where(Employee.name == name)) is not None
