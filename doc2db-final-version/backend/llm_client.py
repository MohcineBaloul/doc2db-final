"""LLM client for vision + text: extract entities/relationships and propose schema."""
import base64
import json
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from config import settings

SYSTEM_PROMPT = """You are a database schema expert. Given a document (PDF page, image, or table),
extract:
1. ENTITIES: main nouns (e.g. Customer, Order, Product) and their key attributes with types.
2. RELATIONSHIPS: how entities relate (e.g. Order has many OrderItems; Customer places Order).
3. NORMALIZATION: suggest 3NF-style tables; avoid redundancy.
4. TABLE_DATA: You MUST extract every row of data visible in the document (e.g. every book in a list, every row in a table). For each entity that has visible rows, list ALL rows in "table_data". Use the exact attribute names from entities as keys (same spelling/casing). Omit "id". Use the same table name as in entities.

Respond with valid JSON only, no markdown, in this exact shape:
{
  "entities": [
    { "name": "EntityName", "attributes": [ {"name": "attr_name", "type": "TEXT|INTEGER|REAL|DATE"} ] }
  ],
  "relationships": [
    { "from": "Entity1", "to": "Entity2", "type": "one-to-many|many-to-many", "fk_in": "Entity2" }
  ],
  "er_description": "Short text description of the ER model for a diagram.",
  "table_data": [
    { "table": "EntityName", "rows": [ {"attr_name": "value", ...}, ... ] }
  ]
}
If the document has no table/list at all, use "table_data": []. Otherwise include every row."""

USER_PROMPT_TEMPLATE = """Analyze this document and extract:
1) entities and relationships for a normalized relational schema,
2) ALL visible data rows into table_data (every row of every table/list you see; this is required for the database to be populated).
Return only the JSON object, no other text."""


async def _encode_file(path: Path, mime: str) -> dict:
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return {"url": f"data:{mime};base64,{data}"}


def _get_client():
    key = (settings.openai_api_key or "").strip()
    if not key or key.startswith("sk-placeholder"):
        raise ValueError(
            "OPENAI_API_KEY is not set or invalid. Add OPENAI_API_KEY=sk-... to backend/.env"
        )
    return AsyncOpenAI(api_key=key)


async def extract_schema_from_image(image_path: Path, mime: str = "image/png") -> dict:
    """Use vision model to extract schema from an image (or PDF page image)."""
    client = _get_client()
    image_url = await _encode_file(image_path, mime)

    response = await client.chat.completions.create(
        model="gpt-4o-mini",  # or gpt-4o for better vision
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT_TEMPLATE},
                    {"type": "image_url", "image_url": image_url},
                ],
            },
        ],
        max_tokens=4000,
    )
    raw = response.choices[0].message.content
    if not raw:
        raise ValueError("LLM returned empty response")
    text = raw.strip()
    # Strip markdown code block if present
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        out = json.loads(text)
        if "table_data" not in out:
            out["table_data"] = []
        return out
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response was not valid JSON: {e}. First 200 chars: {text[:200]}")


async def extract_schema_from_text(text_content: str) -> dict:
    """Extract schema from plain text (e.g. CSV/table content)."""
    client = _get_client()
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{USER_PROMPT_TEMPLATE}\n\nDocument content:\n{text_content}"},
        ],
        max_tokens=4000,
    )
    raw = response.choices[0].message.content
    if not raw:
        raise ValueError("LLM returned empty response")
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    try:
        out = json.loads(raw)
        if "table_data" not in out:
            out["table_data"] = []
        return out
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response was not valid JSON: {e}. First 200 chars: {raw[:200]}")


DATA_EXTRACT_PROMPT = """Extract every row of data visible in this document (e.g. every book, every line in the list).
Return valid JSON only, no markdown, in this exact shape:
{"table_data": [{"table": "EntityName", "rows": [{"Col1": "value1", "Col2": "value2", ...}, ...]}]}
Use the exact column names: {columns}. Table name: {table_name}. Include every row you see."""


async def extract_table_data_from_image(image_path: Path, mime: str, entities: list) -> list:
    """Second LLM call: extract only table_data from image when first call didn't return it."""
    if not entities:
        return []
    ent = entities[0]
    table_name = ent.get("name", "Data").replace(" ", "_")
    attrs = ent.get("attributes", [])
    columns = [a.get("name", "col") for a in attrs if a.get("name", "col").lower() != "id"]
    if not columns:
        return []
    client = _get_client()
    image_url = await _encode_file(image_path, mime)
    prompt = DATA_EXTRACT_PROMPT.format(columns=columns, table_name=table_name)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You extract tabular/list data from images. Return only valid JSON."},
            {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": image_url}]},
        ],
        max_tokens=4000,
    )
    raw = response.choices[0].message.content
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        out = json.loads(text)
        return out.get("table_data") or []
    except json.JSONDecodeError:
        return []


def schema_to_ddl(extraction: dict) -> str:
    """Convert extracted entities/relationships to SQLite DDL."""
    lines = []
    for ent in extraction.get("entities", []):
        name = ent.get("name", "Table").replace(" ", "_")
        attrs = ent.get("attributes", [])
        if not attrs:
            attrs = [{"name": "id", "type": "INTEGER"}]
        col_defs = []
        for a in attrs:
            col_name = a.get("name", "col").replace(" ", "_")
            t = (a.get("type") or "TEXT").upper()
            if t not in ("INTEGER", "REAL", "TEXT", "DATE", "BLOB"):
                t = "TEXT"
            col_defs.append(f'  "{col_name}" {t}')
        # Add PK if we have id
        if not any(c.get("name") == "id" for c in attrs):
            col_defs.insert(0, '  "id" INTEGER PRIMARY KEY AUTOINCREMENT')
        lines.append(f'CREATE TABLE IF NOT EXISTS "{name}" (\n' + ",\n".join(col_defs) + "\n);")
    for rel in extraction.get("relationships", []):
        fk_in = rel.get("fk_in")
        from_ent = rel.get("from", "").replace(" ", "_")
        to_ent = rel.get("to", "").replace(" ", "_")
        if fk_in:
            fk_table = fk_in.replace(" ", "_")
            lines.append(f'-- FK: {from_ent}.id -> {fk_table}.{from_ent.lower()}_id')
            lines.append(
                f'-- ALTER TABLE "{fk_table}" ADD COLUMN "{from_ent.lower()}_id" INTEGER REFERENCES "{from_ent}"(id);'
            )
    return "\n".join(lines)


def schema_to_er_mermaid(extraction: dict) -> str:
    """Convert extraction to Mermaid ER diagram."""
    lines = ["erDiagram"]
    for ent in extraction.get("entities", []):
        name = ent.get("name", "Table").replace(" ", "_")
        attrs = ent.get("attributes", [])[:5]
        lines.append(f"    {name} {{")
        for a in attrs:
            lines.append(f"        {a.get('type', 'TEXT')} {a.get('name', 'col').replace(' ', '_')}")
        lines.append("    }")
    for rel in extraction.get("relationships", []):
        from_ent = rel.get("from", "").replace(" ", "_")
        to_ent = rel.get("to", "").replace(" ", "_")
        rtype = rel.get("type", "one-to-many")
        if "many-to-many" in rtype:
            lines.append(f"    {from_ent} }}o--o{{ {to_ent} : \"\"")
        else:
            lines.append(f"    {from_ent} ||--o{{ {to_ent} : \"\"")
    return "\n".join(lines) if len(lines) > 1 else "erDiagram\n    PLACEHOLDER {}"
