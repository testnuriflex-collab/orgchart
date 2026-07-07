"""적대적 감사(audit_findings.md) 데이터/로직 결함 회귀 테스트.

커버: C2(동일 사번 데이터 유실), M4(이름 누락 스킵 집계), M5(발령 날짜),
H1(부서명 충돌 방어), L2(subtree_width 메모이제이션).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.chart.layout import CARD_WIDTH, H_GAP, OrgNode, compute_org_layout
from app.db.repository import HrRepository, OrgUnitNameConflictError
from app.db.session import create_session_factory, initialize_database
from app.domain.hr import EmployeeInput, ImportAction
from app.importer.excel_importer import ExcelImporter


def _factory(tmp_path: Path):
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    return session_factory


def _write_people_xlsx(path: Path, rows: list[dict]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="명단", index=False)


# ── C2: 동일 사번, 다른 직원 → 조용한 덮어쓰기 차단 ──────────────────────
def test_duplicate_employee_no_becomes_conflict(tmp_path: Path) -> None:
    path = tmp_path / "dup.xlsx"
    _write_people_xlsx(
        path,
        [
            {"사번": "E100", "이름": "김철수", "부서": "영업팀", "재직상태": "재직"},
            {"사번": "E100", "이름": "이영희", "부서": "마케팅팀", "재직상태": "재직"},
        ],
    )
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        preview = ExcelImporter(session).preview(path)
    conflict_rows = [row for row in preview.rows if row.action == ImportAction.CONFLICT]
    assert len(conflict_rows) == 2
    assert all("E100" in row.reason for row in conflict_rows)
    # 충돌이 있으므로 적용 시 두 사람 모두 살아있어야 한다(자동 병합 차단).
    assert preview.counts[ImportAction.ADD] == 0


def test_same_no_same_name_is_not_conflict(tmp_path: Path) -> None:
    path = tmp_path / "same.xlsx"
    _write_people_xlsx(
        path,
        [
            {"사번": "E200", "이름": "홍길동", "부서": "영업팀", "재직상태": "재직"},
            {"사번": "E200", "이름": "홍길동", "부서": "영업팀", "재직상태": "재직"},
        ],
    )
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        preview = ExcelImporter(session).preview(path)
    assert preview.counts[ImportAction.CONFLICT] == 0


# ── M4: 이름 누락 행 스킵 카운트 ─────────────────────────────────────────
def test_missing_name_rows_are_counted(tmp_path: Path) -> None:
    path = tmp_path / "missing.xlsx"
    _write_people_xlsx(
        path,
        [
            {"사번": "E300", "이름": "정민서", "부서": "대표이사실", "재직상태": "재직"},
            {"사번": "E301", "이름": "", "부서": "영업팀", "재직상태": "재직"},
        ],
    )
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        preview = ExcelImporter(session).preview(path)
    assert preview.skipped_no_name_count == 1
    assert len(preview.rows) == 1


# ── M5: 발령 이력이 실제 ISO 날짜로 기록 ─────────────────────────────────
def test_move_records_iso_dates_not_sentinel(tmp_path: Path) -> None:
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        employee = repository.create_or_update_employee(
            EmployeeInput(employee_no="A001", name="홍길동", department="인사팀")
        )
        finance = repository.ensure_org_unit("재무팀")
        session.commit()
        repository.move_employee(employee.id, finance.id)
        session.commit()

    with session_factory() as session:
        from sqlalchemy import select

        from app.db.models import Assignment

        assignments = list(session.scalars(select(Assignment)))
        ended = [a for a in assignments if a.end_date is not None]
        active = [a for a in assignments if a.end_date is None]
        assert ended and ended[0].end_date != "변경"
        # ISO 날짜 형식(YYYY-MM-DD)인지 확인.
        assert ended[0].end_date.count("-") == 2
        assert active and active[0].start_date is not None


# ── H1: 부서명 충돌 방어(rename/reparent/bulk) ──────────────────────────
def test_rename_sibling_conflict_raises(tmp_path: Path) -> None:
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        repository.ensure_org_unit("인사팀")
        repository.ensure_org_unit("피플팀")
        session.commit()
        units = {u.name: u.id for u in repository.list_org_units()}
        with pytest.raises(OrgUnitNameConflictError):
            repository.rename_org_unit(units["인사팀"], "피플팀")


def test_reparent_sibling_conflict_raises(tmp_path: Path) -> None:
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        repository.ensure_org_path(["본부A", "공통팀"])
        repository.ensure_org_path(["본부B", "공통팀"])
        session.commit()
        units = {(u.name, u.parent_id): u for u in repository.list_org_units()}
        b = next(u for (name, _), u in units.items() if name == "본부B")
        b_child = next(
            u for (name, pid), u in units.items() if name == "공통팀" and pid == b.id
        )
        a = next(u for (name, pid), u in units.items() if name == "본부A" and pid is None)
        with pytest.raises(OrgUnitNameConflictError):
            repository.reparent_org_unit(b_child.id, a.id)


def test_bulk_rename_skips_conflict(tmp_path: Path) -> None:
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        repository.ensure_org_unit("인사팀")
        repository.ensure_org_unit("피플팀")
        session.commit()
        changed, conflicts, reverts = repository.bulk_rename_org_units({"인사팀": "피플팀"})
        session.commit()
        assert changed == 0
        assert conflicts == ["피플팀"]
        assert reverts == []
    with session_factory() as session:
        names = {u.name for u in HrRepository(session).list_org_units()}
        assert "인사팀" in names  # 충돌로 건너뛰어 원본 유지


# ── L2: subtree_width 메모이제이션(깊은 체인에서도 정확·완주) ──────────────
def test_layout_deep_chain_is_correct_and_completes() -> None:
    depth = 400
    nodes = [
        OrgNode(id=f"n{i}", name=f"조직{i}", parent_id=(f"n{i - 1}" if i else None))
        for i in range(depth)
    ]
    boxes = compute_org_layout(nodes)
    org_boxes = [b for b in boxes if b.kind == "org"]
    assert len(org_boxes) == depth
    # 단일 체인이므로 모든 카드 폭은 CARD_WIDTH로 동일.
    assert all(b.width == CARD_WIDTH for b in org_boxes)


def test_layout_memoization_matches_expected_width() -> None:
    # 루트 + 자식 3개 → 루트 subtree 폭 = 3*CARD + 2*H_GAP.
    nodes = [
        OrgNode(id="root", name="루트", parent_id=None),
        OrgNode(id="c1", name="c1", parent_id="root"),
        OrgNode(id="c2", name="c2", parent_id="root"),
        OrgNode(id="c3", name="c3", parent_id="root"),
    ]
    boxes = compute_org_layout(nodes)
    xs = [b.x for b in boxes if b.kind == "org" and b.id.startswith("c")]
    span = max(xs) - min(xs) + CARD_WIDTH
    assert span == 3 * CARD_WIDTH + 2 * H_GAP
