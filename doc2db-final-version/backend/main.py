"""Doc2DB-Gen: FastAPI server — uploads, LLM extraction, schema, DB ingestion."""
import csv
import io
import json
import traceback
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from db import get_session, init_db
from llm_client import (
    extract_schema_from_image,
    extract_schema_from_text,
    extract_table_data_from_image,
    schema_to_ddl,
    schema_to_er_mermaid,
)
from models import Extraction, Project
from schema_engine import get_table_preview, insert_extracted_data, run_ddl

app = FastAPI(title="Doc2DB-Gen", description="PDFs/Tables/Images → Normalized DB")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.on_event("startup")
async def startup():
    await init_db()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Return JSON with error detail for any unhandled exception."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    tb = traceback.format_exc()
    print(tb, flush=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": tb.split("\n")[-4:-1]},
    )


class ExtractResponse(BaseModel):
    project_id: str
    extraction_id: int
    er_diagram: str
    sql_ddl: str
    raw_entities: list
    raw_relationships: list


@app.post("/api/projects", response_model=dict)
async def create_project(name: Optional[str] = None):
    async with get_session() as session:
        p = Project(name=name or "Untitled")
        session.add(p)
        await session.flush()
        return {"project_id": str(p.id), "name": p.name}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_id: Optional[str] = None,
):
    if not project_id:
        raise HTTPException(400, "project_id required")
    ext = (Path(file.filename or "").suffix or "").lower()
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls", ".csv", ".txt"}
    if ext not in allowed:
        raise HTTPException(400, f"Allowed: {allowed}")
    path = UPLOAD_DIR / f"{project_id}_{uuid.uuid4().hex}{ext}"
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(400, f"Max size {settings.max_upload_mb}MB")
    with open(path, "wb") as f:
        f.write(content)
    # Use forward slashes so path works when sent back to extract on any OS
    path_str = path.as_posix()
    return {"path": path_str, "filename": file.filename, "size": len(content)}


class ExtractBody(BaseModel):
    upload_path: str


@app.post("/api/extract")
async def extract_schema(project_id: str, body: ExtractBody):
    try:
        return await _do_extract(project_id, body)
    except HTTPException as he:
        return JSONResponse(status_code=he.status_code, content={"detail": he.detail})
    except BaseException as e:
        tb = traceback.format_exc()
        print("EXTRACT ERROR:", tb, flush=True)
        return JSONResponse(status_code=500, content={"detail": str(e), "traceback": tb.split("\n")})


