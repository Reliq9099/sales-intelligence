"""Small local JSON CRM store for researched BWC prospects."""

from __future__ import annotations

from datetime import datetime, timezone
import csv
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any


CRM_PATH = Path(os.getenv("BWC_CRM_PATH", "crm_data.json"))
PIPELINE_STATUSES = ("NEW", "RESEARCHING", "QUALIFIED", "CONTACTED", "MEETING", "WON", "LOST")


def _read_store() -> dict[str, list[dict[str, Any]]]:
    try:
        with CRM_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return {"accounts": payload, "contacts": []}
        if isinstance(payload, dict):
            return {
                "accounts": payload.get("accounts", []) if isinstance(payload.get("accounts", []), list) else [],
                "contacts": payload.get("contacts", []) if isinstance(payload.get("contacts", []), list) else [],
            }
        return {"accounts": [], "contacts": []}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"accounts": [], "contacts": []}


def _write_store(store: dict[str, list[dict[str, Any]]]) -> None:
    CRM_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=".crm_", dir=CRM_PATH.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
        os.replace(temporary_path, CRM_PATH)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def list_prospects() -> list[dict[str, Any]]:
    return sorted(_read_store()["accounts"], key=lambda item: item.get("updated_at", ""), reverse=True)


def list_accounts() -> list[dict[str, Any]]:
    return list_prospects()


def list_contacts(account: str | None = None) -> list[dict[str, Any]]:
    contacts = _read_store()["contacts"]
    if account:
        normalized = account.strip().lower()
        contacts = [item for item in contacts if item.get("account", "").strip().lower() == normalized]
    return sorted(contacts, key=lambda item: item.get("updated_at", ""), reverse=True)


