"""Automated PDF Invoice & Proposal Generator — Streamlit app."""

from __future__ import annotations

import base64
import datetime as dt
import html as html_lib
import urllib.parse

import pandas as pd
import streamlit as st

from utils.pdf_builder import (
    PartyDetails,
    ClientDetails,
    LineItem,
    DocumentData,
    build_pdf,
    format_money,
    THEMES,
)
from utils.i18n import t, DOC_TYPE_KEYS
from utils import storage
from utils.emailer import SmtpConfig, send_email_with_attachment

st.set_page_config(
    page_title="Invoice & Proposal Generator",
    page_icon="🧾",
    layout="wide",
)

# ------------------------------------------------------------------ Theme --
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea, select {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 3rem;
    max-width: 1180px;
}

/* Brand header */
.brand-header { display: flex; align-items: center; gap: 14px; margin-bottom: 4px; }
.brand-mark {
    width: 44px; height: 44px; border-radius: 11px;
    background: linear-gradient(135deg, #2563EB, #1D4ED8);
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; box-shadow: 0 4px 14px rgba(37,99,235,0.28);
    flex-shrink: 0;
}
.brand-title { font-size: 1.55rem; font-weight: 800; color: #0F172A; letter-spacing: -0.02em; line-height: 1.15; }
.brand-subtitle { color: #64748B; font-size: 0.92rem; margin-top: 1px; }

/* Sidebar */
[data-testid="stSidebar"] { background: #F8FAFC; border-right: 1px solid #E2E8F0; }
[data-testid="stSidebar"] .stTitle, [data-testid="stSidebar"] h1 { font-weight: 700; }

/* Buttons */
.stButton > button, .stDownloadButton > button {
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: transform 120ms ease, box-shadow 120ms ease !important;
    border: 1px solid #E2E8F0;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(15,23,42,0.08);
}
.stButton > button[kind="primary"] {
    box-shadow: 0 2px 8px rgba(37,99,235,0.25);
}

/* Metric cards */
[data-testid="stMetric"] {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 14px 16px 10px 16px;
}
[data-testid="stMetricLabel"] { font-weight: 500; }

/* Bordered containers -> soft cards */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border-color: #E2E8F0 !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid #E2E8F0; }
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 10px 22px;
    font-weight: 600;
    color: #64748B;
}
.stTabs [aria-selected="true"] { color: #2563EB !important; }

/* Section captions */
.section-eyebrow {
    text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.72rem;
    font-weight: 700; color: #94A3B8; margin-bottom: 2px;
}

hr { margin: 1.6rem 0 !important; }

/* Hide the Streamlit dev-tool chrome so this reads as a real product */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
.stAppDeployButton { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }

/* Consistent radius + focus ring across every input-like control */
input, textarea,
[data-baseweb="select"] > div,
[data-baseweb="input"] > div,
[data-testid="stFileUploaderDropzone"] {
    border-radius: 8px !important;
}
input:focus, textarea:focus,
[data-baseweb="select"] > div:focus-within,
[data-baseweb="input"] > div:focus-within {
    box-shadow: 0 0 0 3px rgba(37,99,235,0.15) !important;
    border-color: #2563EB !important;
}

/* Data editor / dataframe frame */
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #E2E8F0;
}

/* Softer, left-accented alert boxes instead of full-color fills */
[data-testid="stAlert"] {
    border-radius: 10px;
    border: 1px solid transparent;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
}

/* Tab underline in brand color */
.stTabs [data-baseweb="tab-highlight"] {
    background-color: #2563EB !important;
    height: 3px;
    border-radius: 3px 3px 0 0;
}

/* Tabular figures for money so columns of numbers line up */
[data-testid="stMetricValue"] {
    font-variant-numeric: tabular-nums;
    font-weight: 700;
    letter-spacing: -0.01em;
}

/* Status / overdue badges */
.badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 999px;
    font-size: 0.76rem; font-weight: 600; line-height: 1.6;
}
.badge-overdue { background: #FEF2F2; color: #DC2626; border: 1px solid #FECACA; }
.badge-paid { background: #F0FDF4; color: #16A34A; border: 1px solid #BBF7D0; }
.badge-unpaid { background: #F8FAFC; color: #64748B; border: 1px solid #E2E8F0; }

.doc-title { font-weight: 600; font-size: 0.95rem; color: #0F172A; }
.doc-sub { color: #64748B; font-size: 0.82rem; margin-top: 1px; }
</style>
""", unsafe_allow_html=True)

EMPTY_ITEMS = pd.DataFrame(
    [{"Description": "", "Quantity": 1, "Unit Price": 0.0}]
)

if "items_df" not in st.session_state:
    st.session_state.items_df = EMPTY_ITEMS.copy()
if "lang" not in st.session_state:
    st.session_state.lang = "en"
if "profile_loaded" not in st.session_state:
    saved = storage.load_profile()
    st.session_state.profile = saved or {}
    st.session_state.profile_loaded = True
if "tax_percent_val" not in st.session_state:
    st.session_state.tax_percent_val = 0.0
for key in ["client_name_val", "client_company_val", "client_email_val", "client_address_val"]:
    st.session_state.setdefault(key, "")
st.session_state.setdefault("currency_val", "₺")
st.session_state.setdefault("theme_val", "blue")
st.session_state.setdefault("discount_val", 0.0)
st.session_state.setdefault("advance_val", 0.0)
st.session_state.setdefault("notes_val", "")
st.session_state.setdefault("tax_inclusive_val", False)
st.session_state.setdefault("doctype_val", "Invoice")
if "last_pdf" not in st.session_state:
    st.session_state.last_pdf = None  # dict: bytes, file_name, client_email, doc_type, doc_number

TR_MONTHS = {
    1: "Oca", 2: "Şub", 3: "Mar", 4: "Nis", 5: "May", 6: "Haz",
    7: "Tem", 8: "Ağu", 9: "Eyl", 10: "Eki", 11: "Kas", 12: "Ara",
}
THEME_KEYS = {"blue": "theme_blue", "green": "theme_green", "purple": "theme_purple",
              "navy": "theme_navy", "slate": "theme_slate"}
VAT_PRESETS = [1, 10, 20]


def format_date(d: dt.date, lang: str) -> str:
    if lang == "tr":
        return f"{d.day:02d} {TR_MONTHS[d.month]} {d.year}"
    return d.strftime("%b %d, %Y")


def apply_client(record: dict) -> None:
    st.session_state.client_name_val = record.get("name", "")
    st.session_state.client_company_val = record.get("company", "")
    st.session_state.client_email_val = record.get("email", "")
    st.session_state.client_address_val = record.get("address", "")


def apply_recurring(tpl: dict) -> None:
    apply_client({
        "name": tpl.get("client_name", ""), "company": tpl.get("client_company", ""),
        "email": tpl.get("client_email", ""), "address": tpl.get("client_address", ""),
    })
    st.session_state.doctype_val = tpl.get("doc_type", "Invoice")
    st.session_state.currency_val = tpl.get("currency", "₺")
    st.session_state.theme_val = tpl.get("theme", "blue")
    st.session_state.tax_percent_val = float(tpl.get("tax_percent", 0.0))
    st.session_state.tax_inclusive_val = bool(tpl.get("tax_inclusive", False))
    st.session_state.discount_val = float(tpl.get("discount_amount", 0.0))
    st.session_state.advance_val = float(tpl.get("advance_paid", 0.0))
    st.session_state.notes_val = tpl.get("notes", "")
    items = tpl.get("items") or [{"Description": "", "Quantity": 1, "Unit Price": 0.0}]
    st.session_state.items_df = pd.DataFrame(items)


profile = st.session_state.profile

# Apply any pending client/recurring-template selection BEFORE the widgets
# they affect are instantiated below (Streamlit forbids writing to a keyed
# widget's session_state value after that widget has already rendered).
_pending_client = st.session_state.get("client_picker")
if _pending_client and _pending_client != "__none__" and st.session_state.get("_last_loaded_client") != _pending_client:
    _match = next((c for c in storage.list_clients() if c["id"] == _pending_client), None)
    if _match:
        apply_client(_match)
        st.session_state["_last_loaded_client"] = _pending_client

_pending_recurring = st.session_state.get("recurring_picker")
if _pending_recurring and _pending_recurring != "__none__" and st.session_state.get("_last_loaded_recurring") != _pending_recurring:
    _match = next((r for r in storage.list_recurring_templates() if r["id"] == _pending_recurring), None)
    if _match:
        apply_recurring(_match)
        st.session_state["_last_loaded_recurring"] = _pending_recurring
        st.session_state["_show_recurring_loaded_msg"] = True

# ---------------------------------------------------------------- Sidebar --
with st.sidebar:
    lang_choice = st.selectbox(
        "🌐 Language / Dil",
        options=["en", "tr"],
        format_func=lambda code: "English" if code == "en" else "Türkçe",
        index=["en", "tr"].index(st.session_state.lang),
    )
    st.session_state.lang = lang_choice
    lang = st.session_state.lang

    st.markdown(f"""
    <div class="brand-header">
        <div class="brand-mark">🧾</div>
        <div>
            <div class="brand-title">{t(lang, "app_title")}</div>
        </div>
    </div>
    <div class="brand-subtitle" style="margin-bottom:18px;">{t(lang, "app_subtitle")}</div>
    """, unsafe_allow_html=True)

    st.markdown(f'<div class="section-eyebrow">{t(lang, "sender_section")}</div>', unsafe_allow_html=True)
    with st.container(border=True):
        sender_name = st.text_input(t(lang, "sender_name"), value=profile.get("name", ""))
        sender_email = st.text_input(t(lang, "sender_email"), value=profile.get("email", ""))
        sender_address = st.text_area(t(lang, "sender_address"), value=profile.get("address", ""), height=70)
        sender_tax = st.text_input(t(lang, "sender_tax"), value=profile.get("tax_number", ""))
        sender_logo = st.file_uploader(t(lang, "sender_logo"), type=["png", "jpg", "jpeg"])
        saved_logo_bytes = profile.get("logo_bytes")
        sender_signature = st.file_uploader(t(lang, "signature_upload"), type=["png", "jpg", "jpeg"])
        saved_signature_bytes = profile.get("signature_bytes")

        pcol1, pcol2 = st.columns(2)
        with pcol1:
            if st.button(t(lang, "save_profile"), use_container_width=True):
                storage.save_profile({
                    "name": sender_name,
                    "email": sender_email,
                    "address": sender_address,
                    "tax_number": sender_tax,
                    "logo_bytes": sender_logo.getvalue() if sender_logo is not None else saved_logo_bytes,
                    "signature_bytes": sender_signature.getvalue() if sender_signature is not None else saved_signature_bytes,
                })
                st.success(t(lang, "profile_saved"))
        with pcol2:
            if st.button(t(lang, "clear_profile"), use_container_width=True):
                storage.clear_profile()
                st.session_state.profile = {}
                st.success(t(lang, "profile_cleared"))
                st.rerun()

# ----------------------------------------------------------------- Main ---
lang = st.session_state.lang

tab_new, tab_dashboard, tab_history, tab_records = st.tabs([
    f"📝 {t(lang, 'tab_new')}", f"📊 {t(lang, 'tab_dashboard')}",
    f"📚 {t(lang, 'tab_history')}", f"📇 {t(lang, 'tab_records')}",
])

# ============================================================= TAB: NEW ===
with tab_new:
    st.markdown(f'<div class="section-eyebrow">{t(lang, "doc_settings")}</div>', unsafe_allow_html=True)
    with st.container(border=True):
        s1, s2, s3 = st.columns(3)
        with s1:
            doc_type = st.radio(
                t(lang, "document_type"), options=["Invoice", "Proposal"],
                format_func=lambda v: t(lang, DOC_TYPE_KEYS[v]), horizontal=True, key="doctype_val",
            )
        with s2:
            currency = st.selectbox(t(lang, "currency"), ["₺", "$", "€", "£"], key="currency_val")
        with s3:
            theme_choice = st.selectbox(
                t(lang, "theme_color"), options=list(THEMES.keys()),
                format_func=lambda k: t(lang, THEME_KEYS[k]), key="theme_val",
            )
        d1, d2, d3 = st.columns(3)
        with d1:
            suggested_number = f"{doc_type[:3].upper()}-{storage.peek_next_number(doc_type):04d}"
            doc_number = st.text_input(
                t(lang, "doc_number", doc_type=t(lang, DOC_TYPE_KEYS[doc_type])),
                value=suggested_number,
                help=t(lang, "doc_number_help"),
            )
        with d2:
            issue_date = st.date_input(t(lang, "issue_date"), value=dt.date.today())
        with d3:
            due_date = st.date_input(t(lang, "due_date"), value=dt.date.today() + dt.timedelta(days=14))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="section-eyebrow">{t(lang, "client_details")}</div>', unsafe_allow_html=True)
        with st.container(border=True):
            if st.session_state.pop("_show_recurring_loaded_msg", False):
                st.success(t(lang, "recurring_loaded"))

            recurring_templates = storage.list_recurring_templates()
            if recurring_templates:
                rec_options = ["__none__"] + [r["id"] for r in recurring_templates]
                rec_labels = {r["id"]: r.get("name", "?") for r in recurring_templates}
                rec_labels["__none__"] = t(lang, "load_recurring_placeholder")
                st.selectbox(
                    t(lang, "load_recurring"), options=rec_options,
                    format_func=lambda rid: rec_labels[rid], key="recurring_picker",
                )

            clients = storage.list_clients()
            if clients:
                options = ["__none__"] + [c["id"] for c in clients]
                labels = {c["id"]: f"{c['name']} ({c.get('company', '')})" if c.get("company") else c["name"] for c in clients}
                labels["__none__"] = t(lang, "load_client_placeholder")
                st.selectbox(
                    t(lang, "load_client"), options=options,
                    format_func=lambda cid: labels[cid], key="client_picker",
                )

            client_name = st.text_input(t(lang, "client_name"), key="client_name_val")
            client_company = st.text_input(t(lang, "client_company"), key="client_company_val")
            client_email = st.text_input(t(lang, "client_email"), key="client_email_val")
            client_address = st.text_area(t(lang, "client_address"), key="client_address_val", height=90)

            bcol1, bcol2 = st.columns(2)
            with bcol1:
                if st.button(t(lang, "save_client"), use_container_width=True):
                    if client_name.strip():
                        storage.save_client({
                            "name": client_name.strip(),
                            "company": client_company.strip(),
                            "email": client_email.strip(),
                            "address": client_address.strip(),
                        })
                        st.success(t(lang, "client_saved"))
                    else:
                        st.error(t(lang, "err_client_name"))
            with bcol2:
                with st.popover(t(lang, "save_recurring"), use_container_width=True):
                    recurring_name = st.text_input(t(lang, "recurring_name"), key="recurring_name_input")
                    if st.button(t(lang, "confirm_save"), key="confirm_save_recurring"):
                        if not recurring_name.strip():
                            st.error(t(lang, "err_client_name"))
                        else:
                            rows = st.session_state.items_df.dropna(subset=["Description"])
                            rows = rows[rows["Description"].str.strip() != ""]
                            storage.save_recurring_template({
                                "name": recurring_name.strip(),
                                "doc_type": st.session_state.doctype_val,
                                "client_name": st.session_state.client_name_val,
                                "client_company": st.session_state.client_company_val,
                                "client_email": st.session_state.client_email_val,
                                "client_address": st.session_state.client_address_val,
                                "currency": st.session_state.currency_val,
                                "theme": st.session_state.theme_val,
                                "tax_percent": st.session_state.tax_percent_val,
                                "tax_inclusive": st.session_state.tax_inclusive_val,
                                "discount_amount": st.session_state.discount_val,
                                "advance_paid": st.session_state.advance_val,
                                "notes": st.session_state.notes_val,
                                "items": rows.to_dict("records"),
                            })
                            st.success(t(lang, "recurring_saved"))

    with col2:
        st.markdown(f'<div class="section-eyebrow">{t(lang, "payment_terms")}</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.caption(t(lang, "vat_presets"))
            vat_cols = st.columns(len(VAT_PRESETS) + 1)
            for i, rate in enumerate(VAT_PRESETS):
                if vat_cols[i].button(f"%{rate}", use_container_width=True, key=f"vat_preset_{rate}"):
                    st.session_state.tax_percent_val = float(rate)
            if vat_cols[-1].button(t(lang, "vat_custom"), use_container_width=True, key="vat_preset_custom"):
                pass  # no-op: leaves the number input free for manual entry

            tax_percent = st.number_input(t(lang, "tax_percent"), min_value=0.0, max_value=100.0, step=0.5, key="tax_percent_val")
            tax_inclusive = st.toggle(t(lang, "tax_inclusive_toggle"), help=t(lang, "tax_inclusive_help"), key="tax_inclusive_val")
            discount_amount = st.number_input(t(lang, "discount"), min_value=0.0, step=1.0, key="discount_val")
            advance_paid = st.number_input(t(lang, "advance_paid"), min_value=0.0, step=1.0, key="advance_val")
            notes = st.text_area(
                t(lang, "notes"), height=100, placeholder=t(lang, "notes_placeholder"), key="notes_val",
            )

    st.markdown(f'<div class="section-eyebrow">{t(lang, "itemized_table")}</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.caption(t(lang, "itemized_caption"))

        templates = storage.list_item_templates()
        if templates:
            tcol1, tcol2 = st.columns([4, 1])
            template_options = ["__none__"] + [tpl["id"] for tpl in templates]
            template_labels = {tpl["id"]: f"{tpl['description']} ({tpl['unit_price']:g})" for tpl in templates}
            template_labels["__none__"] = t(lang, "load_template_placeholder")
            picked_template = tcol1.selectbox(
                t(lang, "load_template"), options=template_options,
                format_func=lambda tid: template_labels[tid], key="template_picker", label_visibility="collapsed",
            )
            if tcol2.button(t(lang, "add_to_table"), use_container_width=True) and picked_template != "__none__":
                tpl = next(tp for tp in templates if tp["id"] == picked_template)
                new_row = pd.DataFrame([{
                    "Description": tpl["description"], "Quantity": tpl.get("quantity", 1), "Unit Price": tpl["unit_price"],
                }])
                st.session_state.items_df = pd.concat([st.session_state.items_df, new_row], ignore_index=True)
                st.success(t(lang, "template_added"))
                st.rerun()

        edited_df = st.data_editor(
            st.session_state.items_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Description": st.column_config.TextColumn(t(lang, "col_description"), width="large"),
                "Quantity": st.column_config.NumberColumn(t(lang, "col_quantity"), min_value=0.0, step=1.0),
                "Unit Price": st.column_config.NumberColumn(t(lang, "col_unit_price"), min_value=0.0, step=0.01, format="%.2f"),
            },
            key="items_editor",
        )
        st.session_state.items_df = edited_df

        with st.popover(t(lang, "save_as_template")):
            non_empty = edited_df.dropna(subset=["Description"])
            non_empty = non_empty[non_empty["Description"].str.strip() != ""]
            if non_empty.empty:
                st.caption(t(lang, "err_items"))
            else:
                row_options = list(non_empty.index)
                row_labels = {
                    idx: f"{non_empty.loc[idx, 'Description']} — {non_empty.loc[idx, 'Unit Price']:g}"
                    for idx in row_options
                }
                picked_row = st.selectbox(
                    t(lang, "save_as_template"), options=row_options,
                    format_func=lambda i: row_labels[i], label_visibility="collapsed",
                )
                if st.button(t(lang, "confirm_save"), key="confirm_save_template"):
                    row = non_empty.loc[picked_row]
                    storage.save_item_template({
                        "description": str(row["Description"]).strip(),
                        "quantity": float(row["Quantity"] or 1),
                        "unit_price": float(row["Unit Price"] or 0),
                    })
                    st.success(t(lang, "template_saved"))

    # ------------------------------------------------------- Live totals --
    valid_rows = edited_df.dropna(subset=["Description"])
    valid_rows = valid_rows[valid_rows["Description"].str.strip() != ""]

    items_total = float((valid_rows["Quantity"].fillna(0) * valid_rows["Unit Price"].fillna(0)).sum())
    if tax_inclusive and tax_percent:
        subtotal = items_total / (1 + tax_percent / 100)
        tax_amount = items_total - subtotal
        grand_total = items_total - discount_amount
    else:
        subtotal = items_total
        tax_amount = subtotal * (tax_percent / 100)
        grand_total = subtotal + tax_amount - discount_amount
    balance_due = grand_total - advance_paid

    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    summary_col1.metric(t(lang, "subtotal"), format_money(subtotal, currency, lang))
    tax_key = "tax_label_incl" if tax_inclusive else "tax_label"
    summary_col2.metric(t(lang, tax_key, pct=tax_percent), format_money(tax_amount, currency, lang))
    summary_col3.metric(t(lang, "discount_label"), f"-{format_money(discount_amount, currency, lang)}")
    summary_col4.metric(t(lang, "grand_total"), format_money(grand_total, currency, lang))

    if advance_paid:
        bcol1, bcol2 = st.columns(2)
        bcol1.metric(t(lang, "paid_label"), f"-{format_money(advance_paid, currency, lang)}")
        bcol2.metric(t(lang, "balance_due_label"), format_money(balance_due, currency, lang))

    st.write("")

    # ------------------------------------------------------- Generate PDF --
    generate_col, preview_col = st.columns([1, 3])
    with generate_col:
        generate_clicked = st.button(t(lang, "generate_pdf"), type="primary", use_container_width=True)
    with preview_col:
        show_preview = st.checkbox(t(lang, "preview_toggle"), key="show_preview_val")

    if generate_clicked:
        errors = []
        if not sender_name.strip():
            errors.append(t(lang, "err_sender_name"))
        if not client_name.strip():
            errors.append(t(lang, "err_client_name"))
        if valid_rows.empty:
            errors.append(t(lang, "err_items"))
        if due_date < issue_date:
            errors.append(t(lang, "err_due_date"))

        if errors:
            for err in errors:
                st.error(err)
        else:
            logo_bytes = sender_logo.getvalue() if sender_logo is not None else saved_logo_bytes
            signature_bytes = sender_signature.getvalue() if sender_signature is not None else saved_signature_bytes

            items = [
                LineItem(
                    description=str(row["Description"]).strip(),
                    quantity=float(row["Quantity"] or 0),
                    unit_price=float(row["Unit Price"] or 0),
                )
                for _, row in valid_rows.iterrows()
            ]

            data = DocumentData(
                doc_type=doc_type,
                doc_number=doc_number,
                issue_date=format_date(issue_date, lang),
                due_date=format_date(due_date, lang),
                sender=PartyDetails(
                    name=sender_name.strip(),
                    email=sender_email.strip(),
                    address=sender_address.strip(),
                    tax_number=sender_tax.strip(),
                    logo_bytes=logo_bytes,
                    signature_bytes=signature_bytes,
                ),
                client=ClientDetails(
                    name=client_name.strip(),
                    company=client_company.strip(),
                    email=client_email.strip(),
                    address=client_address.strip(),
                ),
                items=items,
                tax_percent=tax_percent,
                discount_amount=discount_amount,
                currency=currency,
                notes=notes.strip(),
                language=lang,
                tax_inclusive=tax_inclusive,
                accent_color=THEMES[theme_choice],
                advance_paid=advance_paid,
            )

            try:
                pdf_bytes = build_pdf(data)
            except Exception as exc:  # surface generation failures clearly
                st.error(t(lang, "pdf_fail", error=exc))
            else:
                st.success(t(lang, "pdf_success"))
                file_name = f"{doc_type}_{doc_number}.pdf".replace(" ", "_")

                saved_doc_id = storage.save_document(pdf_bytes, {
                    "doc_type": doc_type,
                    "doc_number": doc_number,
                    "client_name": client_name.strip(),
                    "grand_total": round(data.grand_total, 2),
                    "balance_due": round(data.balance_due, 2),
                    "currency": currency,
                    "issue_date": data.issue_date,
                    "due_date_iso": due_date.isoformat(),
                    "created_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "file_name": file_name,
                    "status": "unpaid",
                })
                storage.consume_next_number(doc_type)

                if show_preview:
                    st.caption(t(lang, "preview_caption"))
                    b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
                    st.markdown(
                        f'<iframe src="data:application/pdf;base64,{b64_pdf}" '
                        f'width="100%" height="700" style="border:1px solid #E2E8F0;border-radius:8px;"></iframe>',
                        unsafe_allow_html=True,
                    )

                st.session_state.last_pdf = {
                    "bytes": pdf_bytes,
                    "file_name": file_name,
                    "client_email": client_email.strip(),
                    "client_name": client_name.strip(),
                    "doc_type": doc_type,
                    "doc_number": doc_number,
                    "sender_name": sender_name.strip(),
                    "doc_id": saved_doc_id,
                    "grand_total": round(data.grand_total, 2),
                    "currency": currency,
                }

                st.download_button(
                    label=t(lang, "download_pdf"),
                    data=pdf_bytes,
                    file_name=file_name,
                    mime="application/pdf",
                    use_container_width=True,
                )

    # ------------------------------------------------------------- Email --
    with st.expander(t(lang, "email_section")):
        if not st.session_state.last_pdf:
            st.caption(t(lang, "email_no_pdf"))
        else:
            last = st.session_state.last_pdf
            with st.container(border=True):
                st.caption(t(lang, "email_smtp_settings"))
                scol1, scol2 = st.columns(2)
                smtp_host = scol1.text_input(t(lang, "email_smtp_host"), key="smtp_host", placeholder="smtp.gmail.com")
                smtp_port = scol2.number_input(t(lang, "email_smtp_port"), min_value=1, max_value=65535, value=587, key="smtp_port")
                smtp_user = st.text_input(t(lang, "email_smtp_user"), key="smtp_user")
                smtp_pass = st.text_input(t(lang, "email_smtp_pass"), type="password", key="smtp_pass")
                smtp_tls = st.checkbox(t(lang, "email_smtp_tls"), value=True, key="smtp_tls")

            email_to = st.text_input(t(lang, "email_to"), value=last["client_email"])
            default_subject = t(lang, "email_default_subject", doc_type=last["doc_type"], doc_number=last["doc_number"], sender=last["sender_name"])
            default_body = t(lang, "email_default_body", client=last["client_name"] or "-", doc_type=last["doc_type"], doc_number=last["doc_number"], sender=last["sender_name"])
            email_subject = st.text_input(t(lang, "email_subject"), value=default_subject)
            email_body = st.text_area(t(lang, "email_body"), value=default_body, height=140)

            if st.button(t(lang, "email_send"), type="primary"):
                if not email_to.strip() or not smtp_host or not smtp_user or not smtp_pass:
                    st.error(t(lang, "email_fail", error="Missing SMTP or recipient details"))
                else:
                    try:
                        smtp_cfg = SmtpConfig(
                            host=smtp_host.strip(), port=int(smtp_port),
                            username=smtp_user.strip(), password=smtp_pass, use_tls=smtp_tls,
                        )
                        send_email_with_attachment(
                            smtp_cfg, email_to.strip(), email_subject, email_body,
                            last["bytes"], last["file_name"],
                        )
                    except Exception as exc:
                        st.error(t(lang, "email_fail", error=exc))
                    else:
                        st.success(t(lang, "email_success", to=email_to.strip()))

    # ---------------------------------------------------------- WhatsApp --
    with st.expander(t(lang, "whatsapp_section")):
        if not st.session_state.last_pdf:
            st.caption(t(lang, "email_no_pdf"))
        else:
            last = st.session_state.last_pdf
            wa_phone = st.text_input(t(lang, "whatsapp_phone"), placeholder="905551234567", help=t(lang, "whatsapp_phone_help"))
            try:
                pdf_url = storage.get_document_url(last["doc_id"])
            except Exception:
                pdf_url = None

            if not pdf_url:
                st.caption(t(lang, "whatsapp_no_url"))
            else:
                default_wa_message = t(
                    lang, "whatsapp_default_message",
                    client=last["client_name"] or "-", doc_type=last["doc_type"], doc_number=last["doc_number"],
                    total=format_money(last["grand_total"], last["currency"], lang),
                    sender=last["sender_name"], url=pdf_url,
                )
                wa_message = st.text_area(t(lang, "whatsapp_message"), value=default_wa_message, height=140)

                digits = "".join(ch for ch in wa_phone if ch.isdigit())
                wa_base = f"https://wa.me/{digits}" if digits else "https://wa.me/"
                wa_link = f"{wa_base}?text={urllib.parse.quote(wa_message)}"
                st.link_button(t(lang, "whatsapp_send"), wa_link, type="primary", use_container_width=True)
                st.caption(t(lang, "whatsapp_help"))

# ======================================================= TAB: DASHBOARD ===
with tab_dashboard:
    history = storage.list_documents()
    today_iso = dt.date.today().isoformat()

    def _is_overdue(record: dict) -> bool:
        return bool(
            record.get("status") != "paid"
            and record.get("due_date_iso") and record["due_date_iso"] < today_iso
            and record.get("balance_due", record.get("grand_total", 0)) > 0
        )

    if not history:
        st.info(t(lang, "dashboard_empty"))
    else:
        by_currency: dict[str, float] = {}
        by_client: dict[str, float] = {}
        by_month: dict[str, float] = {}
        for r in history:
            by_currency[r["currency"]] = by_currency.get(r["currency"], 0) + r["grand_total"]
            by_client[r["client_name"]] = by_client.get(r["client_name"], 0) + r["grand_total"]
            month_key = r["created_at"][:7]  # YYYY-MM
            by_month[month_key] = by_month.get(month_key, 0) + r["grand_total"]

        dcol1, dcol2 = st.columns(2)
        total_text = "  •  ".join(f"{format_money(v, c, lang)}" for c, v in by_currency.items())
        dcol1.metric(t(lang, "dashboard_total_invoiced"), total_text)
        dcol2.metric(t(lang, "dashboard_doc_count"), str(len(history)))

        st.write("")
        dcol3, dcol4 = st.columns(2)
        with dcol3:
            st.markdown(f'<div class="section-eyebrow">{t(lang, "dashboard_top_clients")}</div>', unsafe_allow_html=True)
            top_clients = sorted(by_client.items(), key=lambda kv: kv[1], reverse=True)[:5]
            st.dataframe(
                pd.DataFrame(top_clients, columns=[t(lang, "client_name").rstrip(" *"), t(lang, "grand_total")]),
                use_container_width=True, hide_index=True,
            )
        with dcol4:
            st.markdown(f'<div class="section-eyebrow">{t(lang, "dashboard_by_month")}</div>', unsafe_allow_html=True)
            month_series = pd.Series(dict(sorted(by_month.items())))
            st.bar_chart(month_series, color="#2563EB")

# ========================================================= TAB: HISTORY ===
with tab_history:
    history = storage.list_documents()
    today_iso = dt.date.today().isoformat()

    hcol_search, hcol_filter, hcol_export = st.columns([2, 2, 1])
    search_query = hcol_search.text_input(
        t(lang, "history_search"), key="history_search_val",
        placeholder=t(lang, "history_search_placeholder"),
    )
    status_options = ["all", "unpaid", "paid", "overdue"]
    status_display = {
        "all": t(lang, "filter_all"), "unpaid": t(lang, "status_unpaid"),
        "paid": t(lang, "status_paid"), "overdue": t(lang, "status_overdue"),
    }
    status_filter = hcol_filter.selectbox(
        t(lang, "filter_status"), options=status_options,
        format_func=lambda s: status_display[s], key="status_filter_val",
    )

    with hcol_export:
        st.write("")
        if history:
            st.download_button(
                t(lang, "export_all"), data=storage.export_all_zip(),
                file_name="invoice_generator_export.zip", mime="application/zip",
                help=t(lang, "export_all_help"), use_container_width=True,
            )
        else:
            st.caption(t(lang, "export_all_empty"))

    if not history:
        st.info(t(lang, "history_empty"))
    else:
        visible = history
        if status_filter == "overdue":
            visible = [r for r in visible if _is_overdue(r)]
        elif status_filter != "all":
            visible = [r for r in visible if r.get("status", "unpaid") == status_filter]

        if search_query.strip():
            q = search_query.strip().lower()
            visible = [
                r for r in visible
                if q in r.get("client_name", "").lower() or q in r.get("doc_number", "").lower()
            ]

        if not visible:
            st.caption(t(lang, "history_no_matches"))

        for record in visible[:30]:
            with st.container(border=True):
                hcol1, hcol2, hcol3, hcol4 = st.columns([3, 1.3, 1, 1])
                is_overdue = _is_overdue(record)
                if is_overdue:
                    badge_html = f'<span class="badge badge-overdue">⚠ {t(lang, "status_overdue")}</span>'
                elif record.get("status") == "paid":
                    badge_html = f'<span class="badge badge-paid">✓ {t(lang, "status_paid")}</span>'
                else:
                    badge_html = f'<span class="badge badge-unpaid">{t(lang, "status_unpaid")}</span>'
                title = html_lib.escape(
                    f"{record['doc_type']} {record['doc_number']} — {record['client_name']} — "
                    f"{format_money(record['grand_total'], record['currency'], lang)}"
                )
                created_at = html_lib.escape(str(record["created_at"]))
                hcol1.markdown(
                    f'<div class="doc-title">{title}</div>'
                    f'<div class="doc-sub">{created_at} &nbsp; {badge_html}</div>',
                    unsafe_allow_html=True,
                )

                current_status = record.get("status", "unpaid")
                new_status = hcol2.selectbox(
                    t(lang, "status_label"), options=["unpaid", "paid"],
                    format_func=lambda s: status_display[s],
                    index=["unpaid", "paid"].index(current_status if current_status in ("unpaid", "paid") else "unpaid"),
                    key=f"status_{record['id']}", label_visibility="collapsed",
                )
                if new_status != current_status:
                    storage.update_document_status(record["id"], new_status)
                    st.rerun()

                pdf_data = storage.read_document(record["id"])
                if pdf_data:
                    hcol3.download_button(
                        t(lang, "history_download"), data=pdf_data,
                        file_name=record["file_name"], mime="application/pdf",
                        key=f"dl_{record['id']}", use_container_width=True,
                    )
                if hcol4.button(t(lang, "history_delete"), key=f"del_{record['id']}", use_container_width=True):
                    storage.delete_document(record["id"])
                    st.rerun()

# ========================================================= TAB: RECORDS ===
with tab_records:
    rcol1, rcol2, rcol3 = st.columns(3)

    with rcol1:
        st.markdown(f'<div class="section-eyebrow">{t(lang, "address_book")}</div>', unsafe_allow_html=True)
        clients = storage.list_clients()
        if not clients:
            st.caption(t(lang, "address_book_empty"))
        else:
            for c in clients:
                with st.container(border=True):
                    ccol1, ccol2 = st.columns([4, 1])
                    detail = " — ".join(x for x in [c.get("company", ""), c.get("email", "")] if x)
                    ccol1.markdown(f"**{c['name']}**")
                    if detail:
                        ccol1.caption(detail)
                    if ccol2.button("🗑️", key=f"delclient_{c['id']}", use_container_width=True):
                        storage.delete_client(c["id"])
                        st.rerun()

    with rcol2:
        st.markdown(f'<div class="section-eyebrow">{t(lang, "item_templates")}</div>', unsafe_allow_html=True)
        templates = storage.list_item_templates()
        if not templates:
            st.caption(t(lang, "item_templates_empty"))
        else:
            for tpl in templates:
                with st.container(border=True):
                    tpl_col1, tpl_col2 = st.columns([4, 1])
                    tpl_col1.markdown(f"**{tpl['description']}**")
                    tpl_col1.caption(f"{tpl.get('quantity', 1):g} × {tpl['unit_price']:g}")
                    if tpl_col2.button("🗑️", key=f"deltpl_{tpl['id']}", use_container_width=True):
                        storage.delete_item_template(tpl["id"])
                        st.rerun()

    with rcol3:
        st.markdown(f'<div class="section-eyebrow">{t(lang, "recurring_section")}</div>', unsafe_allow_html=True)
        recurring_templates = storage.list_recurring_templates()
        if not recurring_templates:
            st.caption(t(lang, "recurring_empty"))
        else:
            for r in recurring_templates:
                with st.container(border=True):
                    rec_col1, rec_col2 = st.columns([4, 1])
                    item_count = len(r.get("items", []))
                    rec_col1.markdown(f"**{r.get('name', '?')}**")
                    rec_col1.caption(f"{r.get('client_name', '')} — {t(lang, 'items_count', n=item_count)}")
                    if rec_col2.button("🗑️", key=f"delrec_{r['id']}", use_container_width=True):
                        storage.delete_recurring_template(r["id"])
                        st.rerun()

    st.divider()
    st.markdown(f'<div class="section-eyebrow">{t(lang, "restore_section")}</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.caption(t(lang, "restore_help"))
        backup_file = st.file_uploader(t(lang, "restore_upload"), type=["zip"], key="restore_upload_val")
        overwrite_profile_chk = st.checkbox(t(lang, "restore_overwrite_profile"), key="restore_overwrite_val")
        if st.button(t(lang, "restore_button"), disabled=backup_file is None):
            try:
                summary = storage.import_zip(backup_file.getvalue(), overwrite_profile=overwrite_profile_chk)
            except Exception as exc:
                st.error(t(lang, "restore_fail", error=exc))
            else:
                st.success(t(
                    lang, "restore_success",
                    docs=summary["documents"], clients=summary["clients"],
                    items=summary["item_templates"], recurring=summary["recurring_templates"],
                ))
                if summary["profile_applied"]:
                    st.session_state.profile = storage.load_profile() or {}
                st.rerun()