async def _do_extract(project_id: str, body: ExtractBody):
    try:
        # Normalize path: use forward slashes, resolve relative to backend
        raw = (body.upload_path or "").strip().replace("\\", "/")
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise HTTPException(404, "Upload not found")
        ext = path.suffix.lower()
        mime = "image/png"
        if ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif ext == ".pdf":
            try:
                import fitz  # pymupdf
                doc = fitz.open(path)
                page = doc.load_page(0)
                pix = page.get_pixmap()
                img_path = path.with_suffix(".png")
                pix.save(str(img_path))
                doc.close()
                path = img_path
                mime = "image/png"
            except ImportError:
                raise HTTPException(400, "PDF support requires: pip install pymupdf")
            except Exception as e:
                raise HTTPException(400, f"PDF conversion failed: {e}")
        file_rows_for_data = None
        if ext in (".png", ".jpg", ".jpeg", ".pdf"):
            extraction = await extract_schema_from_image(path, mime)
            if not extraction.get("table_data") and extraction.get("entities"):
                extraction["table_data"] = await extract_table_data_from_image(
                    path, mime, extraction.get("entities") or []
                )
        else:
            if ext in (".xlsx", ".xls"):
                import openpyxl
                wb = openpyxl.load_workbook(path, read_only=True)
                ws = wb.active
                rows = [[str(c.value or "") for c in row] for row in ws.iter_rows()]
                file_rows_for_data = rows
                text = "\n".join("\t".join(r) for r in rows)
                wb.close()
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
                if ext in (".csv", ".txt"):
                    try:
                        sniffer = csv.Sniffer()
                        dialect = sniffer.sniff(text[:4096]) if len(text) >= 3 else csv.excel_tab
                        reader = csv.reader(io.StringIO(text), dialect)
                        file_rows_for_data = list(reader)
                    except Exception:
                        lines = [L.strip() for L in text.splitlines() if L.strip()]
                        if lines:
                            sep = "\t" if "\t" in lines[0] else ","
                            file_rows_for_data = [L.split(sep) for L in lines]
            extraction = await extract_schema_from_text(text)
        if not isinstance(extraction, dict):
            raise HTTPException(502, "LLM returned invalid structure")
        if not extraction.get("table_data") and file_rows_for_data and len(file_rows_for_data) >= 2:
            entity_name = (extraction.get("entities") or [{}])[0].get("name", "Data").replace(" ", "_")
            headers = [h.strip() or f"col_{i}" for i, h in enumerate(file_rows_for_data[0])]
            rows = [dict(zip(headers, row)) for row in file_rows_for_data[1:] if len(row) >= len(headers)]
            if rows:
                extraction["table_data"] = [{"table": entity_name, "rows": rows}]
        ddl = schema_to_ddl(extraction)
        er_mermaid = schema_to_er_mermaid(extraction)
        async with get_session() as session:
            proj = await session.get(Project, int(project_id))
            if not proj:
                raise HTTPException(404, "Project not found")
            table_data = extraction.get("table_data") or []
            ext_row = Extraction(
                project_id=proj.id,
                er_diagram=er_mermaid,
                sql_ddl=ddl,
                raw_llm_response=str(extraction),
                extraction_data=json.dumps(table_data) if table_data else None,
            )
            session.add(ext_row)
            await session.flush()
            extraction_id = ext_row.id
        # Ensure JSON-serializable (LLM sometimes returns non-str keys or other types)
        def _safe_list(lst: list) -> list[dict[str, Any]]:
            out = []
            for x in lst if lst else []:
                if isinstance(x, dict):
                    out.append({str(k): (v if isinstance(v, (str, int, float, bool, type(None))) else str(v)) for k, v in x.items()})
                else:
                    out.append({"value": str(x)})
            return out
        raw_entities = extraction.get("entities", [])
        raw_relationships = extraction.get("relationships", [])
        table_data = extraction.get("table_data") or []
        content = {
            "project_id": str(project_id),
            "extraction_id": int(extraction_id),
            "er_diagram": str(er_mermaid),
            "sql_ddl": str(ddl),
            "raw_entities": _safe_list(raw_entities) if raw_entities else [],
            "raw_relationships": _safe_list(raw_relationships) if raw_relationships else [],
            "table_data": [{"table": t.get("table"), "row_count": len(t.get("rows", []))} for t in table_data] if table_data else [],
        }
        return JSONResponse(status_code=200, content=content)
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "insufficient_quota" in err_msg or "RateLimitError" in type(e).__name__:
            raise HTTPException(429, "OpenAI rate limit or quota exceeded")
        if "401" in err_msg or "invalid_api_key" in err_msg or "AuthenticationError" in type(e).__name__:
            raise HTTPException(401, "Invalid or missing OPENAI_API_KEY")
        raise


class ApplySchemaBody(BaseModel):
    extraction_id: int


@app.post("/api/apply-schema")
async def apply_schema(project_id: str, body: ApplySchemaBody):
    async with get_session() as session:
        ext = await session.get(Extraction, body.extraction_id)
        if not ext or str(ext.project_id) != str(project_id):
            raise HTTPException(404, "Extraction not found")
        ddl = ext.sql_ddl
        extraction_data_raw = getattr(ext, "extraction_data", None) or None
    run_ddl(project_id, ddl)
    table_data = []
    if extraction_data_raw:
        try:
            table_data = json.loads(extraction_data_raw)
        except (TypeError, json.JSONDecodeError):
            pass
    rows_inserted = insert_extracted_data(project_id, {}, table_data) if table_data else 0
    return {"ok": True, "message": "DDL applied", "rows_inserted": rows_inserted}


@app.get("/api/preview/{project_id}")
async def preview_db(project_id: str):
    tables = get_table_preview(project_id)
    return {"tables": tables}


@app.get("/api/health")
async def health():
    env_path = Path(__file__).resolve().parent / ".env"
    db_ok, db_error = True, None
    try:
        async with get_session() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
    except Exception as e:
        db_ok, db_error = False, str(e)
    db_display = settings.database_url.split("@")[-1] if "@" in settings.database_url else "sqlite"
    return {
        "status": "ok",
        "llm_configured": bool(settings.openai_api_key),
        "env_exists": env_path.exists(),
        "db_ok": db_ok,
        "db_error": db_error,
        "database": db_display,
        "cwd": str(Path.cwd()),
    }


# Serve frontend
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
