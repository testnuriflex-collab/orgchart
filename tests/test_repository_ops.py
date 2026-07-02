"""조직 재배치·부서 일괄 변환·직원 필드 편집 리포지토리 연산 검증."""
from __future__ import annotations

from pathlib import Path

from app.db.repository import HrRepository
from app.db.session import create_session_factory, initialize_database
from app.domain.hr import EmployeeInput


def _factory(tmp_path: Path):
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    return session_factory


def test_ensure_org_path_builds_nested_chain(tmp_path: Path) -> None:
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        leaf = repository.ensure_org_path(["회사", "본부", "팀"])
        session.commit()
        assert leaf.name == "팀"
        assert leaf.parent.name == "본부"
        assert leaf.parent.parent.name == "회사"


def test_reparent_org_unit_moves_and_blocks_cycle(tmp_path: Path) -> None:
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        repository.ensure_org_path(["A", "B", "C"])
        session.commit()
        units = {unit.name: unit.id for unit in repository.list_org_units()}

        assert repository.reparent_org_unit(units["C"], units["A"]) is True
        session.commit()

    with session_factory() as session:
        repository = HrRepository(session)
        units = {unit.name: unit for unit in repository.list_org_units()}
        assert units["C"].parent.name == "A"
        # 순환 금지: A를 자기 자손(C) 아래로 이동 불가
        assert repository.reparent_org_unit(units["A"].id, units["C"].id) is False
        # 자기 자신 아래로도 불가
        assert repository.reparent_org_unit(units["B"].id, units["B"].id) is False


def test_bulk_rename_org_units(tmp_path: Path) -> None:
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        repository.ensure_org_unit("인사팀")
        repository.ensure_org_unit("재무팀")
        session.commit()
        changed, conflicts, reverts = repository.bulk_rename_org_units(
            {"인사팀": "피플팀", "없는팀": "무시"}
        )
        session.commit()
        assert changed == 1
        assert conflicts == []
        assert reverts and reverts[0][1] == "인사팀"

    with session_factory() as session:
        names = {unit.name for unit in HrRepository(session).list_org_units()}
        assert "피플팀" in names and "인사팀" not in names


def test_update_employee_fields(tmp_path: Path) -> None:
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        employee = repository.create_or_update_employee(
            EmployeeInput(employee_no="A001", name="홍길동", department="인사팀", title="팀원")
        )
        session.commit()
        employee_id = employee.id

    with session_factory() as session:
        repository = HrRepository(session)
        changed = repository.update_employee_fields(
            employee_id, {"title": "팀장", "grade": "책임", "name": ""}
        )
        session.commit()
        assert changed is True

    with session_factory() as session:
        employee = HrRepository(session).list_employees()[0]
        assert employee.title == "팀장"
        assert employee.grade == "책임"
        assert employee.name == "홍길동"  # 빈 이름은 무시


def test_apply_hierarchy_reparents_by_name(tmp_path: Path) -> None:
    from app.domain.hr import HierarchySpec

    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        repository.ensure_org_unit("팀A")
        repository.ensure_org_unit("본부X")
        session.commit()
        repository.apply_hierarchy_spec(
            HierarchySpec(order_by_name={"본부X": 5}, parent_by_name={"팀A": "본부X"})
        )
        session.commit()

    with session_factory() as session:
        units = {unit.name: unit for unit in HrRepository(session).list_org_units()}
        assert units["팀A"].parent.name == "본부X"
        assert units["본부X"].display_order == 5
