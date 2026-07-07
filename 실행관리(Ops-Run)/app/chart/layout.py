from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmployeeNode:
    id: str
    name: str
    grade: str | None
    title: str | None
    status: str
    employee_no: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class OrgNode:
    id: str
    name: str
    parent_id: str | None
    display_order: int = 0
    employees: tuple[EmployeeNode, ...] = ()


@dataclass
class LayoutBox:
    id: str
    kind: str
    x: float
    y: float
    width: float
    height: float
    label: str
    parent_id: str | None = None
    meta: dict[str, str | None] = field(default_factory=dict)


CARD_WIDTH = 272
ORG_HEIGHT = 96
EMPLOYEE_HEIGHT = 76
H_GAP = 68
V_GAP = 76
EMPLOYEE_GAP = 14
VISIBLE_EMPLOYEE_LIMIT = 6
COMPACT_EMPLOYEE_LIMIT = 5
MEMBER_INDENT = 18
MEMBER_START_GAP = 22
VIRTUAL_ROOT_ID = "__company_root__"

GRADE_PRIORITY = {
    "대표": 0,
    "임원": 1,
    "부사장": 2,
    "전무": 3,
    "상무": 4,
    "이사": 5,
    "본부장": 6,
    "팀장": 7,
    "수석": 8,
    "책임": 9,
    "선임": 10,
    "매니저": 11,
    "사원": 12,
    "인턴": 13,
}


def employee_sort_key(employee: EmployeeNode) -> tuple[bool, int, str, str]:
    grade = employee.grade or ""
    title = employee.title or ""
    seniority = min(
        [GRADE_PRIORITY[token] for token in GRADE_PRIORITY if token in grade or token in title],
        default=99,
    )
    return (employee.status != "재직", seniority, grade, employee.name)


def employee_matches_query(employee: EmployeeNode, query: str) -> bool:
    if not query:
        return False
    searchable = " ".join(
        filter(
            None,
            [
                employee.name,
                employee.title,
                employee.grade,
                employee.status,
                employee.employee_no,
                employee.email,
            ],
        )
    ).lower()
    return query in searchable


def visible_employee_limit(employee_count: int) -> int:
    if employee_count > VISIBLE_EMPLOYEE_LIMIT:
        return COMPACT_EMPLOYEE_LIMIT
    return min(employee_count, VISIBLE_EMPLOYEE_LIMIT)


