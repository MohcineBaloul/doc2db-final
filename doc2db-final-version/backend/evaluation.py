"""
Evaluation / research component stubs for Doc2DB-Gen.
- Extraction accuracy (entity/relationship recall vs ground truth).
- Normalization quality (NF checks, redundancy).
- Queryability vs manual schemas.
"""


def extraction_accuracy(extracted: dict, ground_truth: dict) -> dict:
    """
    Compare extracted entities/relationships to ground truth.
    Returns precision, recall, F1 for entities and relationships.
    """
    e_pred = {e.get("name", "").lower() for e in extracted.get("entities", [])}
    e_true = {e.get("name", "").lower() for e in ground_truth.get("entities", [])}
    tp_e = len(e_pred & e_true)
    prec_e = tp_e / len(e_pred) if e_pred else 0.0
    rec_e = tp_e / len(e_true) if e_true else 0.0
    f1_e = 2 * prec_e * rec_e / (prec_e + rec_e) if (prec_e + rec_e) else 0.0

    def rel_key(r):
        return (r.get("from", "").lower(), r.get("to", "").lower())

    r_pred = {rel_key(r) for r in extracted.get("relationships", [])}
    r_true = {rel_key(r) for r in ground_truth.get("relationships", [])}
    tp_r = len(r_pred & r_true)
    prec_r = tp_r / len(r_pred) if r_pred else 0.0
    rec_r = tp_r / len(r_true) if r_true else 0.0
    f1_r = 2 * prec_r * rec_r / (prec_r + rec_r) if (prec_r + rec_r) else 0.0

    return {
        "entities": {"precision": prec_e, "recall": rec_e, "f1": f1_e},
        "relationships": {"precision": prec_r, "recall": rec_r, "f1": f1_r},
    }


def normalization_quality(ddl: str) -> dict:
    """
    Heuristic normalization quality: table count, has primary key, FK mentions.
    """
    lines = [s.strip() for s in ddl.upper().split("\n") if s.strip() and not s.strip().startswith("--")]
    create_count = sum(1 for l in lines if "CREATE TABLE" in l)
    pk_count = sum(1 for l in lines if "PRIMARY KEY" in l or "AUTOINCREMENT" in l)
    fk_mentions = sum(1 for l in lines if "REFERENCES" in l or "FK" in l)
    return {
        "table_count": create_count,
        "tables_with_pk": pk_count,
        "fk_mentions": fk_mentions,
        "score_note": "Higher FK and PK usage suggests better normalization.",
    }


def queryability_score(schema_tables: list, sample_queries: list[str]) -> dict:
    """
    Placeholder: compare queryability of generated schema (e.g. can we run sample queries?).
    """
    return {
        "tables_available": len(schema_tables),
        "sample_queries_count": len(sample_queries),
        "note": "Run sample SELECTs against DB and measure success rate for full metric.",
    }
