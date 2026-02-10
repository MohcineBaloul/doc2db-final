"""Quick test: create project, upload PDF, extract (with fallback table_data), apply, preview."""
import json
import os
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8001"
PDF = os.path.join(os.path.dirname(__file__), "..", "book_list.pdf")
if not os.path.isfile(PDF):
    PDF = "book_list.pdf"

def post_json(path, body, params=None):
    data = json.dumps(body).encode()
    q = "?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else ""
    req = urllib.request.Request(f"{BASE}{path}{q}", data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

def upload_file(pid):
    boundary = "----WebKitFormBoundary7MA4YWxk"
    with open(PDF, "rb") as f:
        raw = f.read()
    b = boundary.encode()
    body = b"--" + b + b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"book_list.pdf\"\r\nContent-Type: application/pdf\r\n\r\n" + raw + b"\r\n--" + b + b"--\r\n"
    req = urllib.request.Request(f"{BASE}/api/upload?project_id={pid}", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def main():
    proj = post_json("/api/projects", {"name": "Debug PDF"})
    pid = proj["project_id"]
    print("Project ID:", pid)

    up = upload_file(pid)
    upload_path = up["path"]
    print("Upload path:", upload_path)

    data = post_json("/api/extract", {"upload_path": upload_path}, {"project_id": pid})
    print("Extraction ID:", data.get("extraction_id"))
    print("Content saved (table_data):", data.get("table_data", []))

    apply_j = post_json("/api/apply-schema", {"extraction_id": data["extraction_id"]}, {"project_id": pid})
    print("Rows inserted:", apply_j.get("rows_inserted", "?"))

    req = urllib.request.Request(f"{BASE}/api/preview/{pid}")
    with urllib.request.urlopen(req, timeout=10) as r:
        prev_j = json.loads(r.read().decode())
    for t in prev_j.get("tables", []):
        print("Preview table", t.get("name"), "rows:", len(t.get("rows", [])))

if __name__ == "__main__":
    main()
