#!/usr/bin/env python3
import argparse, re, sys, os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd

# Primary extractor (pdfminer) with layout tuning
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams
from io import StringIO

# Fallback
import pdfplumber

DATE_PATTERNS = [
    ("%B %d, %Y", re.compile(r"Date:\s*([A-Za-z]+ \d{1,2}, \d{4})", re.I)),
    ("%b %d, %Y",  re.compile(r"Date:\s*([A-Za-z]{3} \d{1,2}, \d{4})", re.I)),
]

RE_INVOICE_ID = re.compile(r"Invoice ID:\s*([0-9a-f-]{16,})", re.I)
RE_STATUS     = re.compile(r"Status:\s*(PAID|REFUNDED)", re.I)
RE_PAYMENT    = re.compile(r"Payment type:\s*([^\n]+)", re.I)
RE_TAXID      = re.compile(r"Tax ID:\s*([A-Z0-9\-]+)", re.I)

# Invoice-level totals (tolerant to whitespace/newlines)
RE_INVOICE_SUBTOTAL   = re.compile(r"Invoice\s+subtotal\s*\$?\s*([0-9\.\,]+)", re.I)
RE_PLAN_DISCOUNT_TOT  = re.compile(r"Total\s+applied\s+plan\s+discount\s*[-–]?\s*\$?\s*([0-9\.\,]+)", re.I)
RE_INVOICE_TAX        = re.compile(r"Tax\s*\$?\s*([0-9\.\,]+)", re.I)
RE_TOTAL_PAID         = re.compile(r"Total\s+paid\s*\([^)]+\)\s*\$?\s*([0-9\.\,]+)", re.I)

# Product patterns
RE_DEAL_PLAN    = re.compile(r"Deal\s+plan:\s*([^\n]+)", re.I)
RE_LINE_SUBTOTAL= re.compile(r"Subtotal\s*\$?\s*([0-9\.\,]+)", re.I)
RE_LINE_TOTAL   = re.compile(r"Total\s*\$?\s*([0-9\.\,]+)", re.I)
RE_LINE_PLAN_DISCOUNT = re.compile(r"Plan\s+discount\s*[-–]?\s*\$?\s*([0-9\.\,]+)", re.I)

# This finds "Name ... Subtotal $xx" even with line breaks between tokens
RE_PRODUCT_NAME_WITH_SUBTOTAL = re.compile(
    r"(?P<name>[A-Za-z0-9].{0,80}?)\s+Subtotal\s*\$?\s*([0-9\.\,]+)",
    re.I | re.S
)

def norm_amount(s: Optional[str]) -> Optional[float]:
    # Normalize '1,234.56' or '1.234,56' or '3,6' to 1234.56/1234.56/3.6
    if not s: return None
    s = s.strip().replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        if "," in s and "." not in s:
            s = s.replace(",", ".")
    try:
        return float(s)
    except:
        m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", s)
        return float(m.group(1)) if m else None

def parse_date(text: str) -> Optional[str]:
    for fmt, rx in DATE_PATTERNS:
        m = rx.search(text)
        if m:
            try:
                d = datetime.strptime(m.group(1), fmt).date()
                return d.isoformat()
            except Exception:
                pass
    return None

def extract_text_pdfminer(pdf_path: Path) -> str:
    output = StringIO()
    laparams = LAParams(char_margin=2.0, line_margin=0.3, word_margin=0.2, boxes_flow=None)
    with open(pdf_path, "rb") as f:
        extract_text_to_fp(f, output, laparams=laparams, output_type='text', codec=None)
    return output.getvalue()

def extract_text_best(pdf_path: Path) -> str:
    try:
        return extract_text_pdfminer(pdf_path)
    except Exception:
        pass
    try:
        txt = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for p in pdf.pages:
                txt.append(p.extract_text() or "")
        return "\n".join(txt)
    except Exception:
        return ""

