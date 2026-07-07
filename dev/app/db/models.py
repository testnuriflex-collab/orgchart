from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    employee_no: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="재직")
    hire_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resign_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class OrgUnit(Base):
    __tablename__ = "org_units"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("org_units.id"), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    parent: Mapped[OrgUnit | None] = relationship(remote_side="OrgUnit.id", backref="children")
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="org_unit", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("name", "parent_id", name="uq_org_unit_name_parent"),)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), nullable=False)
    org_unit_id: Mapped[str] = mapped_column(ForeignKey("org_units.id"), nullable=False)
    start_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    employee: Mapped[Employee] = relationship(back_populates="assignments")
    org_unit: Mapped[OrgUnit] = relationship(back_populates="assignments")


class EmploymentEvent(Base):
    __tablename__ = "employment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ImportRow(Base):
    __tablename__ = "import_rows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class ChangeLog(Base):
    __tablename__ = "change_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    actor: Mapped[str] = mapped_column(String(80), default="local-user")
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    before: Mapped[str | None] = mapped_column(Text, nullable=True)
    after: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    export_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
