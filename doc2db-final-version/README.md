# Doc2DB-Gen

**Multimodal LLM system that converts PDFs, tables & images into normalized databases.**

- **Upload**: PDFs, spreadsheets (.xlsx, .csv), images (.png, .jpg).
- **Extract**: Vision-language LLM extracts entities and relationships.
- **Schema**: System proposes an ER diagram (Mermaid) and SQL DDL.
- **DB**: Data/schema applied to a SQLite DB; preview in the UI.

---

## 1. Prepare & setup

### Prerequisites

- **Python 3.10+** (3.11 or 3.12 recommended)
- **Docker** (optional, for PostgreSQL) — [Install Docker](https://docs.docker.com/get-docker/)
- **OpenAI API key** — [Create one at platform.openai.com](https://platform.openai.com/api-keys)

### Project layout

Use the project folder as the working root (e.g. `c:\Users\Andrey\Desktop\db_llm_project` or your clone path).

### Environment file

1. Go to the **`backend`** folder.
2. Copy the example env and edit:
   - **Windows (PowerShell):** `Copy-Item .env.example .env`
   - **macOS/Linux:** `cp .env.example .env`
3. Open **`backend\.env`** and set at least:
   ```env
   OPENAI_API_KEY=sk-proj-your-actual-key-here
   ```
4. **Optional (PostgreSQL):** If you use Docker for the DB, add:
   ```env
   DATABASE_URL=postgresql+asyncpg://doc2db:doc2db_secret@localhost:5432/doc2db
   ```

Do not commit `.env`; it is in `.gitignore`.

---

## 2. Install dependencies

From the **project root** (or from `backend`):

**Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you use **PostgreSQL** (Docker), the driver `asyncpg` is already in `requirements.txt`. If you added it later, run once:
```powershell
pip install asyncpg
```

---

## 3. Start Docker image (PostgreSQL, optional)

By default the app uses **SQLite** (`backend/doc2db.db`). To use **PostgreSQL** in Docker:

1. From the **project root**:
   ```powershell
   docker compose up -d
   ```
2. Ensure **`backend/.env`** contains:
   ```env
   DATABASE_URL=postgresql+asyncpg://doc2db:doc2db_secret@localhost:5432/doc2db
   ```
3. Start the server (see below); it will create tables in PostgreSQL on first run.

**Useful commands:**
- Check container: `docker ps --filter "name=doc2db"`
- Stop DB: `docker compose down` (from project root)
- Data is stored in the `doc2db_pgdata` volume.

---

## 4. Start the server

From the **`backend`** folder, with the venv **activated**:

**Windows:**
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**macOS / Linux:**
```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

If port **8000** is already in use, use another port (e.g. **8001**):
```powershell
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

Then open the app at **http://localhost:8000** (or **http://localhost:8001**).

**Optional – start script (Windows):**  
From `backend`, run `.\start_server.ps1` to try freeing port 8000 and start a single process.

**Check server:**  
- **http://localhost:8000/api/health** (or your port) — should show `"status": "ok"`, `"llm_configured": true`, `"db_ok": true` when configured correctly.

---

## 5. How to use the app

1. Open the app in your browser: **http://localhost:8000** (or the port you used).

2. **Create a project**  
   Click **“New project”**. A project ID appears (e.g. Project #1).

3. **Upload a file**  
   - Click **“Choose file”** and select a PDF, image (.png, .jpg), or spreadsheet (.xlsx, .csv, .txt).  
   - Click **“Upload file”**.  
   - Wait for “Uploaded: …” to appear.

4. **Extract schema (LLM)**  
   - Click **“Extract entities & relationships”**.  
   - Wait 30–60 seconds while the LLM analyzes the document.  
   - The **ER diagram** and **SQL DDL** appear in the tabs.

5. **Apply schema to DB**  
   - Click **“Apply schema to DB”**.  
   - The generated tables are created in the project database.

6. **Preview DB**  
   - Click **“Preview DB”** to see the created tables and columns (and sample rows if any).

**Tips:**
- Use the same browser tab/origin as the server (e.g. **http://localhost:8000**) to avoid “Failed to fetch”.
- If extract fails, check **http://localhost:8000/api/health** for `llm_configured` and `db_ok`.
- API docs: **http://localhost:8000/docs**.

---

## Setting OPENAI_API_KEY (detail)

The app reads `OPENAI_API_KEY` from **`backend/.env`** (or from the environment). The config loads **`backend/.env`** by path, so the server finds it even if you start uvicorn from another directory.

- **In `.env`:** one line, no spaces around `=`, no quotes:  
  `OPENAI_API_KEY=sk-proj-xxxxxxxx...`
- **Check:** open **http://localhost:8000/api/health** — response should have `"llm_configured": true`.

---

## Project layout

```
db_llm_project/
├── backend/
│   ├── main.py          # FastAPI app, upload/extract/apply/preview
│   ├── llm_client.py    # OpenAI vision + schema extraction, DDL/Mermaid
│   ├── schema_engine.py # Run DDL, insert data, preview
│   ├── db.py            # Metadata DB (projects, extractions)
│   ├── models.py        # Project, Extraction
│   ├── config.py        # Settings from .env
│   ├── evaluation.py    # Stubs: extraction accuracy, normalization, queryability
│   ├── requirements.txt
│   ├── start_server.ps1 # Optional: start server (Windows)
│   ├── data/            # project_<id>.db per project (created at runtime)
│   └── uploads/         # Uploaded files
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── docker-compose.yml   # PostgreSQL service
├── .env.example
└── README.md
```

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/projects` | Create project, returns `project_id` |
| POST | `/api/upload?project_id=` | Upload file (multipart) |
| POST | `/api/extract?project_id=` | Body `{ "upload_path": "..." }` → ER + DDL |
| POST | `/api/apply-schema?project_id=` | Body `{ "extraction_id": 1 }` → run DDL |
| GET | `/api/preview/{project_id}` | List tables and sample rows |
| GET | `/api/health` | Status, LLM and DB config check |

---

## Evaluation / research

- **Extraction accuracy**: `evaluation.extraction_accuracy(extracted, ground_truth)` — entity/relationship precision, recall, F1.
- **Normalization quality**: `evaluation.normalization_quality(ddl)` — table count, PK/FK usage.
- **Queryability**: `evaluation.queryability_score(tables, sample_queries)` — stub for comparing queryability vs manual schemas.

Run your own benchmarks by loading extractions and optional ground truth, then calling these functions.

---

## License

MIT.
