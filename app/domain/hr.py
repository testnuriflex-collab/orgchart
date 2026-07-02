from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class EmploymentStatus(StrEnum):
    ACTIVE = "재직"
    EXIT_CANDIDATE = "퇴사후보"
    RESIGNED = "퇴사"


class ImportAction(StrEnum):
    ADD = "추가"
    UPDATE = "수정"
    EXIT_CANDIDATE = "퇴사후보"
    CONFLICT = "충돌"
    UNCHANGED = "변경없음"


@dataclass(frozen=True)
class EmployeeInput:
    employee_no: str | None
    name: str
    email: str | None = None
    department: str | None = None
    parent_department: str | None = None
    grade: str | None = None
    title: str | None = None
    hire_date: str | None = None
    resign_date: str | None = None
    status: str | None = None
    source_uuid: str | None = None
    company: str | None = None
    division: str | None = None

    def org_path_names(self) -> list[str]:
        """소속 경로를 상위→하위 순서로 반환한다.

        표준 템플릿(소속회사/소속조직/소속부서)이 있으면 3단계 경로를,
        기존 양식(상위부서/부서)만 있으면 2단계 경로를 만든다.
        """
        if self.company or self.division:
            candidates = [self.company, self.division, self.department]
        else:
            candidates = [self.parent_department, self.department]
        return [str(name).strip() for name in candidates if name and str(name).strip()]


@dataclass(frozen=True)
class CardDisplayOptions:
    """조직도 카드에 표시할 필드 토글."""

    name: bool = True
    title: bool = True
    grade: bool = True
    department: bool = False
    employee_no: bool = True
    email: bool = False
    status: bool = True

    def as_dict(self) -> dict[str, bool]:
        return {
            "name": self.name,
            "title": self.title,
            "grade": self.grade,
            "department": self.department,
            "employee_no": self.employee_no,
            "email": self.email,
            "status": self.status,
        }


@dataclass(frozen=True)
class HierarchySpec:
    """'위계' 시트에서 읽은 조직 상하·정렬 정의."""

    order_by_name: dict[str, int] = field(default_factory=dict)
    parent_by_name: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.order_by_name and not self.parent_by_name


@dataclass(frozen=True)
class ImportRowResult:
    action: ImportAction
    row_number: int
    employee: EmployeeInput
    reason: str
    matched_employee_id: str | None = None
    changes: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportPreview:
    rows: list[ImportRowResult]
    missing_existing_employee_ids: list[str]
    skipped_no_name_count: int = 0

    @property
    def counts(self) -> dict[ImportAction, int]:
        return {action: sum(1 for row in self.rows if row.action == action) for action in ImportAction}


def normalize_employment_status(status: str | None, resign_date: str | None = None) -> str:
    if resign_date:
        return EmploymentStatus.RESIGNED.value
    if not status:
        return EmploymentStatus.ACTIVE.value
    if "퇴" in status:
        return EmploymentStatus.RESIGNED.value
    return EmploymentStatus.ACTIVE.value
