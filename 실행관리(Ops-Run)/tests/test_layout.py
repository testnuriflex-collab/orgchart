from app.chart.layout import EmployeeNode, OrgNode, compute_org_layout
from app.ui.main_window import filter_nodes_for_query


def test_layout_is_deterministic_and_aligned() -> None:
    orgs = [
        OrgNode(id="root", name="대표", parent_id=None, display_order=0),
        OrgNode(
            id="dev",
            name="개발",
            parent_id="root",
            display_order=2,
            employees=(EmployeeNode("e2", "김개발", "책임", "Backend", "재직"),),
        ),
        OrgNode(
            id="hr",
            name="인사",
            parent_id="root",
            display_order=1,
            employees=(EmployeeNode("e1", "박인사", "매니저", "HR", "재직"),),
        ),
    ]

    first = compute_org_layout(orgs)
    second = compute_org_layout(list(reversed(orgs)))

    assert [(box.id, box.x, box.y) for box in first] == [(box.id, box.x, box.y) for box in second]
    assert [box.id for box in first if box.kind == "org"] == ["root", "hr", "dev"]


def test_search_filter_keeps_parent_chain_for_matching_child() -> None:
    nodes = [
        OrgNode(id="root", name="대표", parent_id=None, display_order=0),
        OrgNode(
            id="dev",
            name="개발",
            parent_id="root",
            display_order=1,
            employees=(EmployeeNode("e1", "김개발", "책임", "Backend", "재직"),),
        ),
    ]

    filtered = filter_nodes_for_query(nodes, "김개발")
    boxes = compute_org_layout(filtered)

    assert [node.id for node in filtered] == ["root", "dev"]
    assert [box.id for box in boxes if box.kind == "org"] == ["root", "dev"]


def test_search_filter_matches_grade_and_status() -> None:
    nodes = [
        OrgNode(id="root", name="대표", parent_id=None, display_order=0),
        OrgNode(
            id="ops",
            name="운영",
            parent_id="root",
            display_order=1,
            employees=(EmployeeNode("e1", "장현우", "매니저", "Business Operations", "퇴사"),),
        ),
    ]

    assert [node.id for node in filter_nodes_for_query(nodes, "퇴사")] == ["root", "ops"]
    assert [node.id for node in filter_nodes_for_query(nodes, "매니저")] == ["root", "ops"]


def test_employee_layout_orders_senior_roles_first() -> None:
    orgs = [
        OrgNode(
            id="dev",
            name="개발",
            parent_id=None,
            employees=(
                EmployeeNode("junior", "이사원", "사원", "Backend", "재직"),
                EmployeeNode("lead", "김팀장", "책임", "팀장", "재직"),
                EmployeeNode("resigned", "박퇴사", "임원", "Advisor", "퇴사"),
            ),
        )
    ]

    employees = [box.id for box in compute_org_layout(orgs) if box.kind == "employee"]

    assert employees == ["lead", "junior", "resigned"]


def test_large_org_layout_collapses_extra_employees() -> None:
    employees = tuple(
        EmployeeNode(f"e{index}", f"직원{index}", "사원", "Staff", "재직")
        for index in range(10)
    )
    boxes = compute_org_layout([OrgNode(id="large", name="큰팀", parent_id=None, employees=employees)])

    employee_boxes = [box for box in boxes if box.kind == "employee"]
    overflow_boxes = [box for box in boxes if box.kind == "overflow"]

    assert len(employee_boxes) == 5
    assert len(overflow_boxes) == 1
    assert overflow_boxes[0].label == "+5명 더보기"


def test_large_org_search_match_is_kept_visible_and_highlighted() -> None:
    employees = tuple(
        EmployeeNode(f"e{index}", f"직원{index}", "사원", "Staff", "재직")
        for index in range(9)
    ) + (EmployeeNode("target", "특별검색", "사원", "Staff", "재직"),)

    boxes = compute_org_layout(
        [OrgNode(id="large", name="큰팀", parent_id=None, employees=employees)],
        highlight_query="특별",
    )
    employee_boxes = [box for box in boxes if box.kind == "employee"]
    target_box = next(box for box in employee_boxes if box.id == "target")

    assert len(employee_boxes) == 5
    assert target_box.meta["highlight"] == "true"


def test_members_stack_vertically_under_team_card() -> None:
    boxes = compute_org_layout(
        [
            OrgNode(
                id="team",
                name="팀",
                parent_id=None,
                employees=(
                    EmployeeNode("e1", "첫째", "책임", "팀장", "재직"),
                    EmployeeNode("e2", "둘째", "사원", "Staff", "재직"),
                ),
            )
        ]
    )

    employees = [box for box in boxes if box.kind == "employee"]

    assert employees[0].x == employees[1].x
    assert employees[0].y < employees[1].y
    assert employees[0].meta["connector_kind"] == "member"


def test_multiple_root_orgs_get_company_summary_root() -> None:
    boxes = compute_org_layout(
        [
            OrgNode(id="a", name="A본부", parent_id=None),
            OrgNode(id="b", name="B본부", parent_id=None),
        ]
    )

    assert boxes[0].kind == "summary"
    assert boxes[0].label == "회사 조직도"
    assert [box.parent_id for box in boxes if box.kind == "org"] == ["__company_root__", "__company_root__"]


def test_child_org_columns_start_below_member_stack_and_keep_parent_centered() -> None:
    boxes = compute_org_layout(
        [
            OrgNode(
                id="root",
                name="대표",
                parent_id=None,
                employees=(
                    EmployeeNode("e1", "대표1", "대표", "CEO", "재직"),
                    EmployeeNode("e2", "대표2", "임원", "COO", "재직"),
                ),
            ),
            OrgNode(id="left", name="왼쪽", parent_id="root", display_order=1),
            OrgNode(id="right", name="오른쪽", parent_id="root", display_order=2),
        ]
    )

    by_id = {box.id: box for box in boxes}
    employee_bottom = max(box.y + box.height for box in boxes if box.kind == "employee")
    child_orgs = [by_id["left"], by_id["right"]]
    root_center = by_id["root"].x + by_id["root"].width / 2
    child_midpoint = (
        child_orgs[0].x
        + child_orgs[0].width / 2
        + child_orgs[1].x
        + child_orgs[1].width / 2
    ) / 2

    assert all(child.y > employee_bottom for child in child_orgs)
    assert root_center == child_midpoint
    assert by_id["root"].meta["connector_kind"] == "org"
    assert by_id["left"].meta["connector_top_y"] == f"{by_id['left'].y:.1f}"
