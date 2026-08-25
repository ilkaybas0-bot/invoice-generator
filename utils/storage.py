"""Supabase-backed persistence for the sender profile and document history.

Function names and signatures intentionally mirror the earlier local-JSON
implementation so app.py did not need to change. Two Supabase pieces are
used: Postgres tables for structured records, and two Storage buckets
("assets" for the logo/signature, "documents" for generated PDFs).
"""

from __future__ import annotations

import base64
import io
import json
import os
import uuid
import zipfile
from functools import lru_cache

from supabase import create_client, Client

ASSETS_BUCKET = "assets"
DOCUMENTS_BUCKET = "documents"


@lru_cache(maxsize=1)
def _get_client() -> Client:
    """Build the Supabase client from Streamlit secrets, or env vars as a fallback."""
    url = key = None
    try:
        import streamlit as st
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        pass
    url = url or os.environ.get("SUPABASE_URL")
    key = key or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials not found. Set SUPABASE_URL and SUPABASE_KEY in "
            ".streamlit/secrets.toml (local) or the app's Secrets settings (Streamlit Cloud)."
        )
    return create_client(url, key)


def _guess_ext(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    return "bin"


def _content_type_for(ext: str) -> str:
    return {"png": "image/png", "jpg": "image/jpeg"}.get(ext, "application/octet-stream")


def _upload_asset(base_path: str, data: bytes) -> str:
    client = _get_client()
    ext = _guess_ext(data)
    full_path = f"{base_path}.{ext}"
    client.storage.from_(ASSETS_BUCKET).upload(
        full_path, data, {"content-type": _content_type_for(ext), "upsert": "true"},
    )
    return full_path


def _download_asset(path: str | None) -> bytes | None:
    if not path:
        return None
    try:
        return _get_client().storage.from_(ASSETS_BUCKET).download(path)
    except Exception:
        return None


# ---------------------------------------------------------------- Profile --
def save_profile(profile: dict) -> None:
    """Persist sender/company details (logo/signature uploaded to Storage)."""
    client = _get_client()
    row = {
        "id": 1,
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "address": profile.get("address", ""),
        "tax_number": profile.get("tax_number", ""),
    }
    logo_bytes = profile.get("logo_bytes")
    signature_bytes = profile.get("signature_bytes")
    if logo_bytes:
        row["logo_path"] = _upload_asset("profile/logo", logo_bytes)
    if signature_bytes:
        row["signature_path"] = _upload_asset("profile/signature", signature_bytes)
    client.table("profile").upsert(row).execute()


def load_profile() -> dict | None:
    """Load the saved sender profile, or None if none has been saved yet."""
    res = _get_client().table("profile").select("*").eq("id", 1).limit(1).execute()
    if not res.data:
        return None
    row = res.data[0]
    return {
        "name": row.get("name", ""),
        "email": row.get("email", ""),
        "address": row.get("address", ""),
        "tax_number": row.get("tax_number", ""),
        "logo_bytes": _download_asset(row.get("logo_path")),
        "signature_bytes": _download_asset(row.get("signature_path")),
    }


def clear_profile() -> None:
    _get_client().table("profile").delete().eq("id", 1).execute()


# --------------------------------------------------------- Document history --
def save_document(pdf_bytes: bytes, metadata: dict) -> str:
    """Save a generated PDF (to Storage) and its metadata (to Postgres); return its id."""
    client = _get_client()
    doc_id = uuid.uuid4().hex
    pdf_path = f"{doc_id}.pdf"
    client.storage.from_(DOCUMENTS_BUCKET).upload(
        pdf_path, pdf_bytes, {"content-type": "application/pdf", "upsert": "true"},
    )
    row = {
        "id": doc_id,
        "doc_type": metadata["doc_type"],
        "doc_number": metadata["doc_number"],
        "client_name": metadata.get("client_name", ""),
        "grand_total": metadata.get("grand_total", 0),
        "balance_due": metadata.get("balance_due", 0),
        "currency": metadata.get("currency", "₺"),
        "issue_date": metadata.get("issue_date", ""),
        "due_date_iso": metadata.get("due_date_iso"),
        "file_name": metadata.get("file_name", ""),
        "status": metadata.get("status", "unpaid"),
        "pdf_path": pdf_path,
    }
    if metadata.get("created_at"):
        row["created_at"] = metadata["created_at"]
    client.table("documents").insert(row).execute()
    return doc_id


def _normalize_created_at(value) -> str:
    """Render a Postgres timestamp back into the app's 'YYYY-MM-DD HH:MM' display format."""
    text = str(value or "")
    return text.replace("T", " ")[:16]


def list_documents() -> list[dict]:
    """Return saved document metadata, most recent first."""
    res = _get_client().table("documents").select("*").order("created_at", desc=True).execute()
    records = []
    for row in res.data:
        records.append({
            "id": row["id"],
            "doc_type": row.get("doc_type", ""),
            "doc_number": row.get("doc_number", ""),
            "client_name": row.get("client_name", ""),
            "grand_total": float(row.get("grand_total") or 0),
            "balance_due": float(row.get("balance_due") or 0),
            "currency": row.get("currency", "₺"),
            "issue_date": row.get("issue_date", ""),
            "due_date_iso": row.get("due_date_iso"),
            "created_at": _normalize_created_at(row.get("created_at")),
            "file_name": row.get("file_name", ""),
            "status": row.get("status", "unpaid"),
        })
    return records


def read_document(doc_id: str) -> bytes | None:
    try:
        return _get_client().storage.from_(DOCUMENTS_BUCKET).download(f"{doc_id}.pdf")
    except Exception:
        return None


def get_document_url(doc_id: str) -> str:
    """Return the public Storage URL for a generated PDF (bucket is public)."""
    return _get_client().storage.from_(DOCUMENTS_BUCKET).get_public_url(f"{doc_id}.pdf")


def delete_document(doc_id: str) -> None:
    client = _get_client()
    client.table("documents").delete().eq("id", doc_id).execute()
    try:
        client.storage.from_(DOCUMENTS_BUCKET).remove([f"{doc_id}.pdf"])
    except Exception:
        pass


def update_document_status(doc_id: str, status: str) -> None:
    """Set the payment status ('unpaid', 'paid') on a saved document record."""
    _get_client().table("documents").update({"status": status}).eq("id", doc_id).execute()


# ---------------------------------------------------------- Address book --
def save_client(client_data: dict) -> str:
    """Save or update a client in the address book (matched by name+email); return its id."""
    client = _get_client()
    name = client_data.get("name", "").strip()
    email = client_data.get("email", "").strip()
    key = (name.lower(), email.lower())

    existing = client.table("clients").select("*").execute().data
    for row in existing:
        if (row.get("name", "").strip().lower(), row.get("email", "").strip().lower()) == key:
            client.table("clients").update({
                "name": name, "company": client_data.get("company", "").strip(),
                "email": email, "address": client_data.get("address", "").strip(),
            }).eq("id", row["id"]).execute()
            return row["id"]

    res = client.table("clients").insert({
        "name": name, "company": client_data.get("company", "").strip(),
        "email": email, "address": client_data.get("address", "").strip(),
    }).execute()
    return res.data[0]["id"]


def list_clients() -> list[dict]:
    """Return saved clients, alphabetically by name."""
    res = _get_client().table("clients").select("*").order("name").execute()
    return res.data


def delete_client(client_id: str) -> None:
    _get_client().table("clients").delete().eq("id", client_id).execute()


# ------------------------------------------------------- Item templates ---
def save_item_template(template: dict) -> str:
    """Save a reusable line-item template (description, quantity, unit_price)."""
    res = _get_client().table("item_templates").insert({
        "description": template.get("description", ""),
        "quantity": template.get("quantity", 1),
        "unit_price": template.get("unit_price", 0),
    }).execute()
    return res.data[0]["id"]


def list_item_templates() -> list[dict]:
    """Return saved item templates, alphabetically by description."""
    res = _get_client().table("item_templates").select("*").order("description").execute()
    return res.data


def delete_item_template(template_id: str) -> None:
    _get_client().table("item_templates").delete().eq("id", template_id).execute()


# --------------------------------------------------- Recurring templates --
def save_recurring_template(template: dict) -> str:
    """Save a full invoice preset (client, items, tax, notes) for reuse each period."""
    row = dict(template)
    row.setdefault("items", [])
    res = _get_client().table("recurring_templates").insert(row).execute()
    return res.data[0]["id"]


def list_recurring_templates() -> list[dict]:
    """Return saved recurring templates, alphabetically by name."""
    res = _get_client().table("recurring_templates").select("*").order("name").execute()
    return res.data


def delete_recurring_template(template_id: str) -> None:
    _get_client().table("recurring_templates").delete().eq("id", template_id).execute()


# ---------------------------------------------------- Document numbering --
def _get_counter(doc_type: str) -> int:
    res = _get_client().table("counters").select("value").eq("doc_type", doc_type).execute()
    return res.data[0]["value"] if res.data else 0


def peek_next_number(doc_type: str) -> int:
    """Return the sequence number that would be suggested next, without consuming it."""
    return _get_counter(doc_type) + 1


def consume_next_number(doc_type: str) -> int:
    """Advance and persist the counter for doc_type; return the number just consumed."""
    next_n = _get_counter(doc_type) + 1
    _get_client().table("counters").upsert({"doc_type": doc_type, "value": next_n}).execute()
    return next_n


# ------------------------------------------------------------- Export all --
def export_all_zip() -> bytes:
    """Bundle every saved PDF plus the profile/history/clients data into one ZIP."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        profile = load_profile()
        if profile:
            payload = {
                "name": profile.get("name", ""), "email": profile.get("email", ""),
                "address": profile.get("address", ""), "tax_number": profile.get("tax_number", ""),
            }
            logo_bytes = profile.get("logo_bytes")
            signature_bytes = profile.get("signature_bytes")
            payload["logo_bytes_b64"] = base64.b64encode(logo_bytes).decode("ascii") if logo_bytes else None
            payload["signature_bytes_b64"] = base64.b64encode(signature_bytes).decode("ascii") if signature_bytes else None
            zf.writestr("profile.json", json.dumps(payload, ensure_ascii=False, indent=2))

        history = list_documents()
        if history:
            zf.writestr("history.json", json.dumps(history, ensure_ascii=False, indent=2, default=str))
            for rec in history:
                pdf_bytes = read_document(rec["id"])
                if pdf_bytes:
                    zf.writestr(f"documents/{rec['id']}.pdf", pdf_bytes)
            csv_lines = ["id,doc_type,doc_number,client_name,grand_total,currency,issue_date,created_at,file_name"]
            for r in history:
                csv_lines.append(",".join(str(r.get(k, "")).replace(",", ";") for k in [
                    "id", "doc_type", "doc_number", "client_name", "grand_total",
                    "currency", "issue_date", "created_at", "file_name",
                ]))
            zf.writestr("history_summary.csv", "\n".join(csv_lines))

        clients = list_clients()
        if clients:
            zf.writestr("clients.json", json.dumps(clients, ensure_ascii=False, indent=2, default=str))

        templates = list_item_templates()
        if templates:
            zf.writestr("item_templates.json", json.dumps(templates, ensure_ascii=False, indent=2, default=str))

        recurring = list_recurring_templates()
        if recurring:
            zf.writestr("recurring_templates.json", json.dumps(recurring, ensure_ascii=False, indent=2, default=str))

        counters_rows = _get_client().table("counters").select("*").execute().data
        if counters_rows:
            counters_dict = {r["doc_type"]: r["value"] for r in counters_rows}
            zf.writestr("counters.json", json.dumps(counters_dict, ensure_ascii=False, indent=2))

    return buffer.getvalue()


# ------------------------------------------------------- Restore from ZIP --
def import_zip(zip_bytes: bytes, overwrite_profile: bool = False) -> dict:
    """Restore data from a ZIP produced by export_all_zip() (this version or the
    earlier local-file version). Existing data is never deleted — only records
    not already present (by id) are added. The profile is only overwritten if
    `overwrite_profile` is True or nothing is saved yet.
    """
    client = _get_client()
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
            existing_ids = {r["id"] for r in list_documents()}
            for rec in imported_history:
                rid = rec.get("id")
                if not rid or rid in existing_ids:
                    continue
                pdf_name = f"documents/{rid}.pdf"
                pdf_path = None
                if pdf_name in names:
                    pdf_bytes = zf.read(pdf_name)
                    pdf_path = f"{rid}.pdf"
                    client.storage.from_(DOCUMENTS_BUCKET).upload(
                        pdf_path, pdf_bytes, {"content-type": "application/pdf", "upsert": "true"},
                    )
                row = {
                    "id": rid,
                    "doc_type": rec.get("doc_type", "Invoice"),
                    "doc_number": rec.get("doc_number", ""),
                    "client_name": rec.get("client_name", ""),
                    "grand_total": rec.get("grand_total", 0),
                    "balance_due": rec.get("balance_due", 0),
                    "currency": rec.get("currency", "₺"),
                    "issue_date": rec.get("issue_date", ""),
                    "due_date_iso": rec.get("due_date_iso"),
                    "file_name": rec.get("file_name", ""),
                    "status": rec.get("status", "unpaid"),
                    "pdf_path": pdf_path,
                }
                if rec.get("created_at"):
                    row["created_at"] = rec["created_at"]
                client.table("documents").insert(row).execute()
                existing_ids.add(rid)
                summary["documents"] += 1

        # --- id-keyed lists: clients, item templates, recurring templates ---
        for json_name, table_name, key in [
            ("clients.json", "clients", "clients"),
            ("item_templates.json", "item_templates", "item_templates"),
            ("recurring_templates.json", "recurring_templates", "recurring_templates"),
        ]:
            imported = read_json(json_name) or []
            if not imported:
                continue
            existing_ids = {r["id"] for r in client.table(table_name).select("id").execute().data}
            added = 0
            for rec in imported:
                if rec.get("id") and rec["id"] not in existing_ids:
                    client.table(table_name).insert(rec).execute()
                    existing_ids.add(rec["id"])
                    added += 1
            summary[key] = added

        # --- profile (only if requested or nothing local yet) ---
        imported_profile = read_json("profile.json")
        if imported_profile is not None and (overwrite_profile or load_profile() is None):
            row = {
                "id": 1,
                "name": imported_profile.get("name", ""),
                "email": imported_profile.get("email", ""),
                "address": imported_profile.get("address", ""),
                "tax_number": imported_profile.get("tax_number", ""),
            }
            logo_b64 = imported_profile.get("logo_bytes_b64") or imported_profile.get("logo_b64")
            signature_b64 = imported_profile.get("signature_bytes_b64")
            if logo_b64:
                row["logo_path"] = _upload_asset("profile/logo", base64.b64decode(logo_b64))
            if signature_b64:
                row["signature_path"] = _upload_asset("profile/signature", base64.b64decode(signature_b64))
            client.table("profile").upsert(row).execute()
            summary["profile_applied"] = True

        # --- counters: never move a sequence backward ---
        imported_counters = read_json("counters.json") or {}
        if imported_counters:
            existing_counters = {r["doc_type"]: r["value"] for r in client.table("counters").select("*").execute().data}
            for doc_type, value in imported_counters.items():
                new_val = max(existing_counters.get(doc_type, 0), value)
                client.table("counters").upsert({"doc_type": doc_type, "value": new_val}).execute()

    return summary
