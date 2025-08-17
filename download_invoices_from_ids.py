#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd
import re
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

APP_BASE = "https://appsumo.com"
PDF_URL_TMPL = APP_BASE + "/account/history/pdf/{invoice_id}/"
STATE_FILE = Path("storage_state.json")

def collect_ids_from_csv(csv_path: Path):
    df = pd.read_csv(csv_path)
    col = None
    for c in df.columns:
        if c.strip().lower() in {"invoice", "invoice id", "invoice_id"}:
            col = c
            break
    if not col:
        raise SystemExit("No se encuentra columna 'Invoice' en el CSV")
    ids = [str(x).strip() for x in df[col].dropna().tolist() if str(x).strip()]
    # filtra por patrón UUID aproximado
    ids = [x for x in ids if re.match(r"^[0-9a-f-]{16,}$", x, re.I)]
    return list(dict.fromkeys(ids))  # únicos y orden conservado

def collect_ids_from_txt(txt_path: Path):
    ids = []
    for line in txt_path.read_text(encoding="utf-8").splitlines():
        x = line.strip()
        if re.match(r"^[0-9a-f-]{16,}$", x, re.I):
            ids.append(x)
    return list(dict.fromkeys(ids))

def login_flow(headful=False):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context()
        page = context.new_page()
        page.goto(APP_BASE + "/account/products/", wait_until="domcontentloaded")
        print(">>> Inicia sesión en AppSumo y luego cierra la ventana del navegador.")
        try:
            page.get_by_text("Products").first.wait_for(timeout=120000)
        except PWTimeout:
            pass
        context.storage_state(path=str(STATE_FILE))
        print(f">>> Sesión guardada en {STATE_FILE.resolve()}")
        browser.close()

def download_all(ids, out_dir: Path, headful=False, limit=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        if STATE_FILE.exists():
            context = p.chromium.launch(headless=not headful).new_context(storage_state=str(STATE_FILE))
        else:
            print("No existe storage_state.json. Ejecuta primero --login")
            return
        # abre una página para establecer sesión
        page = context.new_page()
        page.goto(APP_BASE + "/account/products/", wait_until="domcontentloaded")
        api = context.request

        done = 0
        for i, inv in enumerate(ids, 1):
            if limit and done >= limit: break
            url = PDF_URL_TMPL.format(invoice_id=inv)
            fname = out_dir / f"invoice-{inv}.pdf"
            if fname.exists():
                print(f"[{i}] SKIP {inv} (ya existe)")
                continue
            print(f"[{i}] GET {url}")
            try:
                resp = api.get(url, timeout=60000)
                if resp.ok:
                    fname.write_bytes(resp.body())
                    print(f"   -> guardado {fname.name} ({len(resp.body())} bytes)")
                    done += 1
                else:
                    print(f"   !! HTTP {resp.status} {resp.status_text}")
            except Exception as e:
                print(f"   !! Error: {e}")
        context.close()

def main():
    ap = argparse.ArgumentParser(description="Descarga masiva de facturas AppSumo por Invoice ID")
    ap.add_argument("--login", action="store_true", help="Abrir navegador para iniciar sesión y guardar storage_state.json")
    ap.add_argument("--download", action="store_true", help="Descargar PDFs")
    ap.add_argument("--csv", type=str, help="CSV con columna 'Invoice' (por defecto appsumo_consolidado_con_facturas.csv)", default="appsumo_consolidado_con_facturas.csv")
    ap.add_argument("--ids", type=str, help="Archivo de texto con un invoice_id por línea")
    ap.add_argument("--out", type=str, help="Directorio de salida (default output/invoices)", default="output/invoices")
    ap.add_argument("--limit", type=int, help="Limitar número de descargas", default=None)
    ap.add_argument("--headful", action="store_true", help="Mostrar navegador")
    args = ap.parse_args()

    if args.login:
        login_flow(headful=args.headful)
        return

    if args.download:
        ids = []
        if args.ids:
            ids = collect_ids_from_txt(Path(args.ids))
        else:
            ids = collect_ids_from_csv(Path(args.csv))
        print(f">>> {len(ids)} IDs de factura para descargar")
        download_all(ids, Path(args.out), headful=args.headful, limit=args.limit)
        return

    ap.print_help()

if __name__ == "__main__":
    main()