def compute_org_layout(org_units: list[OrgNode], highlight_query: str = "") -> list[LayoutBox]:
    highlight_query = highlight_query.strip().lower()
    children: dict[str | None, list[OrgNode]] = {}
    for org in org_units:
        children.setdefault(org.parent_id, []).append(org)
    for siblings in children.values():
        siblings.sort(key=lambda item: (item.display_order, item.name))

    boxes: list[LayoutBox] = []

    def connector_meta(
        x: float,
        y: float,
        width: float,
        height: float,
        connector_kind: str,
    ) -> dict[str, str]:
        center_x = x + width / 2
        return {
            "connector_kind": connector_kind,
            "connector_top_x": f"{center_x:.1f}",
            "connector_top_y": f"{y:.1f}",
            "connector_bottom_x": f"{center_x:.1f}",
            "connector_bottom_y": f"{y + height:.1f}",
        }

    subtree_width_cache: dict[str, float] = {}

    def subtree_width(org: OrgNode) -> float:
        cached = subtree_width_cache.get(org.id)
        if cached is not None:
            return cached
        child_widths = [subtree_width(child) for child in children.get(org.id, [])]
        own_width = CARD_WIDTH
        if not child_widths:
            result = own_width
        else:
            result = max(own_width, sum(child_widths) + H_GAP * (len(child_widths) - 1))
        subtree_width_cache[org.id] = result
        return result

    def member_block_height(org: OrgNode) -> float:
        if not org.employees:
            return 0
        visible_count = visible_employee_limit(len(org.employees))
        overflow_count = 1 if len(org.employees) > visible_count else 0
        row_count = visible_count + overflow_count
        return MEMBER_START_GAP + row_count * EMPLOYEE_HEIGHT + (row_count - 1) * EMPLOYEE_GAP

    def place(
        org: OrgNode,
        left: float,
        top: float,
        visual_parent_id: str | None = None,
        depth: int = 0,
    ) -> float:
        width = subtree_width(org)
        org_x = left + (width - CARD_WIDTH) / 2
        tone = str((org.display_order + len(org.name)) % 5)
        # 레벨별 색 구분용 위계 라벨: 0=회사, 1=본부, 2+=팀.
        level = "company" if depth == 0 else ("division" if depth == 1 else "team")
        boxes.append(
            LayoutBox(
                id=org.id,
                kind="org",
                x=org_x,
                y=top,
                width=CARD_WIDTH,
                height=ORG_HEIGHT,
                label=org.name,
                parent_id=visual_parent_id if visual_parent_id is not None else org.parent_id,
                meta={
                    **connector_meta(org_x, top, CARD_WIDTH, ORG_HEIGHT, "org"),
                    "highlight": "true" if highlight_query and highlight_query in org.name.lower() else None,
                    "employee_count": str(len(org.employees)),
                    "is_root": "true" if org.parent_id is None else None,
                    "level": level,
                    "depth": str(depth),
                    "tone": tone,
                },
            )
        )

        employee_y = top + ORG_HEIGHT + MEMBER_START_GAP
        employee_count = len(org.employees)
        if employee_count:
            visible_count = visible_employee_limit(employee_count)
            overflow_count = employee_count - visible_count
            sorted_employees = sorted(
                org.employees,
                key=lambda employee: (
                    not employee_matches_query(employee, highlight_query) if highlight_query else False,
                    *employee_sort_key(employee),
                ),
            )
            visible_employees = sorted_employees[:visible_count]
            hidden_employees = sorted_employees[visible_count:]
            for index, employee in enumerate(visible_employees):
                boxes.append(
                    LayoutBox(
                        id=employee.id,
                        kind="employee",
                        x=org_x + MEMBER_INDENT,
                        y=employee_y + index * (EMPLOYEE_HEIGHT + EMPLOYEE_GAP),
                        width=CARD_WIDTH - MEMBER_INDENT,
                        height=EMPLOYEE_HEIGHT,
                        label=employee.name,
                        parent_id=org.id,
                        meta={
                            **connector_meta(
                                org_x + MEMBER_INDENT,
                                employee_y + index * (EMPLOYEE_HEIGHT + EMPLOYEE_GAP),
                                CARD_WIDTH - MEMBER_INDENT,
                                EMPLOYEE_HEIGHT,
                                "member",
                            ),
                            "grade": employee.grade,
                            "title": employee.title,
                            "status": employee.status,
                            "employee_no": employee.employee_no,
                            "email": employee.email,
                            "department": org.name,
                            "tone": tone,
                            "highlight": "true"
                            if employee_matches_query(employee, highlight_query)
                            else None,
                        },
                    )
                )
            if overflow_count:
                hidden_names = ", ".join(employee.name for employee in hidden_employees[:12])
                hidden_overflow = len(hidden_employees) - 12
                if hidden_overflow > 0:
                    hidden_names = f"{hidden_names}, 외 {hidden_overflow}명"
                boxes.append(
                    LayoutBox(
                        id=f"{org.id}:overflow",
                        kind="overflow",
                        x=org_x + MEMBER_INDENT,
                        y=employee_y + visible_count * (EMPLOYEE_HEIGHT + EMPLOYEE_GAP),
                        width=CARD_WIDTH - MEMBER_INDENT,
                        height=EMPLOYEE_HEIGHT,
                        label=f"+{overflow_count}명 더보기",
                        parent_id=org.id,
                        meta={
                            **connector_meta(
                                org_x + MEMBER_INDENT,
                                employee_y + visible_count * (EMPLOYEE_HEIGHT + EMPLOYEE_GAP),
                                CARD_WIDTH - MEMBER_INDENT,
                                EMPLOYEE_HEIGHT,
                                "member",
                            ),
                            "org_id": org.id,
                            "status": "접힌 구성원",
                            "employee_names": hidden_names,
                            "tone": tone,
                            "highlight": "true"
                            if any(employee_matches_query(employee, highlight_query) for employee in hidden_employees)
                            else None,
                        },
                    )
                )

        child_top = top + ORG_HEIGHT + member_block_height(org) + V_GAP
        child_left = left
        for child in children.get(org.id, []):
            child_width = subtree_width(child)
            place(child, child_left, child_top, depth=depth + 1)
            child_left += child_width + H_GAP
        return width

    root_units = children.get(None, [])
    if len(root_units) > 1:
        root_widths = [subtree_width(root) for root in root_units]
        total_width = sum(root_widths) + H_GAP * (len(root_widths) - 1)
        boxes.append(
            LayoutBox(
                id=VIRTUAL_ROOT_ID,
                kind="summary",
                x=(total_width - CARD_WIDTH) / 2,
                y=0,
                width=CARD_WIDTH,
                height=ORG_HEIGHT,
                label="회사 조직도",
                parent_id=None,
                meta={
                    **connector_meta((total_width - CARD_WIDTH) / 2, 0, CARD_WIDTH, ORG_HEIGHT, "org"),
                    "employee_count": "",
                    "is_root": "true",
                },
            )
        )
        cursor = 0.0
        for root, root_width in zip(root_units, root_widths, strict=True):
            place(root, cursor, ORG_HEIGHT + V_GAP, VIRTUAL_ROOT_ID)
            cursor += root_width + H_GAP
        return boxes

    cursor = 0.0
    for root in root_units:
        root_width = subtree_width(root)
        place(root, cursor, 0.0)
        cursor += root_width + H_GAP
    return boxes
