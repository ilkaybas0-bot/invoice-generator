"""Local JSON-based persistence for the sender profile and document history."""

from __future__ import annotations

import base64
import io
import json
import uuid
import zipfile
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DOCS_DIR = DATA_DIR / "documents"
PROFILE_PATH = DATA_DIR / "profile.json"
HISTORY_PATH = DATA_DIR / "history.json"
CLIENTS_PATH = DATA_DIR / "clients.json"
ITEM_TEMPLATES_PATH = DATA_DIR / "item_templates.json"
RECURRING_PATH = DATA_DIR / "recurring_templates.json"
COUNTERS_PATH = DATA_DIR / "counters.json"


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)


_BINARY_FIELDS = ["logo_bytes", "signature_bytes"]


def save_profile(profile: dict) -> None:
    """Persist sender/company details (logo/signature images, base64-encoded) to disk."""
    _ensure_dirs()
    payload = dict(profile)
    for field_name in _BINARY_FIELDS:
        raw = payload.pop(field_name, None)
        payload[f"{field_name}_b64"] = base64.b64encode(raw).decode("ascii") if raw else None
    PROFILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_profile() -> dict | None:
    """Load a previously saved sender profile, or None if none exists."""
    if not PROFILE_PATH.exists():
        return None
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    for field_name in _BINARY_FIELDS:
        b64 = payload.pop(f"{field_name}_b64", None)
        payload[field_name] = base64.b64decode(b64) if b64 else None
    return payload


def clear_profile() -> None:
    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()


def _load_history_index() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def _save_history_index(records: list[dict]) -> None:
    HISTORY_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def save_document(pdf_bytes: bytes, metadata: dict) -> str:
    """Save a generated PDF and its metadata; return the new record id."""
    _ensure_dirs()
    doc_id = uuid.uuid4().hex[:12]
    file_path = DOCS_DIR / f"{doc_id}.pdf"
    file_path.write_bytes(pdf_bytes)

    records = _load_history_index()
    record = {"id": doc_id, "file": file_path.name, **metadata}
    records.insert(0, record)
    _save_history_index(records)
    return doc_id


def list_documents() -> list[dict]:
    """Return saved document metadata, most recent first."""
    return _load_history_index()


def read_document(doc_id: str) -> bytes | None:
    path = DOCS_DIR / f"{doc_id}.pdf"
    return path.read_bytes() if path.exists() else None


def delete_document(doc_id: str) -> None:
    records = _load_history_index()
    records = [r for r in records if r["id"] != doc_id]
    _save_history_index(records)
    path = DOCS_DIR / f"{doc_id}.pdf"
    if path.exists():
        path.unlink()


def update_document_status(doc_id: str, status: str) -> None:
    """Set the payment status ('unpaid', 'paid') on a saved document record."""
    records = _load_history_index()
    for r in records:
        if r["id"] == doc_id:
            r["status"] = status
            break
    _save_history_index(records)


# ---------------------------------------------------------- Address book --
def _load_clients() -> list[dict]:
    if not CLIENTS_PATH.exists():
        return []
    return json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))


def _save_clients(records: list[dict]) -> None:
    _ensure_dirs()
    CLIENTS_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def save_client(client: dict) -> str:
    """Save or update a client in the address book (matched by name+email); return its id."""
    records = _load_clients()
    key = (client.get("name", "").strip().lower(), client.get("email", "").strip().lower())
    for r in records:
        if (r.get("name", "").strip().lower(), r.get("email", "").strip().lower()) == key:
            r.update(client)
            _save_clients(records)
            return r["id"]

    client_id = uuid.uuid4().hex[:12]
    record = {"id": client_id, **client}
    records.append(record)
    _save_clients(records)
    return client_id


def list_clients() -> list[dict]:
    """Return saved clients, alphabetically by name."""
    return sorted(_load_clients(), key=lambda r: r.get("name", "").lower())


def delete_client(client_id: str) -> None:
    records = [r for r in _load_clients() if r["id"] != client_id]
    _save_clients(records)


# ------------------------------------------------------- Item templates ---
def _load_item_templates() -> list[dict]:
    if not ITEM_TEMPLATES_PATH.exists():
        return []
    return json.loads(ITEM_TEMPLATES_PATH.read_text(encoding="utf-8"))


def _save_item_templates(records: list[dict]) -> None:
    _ensure_dirs()
    ITEM_TEMPLATES_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def save_item_template(template: dict) -> str:
    """Save a reusable line-item template (description, quantity, unit_price)."""
    records = _load_item_templates()
    template_id = uuid.uuid4().hex[:12]
    record = {"id": template_id, **template}
    records.append(record)
    _save_item_templates(records)
    return template_id


def list_item_templates() -> list[dict]:
    """Return saved item templates, alphabetically by description."""
    return sorted(_load_item_templates(), key=lambda r: r.get("description", "").lower())


def delete_item_template(template_id: str) -> None:
    records = [r for r in _load_item_templates() if r["id"] != template_id]
    _save_item_templates(records)


