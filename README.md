# AppSumo Invoices: Descarga y Parser

Automatiza la descarga masiva de facturas de AppSumo y su parseo a CSV/XLSX.

## Qué incluye
- `download_invoices_from_ids.py`: descarga PDFs de facturas por `invoice_id` usando Playwright.
- `parse_appsumo_invoices.py`: extrae campos clave de los PDFs y genera CSV/XLSX.
- `ids.txt`: ejemplo de lista de IDs (un ID por línea).
- `output/invoices/`: carpeta donde se guardan los PDFs descargados.

## Requisitos
- Python 3.10+
- Google Chromium (lo instala Playwright)
- Dependencias Python:
  - `playwright==1.46.0`
  - `pandas==2.2.2`
  - `pdfminer.six==20231228`
  - `pdfplumber==0.11.4`
  - `openpyxl==3.1.5` (solo si vas a exportar `.xlsx`)
- Una sesión iniciada de AppSumo guardada en `storage_state.json`

Instalación de dependencias y navegador:
```bash
python -m venv venv
source venv/bin/activate  # en macOS/Linux
pip install --upgrade pip
pip install playwright==1.46.0 pandas==2.2.2 pdfminer.six==20231228 pdfplumber==0.11.4 openpyxl==3.1.5
playwright install chromium
```

## 1) Guardar la sesión de AppSumo (una vez)
Guarda cookies/estado en `storage_state.json` para que las descargas funcionen autenticadas.
```bash
python download_invoices_from_ids.py --login
```
Se abrirá Chromium. Inicia sesión en AppSumo y cierra el navegador. Se generará `storage_state.json` en el directorio del proyecto.

## 2) Descargar facturas en PDF
Puedes obtener los `invoice_id` desde un CSV o desde un archivo de texto.

### 2.a) Desde CSV consolidado
Por defecto lee `appsumo_consolidado_con_facturas.csv` (debe contener una columna `Invoice`, `Invoice ID` o `invoice_id`):
```bash
python download_invoices_from_ids.py --download --csv appsumo_consolidado_con_facturas.csv
```

### 2.b) Desde archivo de IDs
Crea un `ids.txt` con un `invoice_id` por línea y ejecuta:
```bash
python download_invoices_from_ids.py --download --ids ids.txt
```

### Opciones útiles
- `--limit N`: descarga solo los primeros N (pruebas rápidas).
- `--headful`: muestra el navegador (por defecto es headless).
- `--out DIR`: carpeta destino (por defecto `output/invoices`).

Los PDFs se guardan como `invoice-<invoice_id>.pdf` en `output/invoices/`.

## 3) Parsear los PDFs a CSV/XLSX
Convierte los PDFs descargados en una tabla con columnas normalizadas.

```bash
python parse_appsumo_invoices.py --in output/invoices --out output/parsed/appsumo_invoices.xlsx --log output/parsed/parse_log.csv
```

También puedes generar CSV:
```bash
python parse_appsumo_invoices.py --in output/invoices --out output/parsed/appsumo_invoices.csv --log output/parsed/parse_log.csv
```

Columnas principales generadas por el parser:
- `invoice_id`
- `invoice_status` (PAID/REFUNDED)
- `invoice_date` (YYYY-MM-DD)
- `payment_type`
- `tax_id`
- `product_name`
- `deal_plan`
- `line_subtotal`
- `line_plan_discount`
- `line_total`
- `invoice_subtotal`
- `invoice_plan_discount_total`
- `invoice_tax`
- `invoice_total_paid`
- `_source_file` (ruta del PDF de origen)

Notas del parser:
- Usa `pdfminer.six` como extractor principal con parámetros ajustados al layout de AppSumo y `pdfplumber` como fallback.
- Si una factura tiene una sola línea de producto, el parser completa `line_total` y `line_subtotal` a partir de los totales de factura cuando es posible.

## Estructura sugerida de carpetas
```
.
├─ download_invoices_from_ids.py
├─ parse_appsumo_invoices.py
├─ ids.txt
├─ storage_state.json               # generado tras el login
└─ output/
   ├─ invoices/                     # PDFs descargados
   └─ parsed/                       # CSV/XLSX y logs
```

## Solución de problemas
- 403/401 al descargar: asegúrate de haber ejecutado `--login` recientemente y de que `storage_state.json` exista.
- CAPTCHA o bloqueos: usa `--headful` y completa interacción manual si es necesario; luego cierra el navegador para guardar el estado.
- Playwright no encuentra navegador: ejecuta `playwright install chromium`.
- Exportar a Excel falla: instala `openpyxl`.

## Seguridad
`storage_state.json` contiene cookies de tu sesión. No lo compartas ni lo subas públicamente.

## Licencia
MIT (o la que prefieras)