def records_to_csv(records: list[dict[str, Any]], fields: list[str]) -> str:
    """Serialize CRM records with stable columns for spreadsheet import/export."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({field: record.get(field, "") for field in fields} for record in records)
    return output.getvalue()


def accounts_csv() -> str:
    return records_to_csv(list_accounts(), [
        "company", "website", "industry", "pipeline_status", "owner", "sales_score",
        "research_quality", "recommendation", "solution", "research_status", "next_action",
        "follow_up_date", "notes", "created_at", "updated_at",
    ])


def contacts_csv() -> str:
    return records_to_csv(list_contacts(), [
        "account", "name", "role", "email", "phone", "notes", "created_at", "updated_at",
    ])


def contact_template_csv() -> str:
    return records_to_csv([], ["account", "name", "role", "email", "phone", "notes"])


def _csv_rows(content: bytes | str) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    return list(csv.DictReader(io.StringIO(text)))


def import_accounts_csv(content: bytes | str) -> tuple[int, list[str]]:
    imported = 0
    errors: list[str] = []
    for row_number, row in enumerate(_csv_rows(content), start=2):
        company = (row.get("company") or row.get("account") or "").strip()
        if not company:
            errors.append(f"Row {row_number}: company is required.")
            continue
        save_account(
            company=company,
            website=(row.get("website") or "").strip(),
            industry=(row.get("industry") or "").strip(),
            notes=(row.get("notes") or "").strip(),
            owner=(row.get("owner") or "").strip(),
            pipeline_status=(row.get("pipeline_status") or "NEW").strip().upper(),
            follow_up_date=(row.get("follow_up_date") or "").strip(),
            sales_score=(row.get("sales_score") or "").strip(),
            research_quality=(row.get("research_quality") or "").strip(),
            recommendation=(row.get("recommendation") or "").strip(),
            solution=(row.get("solution") or "").strip(),
            research_status=(row.get("research_status") or "").strip(),
            next_action=(row.get("next_action") or "").strip(),
        )
        imported += 1
    return imported, errors


def import_contacts_csv(content: bytes | str) -> tuple[int, list[str]]:
    imported = 0
    errors: list[str] = []
    existing_accounts = {item.get("company", "").strip().lower() for item in list_accounts()}
    for row_number, row in enumerate(_csv_rows(content), start=2):
        account = (row.get("account") or row.get("company") or "").strip()
        name = (row.get("name") or row.get("contact") or "").strip()
        if not account:
            errors.append(f"Row {row_number}: account is required.")
            continue
        if not name:
            errors.append(f"Row {row_number}: contact name is required.")
            continue
        if account.lower() not in existing_accounts:
            errors.append(f"Row {row_number}: account '{account}' does not exist; create the account first.")
            continue
        save_contact(
            account=account,
            name=name,
            role=(row.get("role") or "").strip(),
            email=(row.get("email") or "").strip(),
            phone=(row.get("phone") or "").strip(),
            notes=(row.get("notes") or "").strip(),
        )
        imported += 1
    return imported, errors


def save_account(*, company: str, website: str = "", industry: str = "", notes: str = "", **fields: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    store = _read_store()
    normalized = company.strip().lower()
    existing = next((item for item in store["accounts"] if item.get("company", "").strip().lower() == normalized), None)
    account = dict(existing or {})
    account.update({
        "company": company.strip(),
        "website": website.strip(),
        "industry": industry,
        "notes": notes,
        "pipeline_status": "NEW",
        "owner": "",
        "sales_score": "",
        **fields,
    })
    account.setdefault("created_at", now)
    account["updated_at"] = now
    if existing:
        store["accounts"][store["accounts"].index(existing)] = account
    else:
        store["accounts"].append(account)
    _write_store(store)
    return account


def save_prospect(
    *,
    company: str,
    industry: str,
    website: str,
    sales_score: int,
    research_quality: int,
    recommendation: str,
    solution: str,
    primary_persona: str,
    secondary_personas: list[str],
    next_action: str,
    research_status: str,
    notes: str = "",
    owner: str = "",
    pipeline_status: str = "NEW",
    follow_up_date: str = "",
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    store = _read_store()
    records = store["accounts"]
    normalized_company = company.strip().lower()
    existing = next((item for item in records if item.get("company", "").strip().lower() == normalized_company), None)
    prospect = {
        "company": company.strip(),
        "industry": industry,
        "website": website,
        "sales_score": sales_score,
        "research_quality": research_quality,
        "recommendation": recommendation,
        "solution": solution,
        "primary_persona": primary_persona,
        "secondary_personas": secondary_personas,
        "next_action": next_action,
        "research_status": research_status,
        "notes": notes,
        "owner": owner,
        "pipeline_status": pipeline_status if pipeline_status in PIPELINE_STATUSES else "NEW",
        "follow_up_date": follow_up_date,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
    }
    if existing:
        index = records.index(existing)
        records[index] = prospect
    else:
        records.append(prospect)
    store["accounts"] = records
    _write_store(store)
    return prospect


def save_contact(*, account: str, name: str, role: str = "", email: str = "", phone: str = "", notes: str = "") -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    store = _read_store()
    normalized_account = account.strip().lower()
    normalized_name = name.strip().lower()
    existing = next((item for item in store["contacts"] if item.get("account", "").strip().lower() == normalized_account and item.get("name", "").strip().lower() == normalized_name), None)
    contact = dict(existing or {})
    contact.update({"account": account.strip(), "name": name.strip(), "role": role.strip(), "email": email.strip(), "phone": phone.strip(), "notes": notes.strip()})
    contact.setdefault("created_at", now)
    contact["updated_at"] = now
    if existing:
        store["contacts"][store["contacts"].index(existing)] = contact
    else:
        store["contacts"].append(contact)
    _write_store(store)
    return contact


def delete_prospect(company: str) -> None:
    normalized_company = company.strip().lower()
    store = _read_store()
    store["accounts"] = [item for item in store["accounts"] if item.get("company", "").strip().lower() != normalized_company]
    store["contacts"] = [item for item in store["contacts"] if item.get("account", "").strip().lower() != normalized_company]
    _write_store(store)