# ------------------------------------------------------------- Export all --
def export_all_zip() -> bytes:
    """Bundle every saved PDF plus the profile/history/clients JSON into one ZIP."""
    _ensure_dirs()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for json_path in [PROFILE_PATH, HISTORY_PATH, CLIENTS_PATH, ITEM_TEMPLATES_PATH, RECURRING_PATH, COUNTERS_PATH]:
            if json_path.exists():
                zf.write(json_path, arcname=json_path.name)
        for pdf_path in DOCS_DIR.glob("*.pdf"):
            zf.write(pdf_path, arcname=f"documents/{pdf_path.name}")

        history = _load_history_index()
        if history:
            csv_lines = ["id,doc_type,doc_number,client_name,grand_total,currency,issue_date,created_at,file_name"]
            for r in history:
                csv_lines.append(",".join(str(r.get(k, "")).replace(",", ";") for k in [
                    "id", "doc_type", "doc_number", "client_name", "grand_total",
                    "currency", "issue_date", "created_at", "file_name",
                ]))
            zf.writestr("history_summary.csv", "\n".join(csv_lines))

    return buffer.getvalue()


# --------------------------------------------------- Recurring templates --
def _load_recurring() -> list[dict]:
    if not RECURRING_PATH.exists():
        return []
    return json.loads(RECURRING_PATH.read_text(encoding="utf-8"))


def _save_recurring(records: list[dict]) -> None:
    _ensure_dirs()
    RECURRING_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def save_recurring_template(template: dict) -> str:
    """Save a full invoice preset (client, items, tax, notes) for reuse each period."""
    records = _load_recurring()
    template_id = uuid.uuid4().hex[:12]
    record = {"id": template_id, **template}
    records.append(record)
    _save_recurring(records)
    return template_id


def list_recurring_templates() -> list[dict]:
    """Return saved recurring templates, alphabetically by name."""
    return sorted(_load_recurring(), key=lambda r: r.get("name", "").lower())


def delete_recurring_template(template_id: str) -> None:
    records = [r for r in _load_recurring() if r["id"] != template_id]
    _save_recurring(records)


# ---------------------------------------------------- Document numbering --
def _load_counters() -> dict:
    if not COUNTERS_PATH.exists():
        return {}
    return json.loads(COUNTERS_PATH.read_text(encoding="utf-8"))


def _save_counters(counters: dict) -> None:
    _ensure_dirs()
    COUNTERS_PATH.write_text(json.dumps(counters, ensure_ascii=False, indent=2), encoding="utf-8")


def peek_next_number(doc_type: str) -> int:
    """Return the sequence number that would be suggested next, without consuming it."""
    return _load_counters().get(doc_type, 0) + 1


def consume_next_number(doc_type: str) -> int:
    """Advance and persist the counter for doc_type; return the number just consumed."""
    counters = _load_counters()
    next_n = counters.get(doc_type, 0) + 1
    counters[doc_type] = next_n
    _save_counters(counters)
    return next_n


# ------------------------------------------------------- Restore from ZIP --
def import_zip(zip_bytes: bytes, overwrite_profile: bool = False) -> dict:
    """Restore data from a ZIP produced by export_all_zip().

    Existing local data is never deleted. Records are merged by id — only
    entries not already present locally are added. The profile is only
    overwritten if `overwrite_profile` is True or no local profile exists.
    Returns a summary of how many items were imported per category.
    """
    _ensure_dirs()
    summary = {"documents": 0, "clients": 0, "item_templates": 0, "recurring_templates": 0, "profile_applied": False}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())

        def read_json(name: str):
            if name not in names:
                return None
            return json.loads(zf.read(name).decode("utf-8"))

        # --- history + PDFs ---
        imported_history = read_json("history.json") or []
        if imported_history:
            existing = _load_history_index()
            existing_ids = {r["id"] for r in existing}
            for rec in imported_history:
                rid = rec.get("id")
                if not rid or rid in existing_ids:
                    continue
                pdf_name = f"documents/{rid}.pdf"
                if pdf_name in names:
                    (DOCS_DIR / f"{rid}.pdf").write_bytes(zf.read(pdf_name))
                existing.append(rec)
                existing_ids.add(rid)
                summary["documents"] += 1
            existing.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            _save_history_index(existing)

        # --- id-keyed lists: clients, item templates, recurring templates ---
        for json_name, loader, saver, key in [
            ("clients.json", _load_clients, _save_clients, "clients"),
            ("item_templates.json", _load_item_templates, _save_item_templates, "item_templates"),
            ("recurring_templates.json", _load_recurring, _save_recurring, "recurring_templates"),
        ]:
            imported = read_json(json_name) or []
            if not imported:
                continue
            existing = loader()
            existing_ids = {r["id"] for r in existing if "id" in r}
            added = 0
            for rec in imported:
                if rec.get("id") and rec["id"] not in existing_ids:
                    existing.append(rec)
                    existing_ids.add(rec["id"])
                    added += 1
            if added:
                saver(existing)
            summary[key] = added

        # --- profile (only if requested or nothing local yet) ---
        imported_profile = read_json("profile.json")
        if imported_profile is not None and (overwrite_profile or not PROFILE_PATH.exists()):
            PROFILE_PATH.write_text(json.dumps(imported_profile, ensure_ascii=False, indent=2), encoding="utf-8")
            summary["profile_applied"] = True

        # --- counters: never move a sequence backward ---
        imported_counters = read_json("counters.json") or {}
        if imported_counters:
            counters = _load_counters()
            for doc_type, value in imported_counters.items():
                counters[doc_type] = max(counters.get(doc_type, 0), value)
            _save_counters(counters)

    return summary
