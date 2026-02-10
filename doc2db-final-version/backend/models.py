"""Metadata models for Doc2DB-Gen (projects, extractions)."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from db import Base


class Project(Base):
    """A Doc2DB-Gen project (one upload batch)."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), default="Untitled")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Extraction(Base):
    """Result of one LLM extraction (ER + DDL + sample data)."""

    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    er_diagram = Column(Text)  # Mermaid or text ER description
    sql_ddl = Column(Text)    # Generated SQL DDL
    raw_llm_response = Column(Text)
    extraction_data = Column(Text)  # JSON: list of { "table": "...", "rows": [...] }
    created_at = Column(DateTime(timezone=True), server_default=func.now())