def split_product_blocks(text: str) -> List[Dict[str, Any]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    rows: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        window = "\n".join(lines[i:i+12])
        m = RE_PRODUCT_NAME_WITH_SUBTOTAL.search(window)
        if m:
            name = m.group("name").strip()
            window2 = "\n".join(lines[i:i+25])
            mplan = RE_DEAL_PLAN.search(window2)
            msub  = RE_LINE_SUBTOTAL.search(window2)
            mdisc = RE_LINE_PLAN_DISCOUNT.search(window2)
            mtot  = RE_LINE_TOTAL.search(window2)
            rows.append({
                "product_name": name,
                "deal_plan": mplan.group(1).strip() if mplan else None,
                "line_subtotal": norm_amount(msub.group(1)) if msub else None,
                "line_plan_discount": norm_amount(mdisc.group(1)) if mdisc else None,
                "line_total": norm_amount(mtot.group(1)) if mtot else None,
            })
            i += 6
        else:
            i += 1
    return rows

def parse_invoice_text(text: str) -> List[Dict[str, Any]]:
    inv_id = RE_INVOICE_ID.search(text)
    status = RE_STATUS.search(text)
    payment = RE_PAYMENT.search(text)
    inv_date = parse_date(text)
    taxid = RE_TAXID.search(text)

    invoice_id   = inv_id.group(1) if inv_id else None
    invoice_stat = status.group(1).upper() if status else None
    payment_type = payment.group(1).strip() if payment else None
    tax_id       = taxid.group(1).strip() if taxid else None

    inv_subtotal = norm_amount(RE_INVOICE_SUBTOTAL.search(text).group(1)) if RE_INVOICE_SUBTOTAL.search(text) else None
    plan_disc_tot= norm_amount(RE_PLAN_DISCOUNT_TOT.search(text).group(1)) if RE_PLAN_DISCOUNT_TOT.search(text) else None
    inv_tax      = norm_amount(RE_INVOICE_TAX.search(text).group(1)) if RE_INVOICE_TAX.search(text) else None
    total_paid   = norm_amount(RE_TOTAL_PAID.search(text).group(1)) if RE_TOTAL_PAID.search(text) else None

    prod_rows = split_product_blocks(text)

    if len(prod_rows) == 1:
        if prod_rows[0].get("line_total") is None and total_paid is not None:
            prod_rows[0]["line_total"] = total_paid
        if prod_rows[0].get("line_subtotal") is None and inv_subtotal is not None:
            prod_rows[0]["line_subtotal"] = inv_subtotal

    out: List[Dict[str, Any]] = []
    if not prod_rows and invoice_id:
        out.append({
            "invoice_id": invoice_id,
            "invoice_status": invoice_stat,
            "invoice_date": inv_date,
            "payment_type": payment_type,
            "tax_id": tax_id,
            "product_name": None,
            "deal_plan": None,
            "line_subtotal": None,
            "line_plan_discount": None,
            "line_total": None,
            "invoice_subtotal": inv_subtotal,
            "invoice_plan_discount_total": plan_disc_tot,
            "invoice_tax": inv_tax,
            "invoice_total_paid": total_paid,
        })
    else:
        for r in prod_rows:
            r.update({
                "invoice_id": invoice_id,
                "invoice_status": invoice_stat,
                "invoice_date": inv_date,
                "payment_type": payment_type,
                "tax_id": tax_id,
                "invoice_subtotal": inv_subtotal,
                "invoice_plan_discount_total": plan_disc_tot,
                "invoice_tax": inv_tax,
                "invoice_total_paid": total_paid,
            })
            out.append(r)

    return out

def main():
    ap = argparse.ArgumentParser(description="Parse AppSumo invoice PDFs to CSV/Excel (v2 robust)")
    ap.add_argument("--in", dest="in_dir", required=True, help="Folder with PDFs")
    ap.add_argument("--out", dest="out_path", required=True, help="Output .xlsx or .csv")
    ap.add_argument("--log", dest="log_csv", required=False, help="Log CSV path")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_path = Path(args.out_path)
    if not in_dir.exists():
        sys.exit(f"Input folder not found: {in_dir}")

    all_rows: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    pdfs = sorted([p for p in in_dir.rglob("*.pdf")])
    print(f">>> Found {len(pdfs)} PDFs")
    for i, pdf in enumerate(pdfs, 1):
        try:
            text = extract_text_best(pdf)
            rows = parse_invoice_text(text)
            for r in rows:
                r["_source_file"] = str(pdf)
            all_rows.extend(rows)
            logs.append({"pdf_file": str(pdf), "invoice_id": rows[0]["invoice_id"] if rows else None, "rows": len(rows), "error": ""})
            print(f"  [{i}] {pdf.name} -> {len(rows)} row(s)")
        except Exception as e:
            logs.append({"pdf_file": str(pdf), "invoice_id": None, "rows": 0, "error": str(e)})
            print(f"  [{i}] ERROR parsing {pdf.name}: {e}")

    df = pd.DataFrame(all_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".xlsx":
        df.to_excel(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)
    print(f">>> Saved: {out_path.resolve()}")

    if args.log_csv:
        log_path = Path(args.log_csv)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(logs).to_csv(log_path, index=False)
        print(f">>> Log saved: {log_path.resolve()}")

    if not df.empty:
        invoices = df["invoice_id"].nunique()
        lines = df.shape[0]
        print(f">>> Invoices parsed: {invoices}, product lines: {lines}")

if __name__ == "__main__":
    main()
