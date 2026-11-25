import json
import os
import re
import sqlite3
import socket
import uuid
import io
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Timer
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import webbrowser
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from flask import Flask, abort, jsonify, request, send_file, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from evaluation import evaluate_expense
from sire_import import parse_purchase_workbook


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "plantillas_excel"
def _get_instance_dir():
    if os.environ.get("VERCEL") == "1":
        return Path("/tmp/tribuanalisis")
    configured_instance = os.environ.get("TRIBUANALISIS_INSTANCE")
    if configured_instance:
        return Path(configured_instance)
    return BASE_DIR / "instance"


IS_VERCEL = os.environ.get("VERCEL") == "1"
INSTANCE_DIR = _get_instance_dir()
if IS_VERCEL:
    DATABASE_PATH = INSTANCE_DIR / "tribuanalisis.db"
    UPLOAD_DIR = INSTANCE_DIR / "uploads"
else:
    DATABASE_PATH = Path(os.environ.get("TRIBUANALISIS_DB", INSTANCE_DIR / "tribuanalisis.db"))
    UPLOAD_DIR = Path(os.environ.get("TRIBUANALISIS_UPLOAD_DIR", INSTANCE_DIR / "uploads"))
CASE_BATCH_DIR = INSTANCE_DIR / "casos_prueba"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CASE_BATCH_DIR.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)
app.secret_key = os.environ.get("TRIBUANALISIS_SECRET_KEY") or os.urandom(32)
app.config.update(
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

ALLOWED_EXTENSIONS = {
    ".css",
    ".html",
    ".ico",
    ".pdf",
    ".xml",
    ".jpeg",
    ".jpg",
    ".js",
    ".png",
    ".svg",
    ".webp",
    ".xls",
    ".xlsx",
}

def db():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@contextmanager
def database():
    yield from db()


def init_db():
    with database() as connection:
        connection.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspaces(
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                profile_json TEXT NOT NULL DEFAULT '{}',
                empresa_json TEXT NOT NULL DEFAULT '{}',
                fin_json TEXT NOT NULL DEFAULT '{}',
                receipts_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS companies(
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ruc TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                activity TEXT NOT NULL DEFAULT '',
                data_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(user_id, ruc)
            );
            CREATE TABLE IF NOT EXISTS expenses(
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expense_id TEXT NOT NULL,
                company_ruc TEXT NOT NULL DEFAULT '',
                issue_date TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL DEFAULT 0,
                classification TEXT NOT NULL,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(user_id, expense_id)
            );
            CREATE INDEX IF NOT EXISTS idx_expenses_company_period
                ON expenses(user_id, company_ruc, issue_date);
            CREATE TABLE IF NOT EXISTS documents(
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                company_ruc TEXT NOT NULL DEFAULT '',
                expense_id TEXT,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                content BLOB NOT NULL,
                extracted_text TEXT NOT NULL DEFAULT '',
                extracted_json TEXT NOT NULL DEFAULT '{}',
                uploaded_at TEXT NOT NULL
            );
        """)


init_db()


@contextmanager
def transaction():
    with database() as connection:
        yield connection


def current_user_id():
    return session.get("user_id")


def login_required():
    user_id = current_user_id()
    if not user_id:
        return None, (jsonify(error="Inicia sesión para continuar."), 401)
    return user_id, None


def _xml_value(root, name):
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == name and element.text and element.text.strip():
            return element.text.strip()
    return ""


def _xml_party_value(root, party_name, field_name):
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != party_name:
            continue
        for child in element.iter():
            if child.tag.rsplit("}", 1)[-1] == field_name and child.text and child.text.strip():
                return child.text.strip()
    return ""


def _extract_invoice_xml(root):
    type_code = _xml_value(root, "InvoiceTypeCode")
    invoice_id = _xml_value(root, "ID")
    tax_amount = 0.0
    taxable_amount = 0.0
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "TaxSubtotal":
            continue
        scheme_ids = [
            child.text.strip() for child in element.iter()
            if child.tag.rsplit("}", 1)[-1] == "ID" and child.text and child.text.strip()
        ]
        if scheme_ids and "1000" not in scheme_ids:
            continue
        for child in element.iter():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "TaxAmount" and child.text:
                try:
                    tax_amount += float(child.text)
                except ValueError:
                    pass
            elif tag == "TaxableAmount" and child.text:
                try:
                    taxable_amount += float(child.text)
                except ValueError:
                    pass
    if tax_amount == 0:
        try:
            tax_amount = float(_xml_value(root, "TaxAmount") or 0)
        except ValueError:
            tax_amount = 0
    payable = _xml_value(root, "PayableAmount") or _xml_value(root, "TaxInclusiveAmount")
    try:
        total_amount = float(payable) if payable else 0
    except ValueError:
        total_amount = 0
    descriptions = [
        item.text.strip() for item in root.iter()
        if item.tag.rsplit("}", 1)[-1] == "Description" and item.text and item.text.strip()
    ]
    type_names = {"01": "Factura", "03": "Boleta de venta", "07": "Nota de crédito", "08": "Nota de débito"}
    currency_code = _xml_value(root, "DocumentCurrencyCode").upper()
    return {
        "fecha": _xml_value(root, "IssueDate"),
        "numero": invoice_id,
        "tipoComprobante": type_names.get(type_code, type_code),
        "moneda": currency_code if currency_code in {"PEN", "USD", "EUR"} else "",
        "proveedorRuc": _xml_party_value(root, "AccountingSupplierParty", "CompanyID"),
        "proveedor": _xml_party_value(root, "AccountingSupplierParty", "RegistrationName"),
        "rucReceptor": _xml_party_value(root, "AccountingCustomerParty", "CompanyID"),
        "empresa": _xml_party_value(root, "AccountingCustomerParty", "RegistrationName"),
        "concepto": "; ".join(dict.fromkeys(descriptions)),
        "baseImponible": taxable_amount,
        "igv": tax_amount,
        "importeTotal": total_amount,
        "estructuraXmlLeida": True,
    }


def _extract_text_fields(text):
    def amount_for(pattern):
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return 0
        value = match.group(1).replace(" ", "")
        if "," in value and "." in value:
            value = value.replace(",", "") if value.rfind(".") > value.rfind(",") else value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", ".")
        try:
            return float(value)
        except ValueError:
            return 0

    rucs = re.findall(r"\bR\.?\s*U\.?\s*C\.?\s*(?:N[°º.]?\s*)?[:\-]?\s*(\d{11})", text, re.IGNORECASE)
    date_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    voucher_match = re.search(r"\b([A-Z]\d{2,3}\s*-\s*\d{1,10})\b", text, re.IGNORECASE)
    return {
        "fecha": f"{date_match.group(3)}-{int(date_match.group(2)):02d}-{int(date_match.group(1)):02d}" if date_match else "",
        "numero": re.sub(r"\s+", "", voucher_match.group(1)).upper() if voucher_match else "",
        "proveedorRuc": rucs[0] if rucs else "",
        "rucReceptor": rucs[1] if len(rucs) > 1 else "",
        "importeTotal": amount_for(r"(?:importe\s+total|total\s+a\s+pagar|total)\s*[:\-]?\s*(?:S/?\s*)?([\d.,]+)"),
        "igv": amount_for(r"\bIGV\b\s*[:\-]?\s*(?:S/?\s*)?([\d.,]+)"),
        "textoReconocido": bool(text.strip()),
    }


def extract_document(filename, content):
    extension = Path(filename).suffix.lower()
    if extension not in {".xml", ".pdf", ".jpg", ".jpeg", ".png"}:
        raise ValueError("Formato no permitido. Utiliza XML, PDF, JPG o PNG.")
    if extension == ".xml":
        try:
            root = ET.fromstring(content)
            data = _extract_invoice_xml(root)
        except (ET.ParseError, DefusedXmlException) as error:
            raise ValueError("No se pudo interpretar el XML del comprobante.") from error
        text = " ".join(
            element.text.strip() for element in root.iter()
            if element.text and element.text.strip()
        )
        return text, data, ""

    text = ""
    warning = ""
    if extension == ".pdf":
        try:
            import pymupdf
        except ImportError:
            raise ValueError("Instala PyMuPDF para extraer texto de PDF.") from None
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.page_count > 100:
                raise ValueError("El PDF supera el máximo de 100 páginas.")
            text = "\n".join(page.get_text() for page in document)
    if extension in {".jpg", ".jpeg", ".png"} or not text.strip():
        try:
            from PIL import Image
            import pytesseract

            if os.environ.get("TESSERACT_CMD"):
                pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
            if extension == ".pdf":
                import pymupdf
                with pymupdf.open(stream=content, filetype="pdf") as document:
                    pages = []
                    for page in document:
                        if page.get_text().strip():
                            pages.append(page.get_text())
                        else:
                            image = Image.open(io.BytesIO(page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")))
                            pages.append(pytesseract.image_to_string(image, lang="spa+eng"))
                    text = "\n".join(pages)
            else:
                text = pytesseract.image_to_string(Image.open(io.BytesIO(content)), lang="spa+eng")
        except ImportError:
            warning = "OCR no disponible: instala Pillow, pytesseract y Tesseract con el idioma español."
        except Exception as error:
            if "tesseract" in str(error).lower() or error.__class__.__name__ == "TesseractNotFoundError":
                warning = "OCR no disponible: instala Tesseract y el paquete de idioma español."
            else:
                raise ValueError(f"No se pudo leer el documento: {error}") from error
    data = _extract_text_fields(text)
    if not text.strip() and not warning:
        warning = "No se pudo extraer texto del archivo; completa los campos revisando el comprobante."
    return text, data, warning


def ruc_api_token() -> str:
    token = os.environ.get("DECOLECTA_API_TOKEN", "").strip()
    if token:
        return token

    config_path = BASE_DIR / "config.json"
    if not config_path.exists():
        return ""
    try:
        settings = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        app.logger.exception("No se pudo leer la configuración local de consulta RUC.")
        raise RuntimeError("El archivo config.json no se pudo leer. Revisa su contenido.") from None
    if not isinstance(settings, dict):
        app.logger.error("La configuración local de consulta RUC debe ser un objeto JSON.")
        raise RuntimeError("El archivo config.json no tiene el formato esperado.")
    token = settings.get("DECOLECTA_API_TOKEN", "")
    return token.strip() if isinstance(token, str) else ""


def is_valid_ruc(ruc: str) -> bool:
    if not re.fullmatch(r"\d{11}", ruc):
        return False
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    check_digit = 11 - sum(int(digit) * weight for digit, weight in zip(ruc[:10], weights)) % 11
    expected = 0 if check_digit == 10 else 1 if check_digit == 11 else check_digit
    return int(ruc[10]) == expected


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


def _json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValueError("El cuerpo de la solicitud debe ser un objeto JSON.")
    return body


@app.post("/api/register")
def register():
    try:
        body = _json_body()
    except (ValueError, TypeError):
        return jsonify(error="La solicitud de registro no es válida."), 400
    name = str(body.get("name") or "").strip()
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    if len(name) < 2 or len(name) > 160 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify(error="Ingresa un nombre y correo válidos."), 400
    if len(password) < 6 or len(password) > 256:
        return jsonify(error="La contraseña debe tener entre 6 y 256 caracteres."), 400
    try:
        with database() as connection:
            cursor = connection.execute(
                "INSERT INTO users(email,name,password_hash,created_at) VALUES(?,?,?,?)",
                (email, name, generate_password_hash(password),
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            user_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO workspaces(user_id,profile_json,updated_at) VALUES(?,?,?)",
                (user_id, json.dumps({"name": name, "email": email}), datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
    except sqlite3.IntegrityError:
        return jsonify(error="Ya existe una cuenta con ese correo."), 409
    session.clear()
    session["user_id"] = user_id
    session["email"] = email
    return jsonify(user={"id": user_id, "name": name, "email": email}), 201


@app.post("/api/login")
def login():
    try:
        body = _json_body()
    except (ValueError, TypeError):
        return jsonify(error="La solicitud de inicio de sesión no es válida."), 400
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    with database() as connection:
        user = connection.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Correo o contraseña incorrectos."), 401
    session.clear()
    session["user_id"] = user["id"]
    session["email"] = user["email"]
    return jsonify(user={"id": user["id"], "name": user["name"], "email": user["email"]})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/session")
def active_session():
    user_id, error_response = login_required()
    if error_response:
        return error_response
    with database() as connection:
        user = connection.execute("SELECT id,name,email FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        session.clear()
        return jsonify(error="La sesión ya no tiene una cuenta activa."), 401
    return jsonify(user=dict(user))


@app.post("/api/change-password")
def change_password():
    user_id, error_response = login_required()
    if error_response:
        return error_response
    try:
        body = _json_body()
    except (ValueError, TypeError):
        return jsonify(error="La solicitud no es válida."), 400
    password = str(body.get("password") or "")
    if not 6 <= len(password) <= 256:
        return jsonify(error="La contraseña debe tener entre 6 y 256 caracteres."), 400
    with database() as connection:
        connection.execute("UPDATE users SET password_hash=? WHERE id=?",
                           (generate_password_hash(password), user_id))
    return jsonify(ok=True)


def _evaluate_workspace_cases(cases):
    ordered_cases = sorted(
        cases,
        key=lambda item: (str(item.get("fecha") or ""), str(item.get("id") or "")),
    )
    processed = []
    for case in ordered_cases:
        item = dict(case)
        expense_id = str(item.get("id") or "").strip()
        if not expense_id or len(expense_id) > 100:
            raise ValueError("Cada gasto debe tener un identificador válido.")
        company_ruc = str(item.get("empresaRuc") or item.get("ruc") or "").strip()
        prior = [
            row for row in processed
            if str(row.get("empresaRuc") or row.get("ruc") or "") == company_ruc
        ]
        try:
            evaluation = evaluate_expense(item, prior)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"No se pudo evaluar el gasto {expense_id}: {error}") from error
        item["evaluation"] = evaluation
        item["estado"] = evaluation["status"]
        item["clasificacion"] = evaluation["label"]
        item["deducible"] = evaluation["deductibleAmount"]
        item["noDeducible"] = evaluation["nonDeductibleAmount"]
        processed.append(item)
    return processed


@app.get("/api/workspace")
def get_workspace():
    user_id, error_response = login_required()
    if error_response:
        return error_response
    with database() as connection:
        workspace = connection.execute(
            "SELECT profile_json,empresa_json,fin_json,receipts_json FROM workspaces WHERE user_id=?",
            (user_id,),
        ).fetchone()
        rows = connection.execute(
            "SELECT data_json FROM expenses WHERE user_id=? ORDER BY issue_date DESC,updated_at DESC",
            (user_id,),
        ).fetchall()
        company_rows = connection.execute(
            "SELECT ruc,name,activity,data_json FROM companies WHERE user_id=? ORDER BY name,ruc",
            (user_id,),
        ).fetchall()
        documents = connection.execute(
            """SELECT id,company_ruc,expense_id,filename,content_type,extracted_json,uploaded_at
               FROM documents WHERE user_id=? ORDER BY uploaded_at DESC""",
            (user_id,),
        ).fetchall()
    stored_receipts = json.loads(workspace["receipts_json"]) if workspace else []
    stored_ids = {item.get("id") for item in stored_receipts if isinstance(item, dict) and item.get("id")}
    document_receipts = [{
        "id": row["id"],
        "name": row["filename"],
        "empresaRuc": row["company_ruc"],
        "expenseId": row["expense_id"],
        "contentType": row["content_type"],
        "datosExtraidos": json.loads(row["extracted_json"]),
        "status": "Pendiente de consulta oficial SUNAT",
        "date": row["uploaded_at"],
        "url": f"/api/documents/{row['id']}",
    } for row in documents if row["id"] not in stored_ids]
    companies = []
    for row in company_rows:
        company = json.loads(row["data_json"])
        company.update(ruc=row["ruc"], name=row["name"], activity=row["activity"])
        companies.append(company)
    try:
        cases = _evaluate_workspace_cases([
            json.loads(row["data_json"]) for row in rows
        ])
    except ValueError as error:
        app.logger.exception("No se pudo reevaluar el historial guardado.")
        return jsonify(error=str(error)), 500
    return jsonify(
        profile=json.loads(workspace["profile_json"]) if workspace else {},
        empresa=json.loads(workspace["empresa_json"]) if workspace else {},
        fin=json.loads(workspace["fin_json"]) if workspace else {},
        cases=list(reversed(cases)),
        companies=companies,
        receipts=stored_receipts + document_receipts,
    )


def _clean_workspace_list(value, field_name):
    if not isinstance(value, list) or len(value) > 10000:
        raise ValueError(f"El campo {field_name} debe ser una lista de hasta 10 000 registros.")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Todos los elementos de {field_name} deben ser objetos.")
    return value


def _expense_batch_id(item):
    if not isinstance(item, dict) or item.get("origen") != "Importación Excel":
        return None
    metadata = item.get("loteExcel") or {}
    return str(metadata.get("id") or "importacion-anterior")


def _batch_file_path(user_id, batch_id, suffix):
    try:
        normalized_id = uuid.UUID(str(batch_id)).hex
    except (ValueError, AttributeError, TypeError):
        return None
    if suffix not in {".xlsx", ".xls"}:
        return None
    return CASE_BATCH_DIR / str(user_id) / f"{normalized_id}{suffix}"


def _remove_batch_file(user_id, batch_id):
    removed = False
    for suffix in (".xlsx", ".xls"):
        path = _batch_file_path(user_id, batch_id, suffix)
        if path is None:
            continue
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


@app.put("/api/workspace")
def save_workspace():
    user_id, error_response = login_required()
    if error_response:
        return error_response
    try:
        body = _json_body()
        cases = _clean_workspace_list(body.get("cases", []), "cases")
        companies = _clean_workspace_list(body.get("companies", []), "companies")
        if any(
            not re.fullmatch(r"\d{11}", str(company.get("ruc") or "").strip())
            or not str(company.get("name") or company.get("razonSocial") or "").strip()
            for company in companies
        ):
            raise ValueError("Cada empresa debe tener un RUC de 11 dígitos y una razón social; la evaluación verifica el dígito de control.")
        for field in ("profile", "empresa", "fin"):
            if not isinstance(body.get(field, {}), dict):
                raise ValueError(f"El campo {field} debe ser un objeto.")
        if not isinstance(body.get("receipts", []), list):
            raise ValueError("El campo receipts debe ser una lista.")
    except (ValueError, TypeError) as error:
        return jsonify(error=str(error)), 400

    encoded = json.dumps(body, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > 10 * 1024 * 1024:
        return jsonify(error="El espacio de trabajo supera el límite de 10 MB."), 413
    try:
        processed = _evaluate_workspace_cases(cases)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    profile = body.get("profile", {})
    empresa = body.get("empresa", {})
    fin = body.get("fin", {})
    try:
        with database() as connection:
            connection.execute(
                """INSERT INTO workspaces(user_id,profile_json,empresa_json,fin_json,receipts_json,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET profile_json=excluded.profile_json,
                   empresa_json=excluded.empresa_json,fin_json=excluded.fin_json,
                   receipts_json=excluded.receipts_json,updated_at=excluded.updated_at""",
                (user_id, json.dumps(profile, ensure_ascii=False), json.dumps(empresa, ensure_ascii=False),
                 json.dumps(fin, ensure_ascii=False), json.dumps(body.get("receipts", []), ensure_ascii=False), stamp),
            )
            for company in companies:
                company_ruc = str(company.get("ruc") or "").strip()
                name = str(company.get("name") or company.get("razonSocial") or "").strip()
                activity = str(company.get("activity") or company.get("actividadEconomica") or "").strip()
                connection.execute(
                    """INSERT INTO companies(user_id,ruc,name,activity,data_json)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(user_id,ruc) DO UPDATE SET
                       name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE companies.name END,
                       activity=CASE WHEN excluded.activity<>'' THEN excluded.activity ELSE companies.activity END,
                       data_json=excluded.data_json""",
                    (user_id, company_ruc, name, activity,
                     json.dumps(company, ensure_ascii=False)),
                )
            for item in processed:
                company_ruc = str(item.get("empresaRuc") or item.get("ruc") or "").strip()
                name = str(item.get("empresa") or "").strip()
                connection.execute(
                    """INSERT INTO expenses(user_id,expense_id,company_ruc,issue_date,amount,
                       classification,data_json,updated_at) VALUES(?,?,?,?,?,?,?,?)
                       ON CONFLICT(user_id,expense_id) DO UPDATE SET
                       company_ruc=excluded.company_ruc,issue_date=excluded.issue_date,
                       amount=excluded.amount,classification=excluded.classification,
                       data_json=excluded.data_json,updated_at=excluded.updated_at""",
                    (user_id, str(item["id"]), company_ruc, str(item.get("fecha") or ""),
                     float(item.get("monto") or 0), item["evaluation"]["status"],
                     json.dumps(item, ensure_ascii=False), stamp),
                )
                connection.execute(
                    "UPDATE documents SET company_ruc=? WHERE user_id=? AND expense_id=?",
                    (company_ruc, user_id, str(item["id"])),
                )
                if company_ruc:
                    connection.execute(
                        """INSERT INTO companies(user_id,ruc,name,activity,data_json)
                           VALUES(?,?,?,?,?)
                           ON CONFLICT(user_id,ruc) DO UPDATE SET
                           name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE companies.name END,
                           activity=CASE WHEN excluded.activity<>'' THEN excluded.activity ELSE companies.activity END""",
                        (user_id, company_ruc, name, str(item.get("empresaActividad") or ""),
                         json.dumps({"name": name, "activity": item.get("empresaActividad", "")}, ensure_ascii=False)),
                    )
    except (sqlite3.Error, ValueError, TypeError):
        app.logger.exception("No se pudo guardar el espacio de trabajo.")
        return jsonify(error="No se pudo guardar la información en la base de datos."), 500
    return jsonify(ok=True, cases=processed)


@app.post("/api/case-batches")
def save_case_batch():
    user_id, error_response = login_required()
    if error_response:
        return error_response
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(error="Adjunta el archivo Excel que se va a importar."), 400
    filename = secure_filename(uploaded.filename or "")
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in {".xlsx", ".xls"}:
        return jsonify(error="El archivo de casos debe ser .xlsx o .xls."), 400

    batch_id = uuid.uuid4().hex
    user_directory = CASE_BATCH_DIR / str(user_id)
    path = _batch_file_path(user_id, batch_id, suffix)
    try:
        user_directory.mkdir(parents=True, exist_ok=True)
        uploaded.save(path)
        if path.stat().st_size == 0:
            path.unlink()
            return jsonify(error="El archivo Excel está vacío."), 400
    except OSError:
        app.logger.exception("No se pudo guardar el archivo Excel del lote.")
        return jsonify(error="No se pudo archivar el Excel de casos de prueba."), 500
    return jsonify(
        id=batch_id,
        name=filename,
        date=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    ), 201


@app.post("/api/expense-import-preview")
def expense_import_preview():
    _, error_response = login_required()
    if error_response:
        return error_response
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(error="Adjunta el archivo Excel que se va a analizar."), 400
    filename = secure_filename(uploaded.filename or "")
    if Path(filename).suffix.lower() != ".xlsx":
        return jsonify(error="La lectura completa del Registro de Compras SIRE requiere un archivo .xlsx."), 400
    content = uploaded.read()
    if not content:
        return jsonify(error="El archivo Excel está vacío."), 400
    try:
        result = parse_purchase_workbook(content)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    return jsonify(result)


@app.delete("/api/expense-batches/<batch_id>")
def delete_expense_batch(batch_id):
    user_id, error_response = login_required()
    if error_response:
        return error_response
    try:
        with database() as connection:
            rows = connection.execute(
                "SELECT expense_id,data_json FROM expenses WHERE user_id=?",
                (user_id,),
            ).fetchall()
            expense_ids = [
                row["expense_id"] for row in rows
                if _expense_batch_id(json.loads(row["data_json"])) == batch_id
            ]
            if not expense_ids and not _remove_batch_file(user_id, batch_id):
                return jsonify(error="No se encontró ese lote en esta cuenta."), 404
            if expense_ids:
                placeholders = ",".join("?" for _ in expense_ids)
                connection.execute(
                    f"UPDATE documents SET expense_id=NULL WHERE user_id=? AND expense_id IN ({placeholders})",
                    [user_id, *expense_ids],
                )
                connection.execute(
                    f"DELETE FROM expenses WHERE user_id=? AND expense_id IN ({placeholders})",
                    [user_id, *expense_ids],
                )
                remaining = connection.execute(
                    "SELECT data_json FROM expenses WHERE user_id=?",
                    (user_id,),
                ).fetchall()
                if not any(
                    _expense_batch_id(json.loads(row["data_json"])) == batch_id
                    for row in remaining
                ):
                    _remove_batch_file(user_id, batch_id)
    except (sqlite3.Error, OSError, ValueError):
        app.logger.exception("No se pudo eliminar el lote de gastos.")
        return jsonify(error="No se pudo completar la eliminación del lote."), 500
    return jsonify(ok=True, deleted=len(expense_ids))


@app.delete("/api/expenses")
def delete_all_expenses():
    user_id, error_response = login_required()
    if error_response:
        return error_response
    try:
        with database() as connection:
            rows = connection.execute(
                "SELECT expense_id,data_json FROM expenses WHERE user_id=?",
                (user_id,),
            ).fetchall()
            batch_ids = {
                _expense_batch_id(json.loads(row["data_json"]))
                for row in rows
            } - {None}
            connection.execute(
                "UPDATE documents SET expense_id=NULL WHERE user_id=?",
                (user_id,),
            )
            connection.execute("DELETE FROM expenses WHERE user_id=?", (user_id,))
            for batch_id in batch_ids:
                _remove_batch_file(user_id, batch_id)
    except (sqlite3.Error, OSError, ValueError):
        app.logger.exception("No se pudo eliminar el historial de gastos.")
        return jsonify(error="No se pudo completar la eliminación del historial."), 500
    return jsonify(ok=True, deleted=len(rows))


@app.delete("/api/expenses/<expense_id>")
def delete_expense(expense_id):
    user_id, error_response = login_required()
    if error_response:
        return error_response
    try:
        with database() as connection:
            row = connection.execute(
                "SELECT data_json FROM expenses WHERE user_id=? AND expense_id=?",
                (user_id, expense_id),
            ).fetchone()
            if row is None:
                return jsonify(error="No se encontró el gasto de esta cuenta."), 404
            batch_id = _expense_batch_id(json.loads(row["data_json"]))
            connection.execute(
                "UPDATE documents SET expense_id=NULL WHERE user_id=? AND expense_id=?",
                (user_id, expense_id),
            )
            connection.execute(
                "DELETE FROM expenses WHERE user_id=? AND expense_id=?",
                (user_id, expense_id),
            )
            if batch_id:
                remaining = connection.execute(
                    "SELECT data_json FROM expenses WHERE user_id=?",
                    (user_id,),
                ).fetchall()
                if not any(
                    _expense_batch_id(json.loads(item["data_json"])) == batch_id
                    for item in remaining
                ):
                    _remove_batch_file(user_id, batch_id)
    except (sqlite3.Error, OSError, ValueError):
        app.logger.exception("No se pudo eliminar el gasto.")
        return jsonify(error="No se pudo completar la eliminación del gasto."), 500
    return jsonify(ok=True)


@app.post("/api/evaluate")
def evaluate():
    user_id, error_response = login_required()
    if error_response:
        return error_response
    try:
        expense = _json_body()
    except (ValueError, TypeError):
        return jsonify(error="La solicitud de evaluación no es válida."), 400
    company_ruc = str(expense.get("empresaRuc") or expense.get("ruc") or "")
    issue_year = str(expense.get("fecha") or "")[:4]
    with database() as connection:
        rows = connection.execute(
            "SELECT data_json FROM expenses WHERE user_id=? AND company_ruc=? AND issue_date LIKE ?",
            (user_id, company_ruc, f"{issue_year}%"),
        ).fetchall()
    previous = [json.loads(row["data_json"]) for row in rows]
    try:
        result = evaluate_expense(expense, previous)
    except (TypeError, ValueError, OverflowError) as error:
        return jsonify(error=f"No se pudo evaluar la información: {error}"), 400
    return jsonify(result)


@app.post("/api/documents/extract")
def extract_uploaded_documents():
    user_id, error_response = login_required()
    if error_response:
        return error_response
    files = request.files.getlist("documents") or request.files.getlist("document")
    if not files or len(files) > 10:
        return jsonify(error="Selecciona entre 1 y 10 documentos."), 400
    results = []
    for uploaded in files:
        if not uploaded.filename:
            continue
        filename = secure_filename(uploaded.filename)
        content = uploaded.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            return jsonify(error=f"{filename}: supera el límite de 20 MB."), 413
        try:
            text, extracted, warning = extract_document(filename, content)
        except (ValueError, ET.ParseError, OSError) as error:
            return jsonify(error=f"{filename}: {error}"), 400
        results.append({
            "name": filename,
            "contentType": uploaded.mimetype or "application/octet-stream",
            "datosExtraidos": extracted,
            "warning": warning,
        })
    if not results:
        return jsonify(error="No se recibieron archivos válidos."), 400
    return jsonify(documents=results)


@app.post("/api/documents")
def save_document():
    user_id, error_response = login_required()
    if error_response:
        return error_response
    uploaded = request.files.get("document")
    if not uploaded or not uploaded.filename:
        return jsonify(error="Selecciona un documento."), 400
    filename = secure_filename(uploaded.filename)
    content = uploaded.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        return jsonify(error="El documento supera el límite de 20 MB."), 413
    try:
        text, extracted, warning = extract_document(filename, content)
    except (ValueError, ET.ParseError, OSError) as error:
        return jsonify(error=str(error)), 400
    document_id = uuid.uuid4().hex
    company_ruc = str(request.form.get("companyRuc") or "").strip()
    expense_id = str(request.form.get("expenseId") or "").strip()
    if not is_valid_ruc(company_ruc):
        return jsonify(error="Asocia el documento con un RUC de empresa válido."), 400
    if expense_id:
        with database() as connection:
            expense = connection.execute(
                "SELECT company_ruc FROM expenses WHERE user_id=? AND expense_id=?",
                (user_id, expense_id),
            ).fetchone()
        if not expense:
            return jsonify(error="No se encontró el gasto de esta cuenta al que se quiere asociar el documento."), 404
        if expense["company_ruc"] != company_ruc:
            return jsonify(error="El RUC de empresa del documento no coincide con el gasto seleccionado."), 400
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with database() as connection:
        connection.execute(
            """INSERT INTO documents(id,user_id,company_ruc,expense_id,filename,content_type,
               content,extracted_text,extracted_json,uploaded_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (document_id, user_id, company_ruc, expense_id or None, filename,
             uploaded.mimetype or "application/octet-stream", sqlite3.Binary(content),
             text[:100000], json.dumps(extracted, ensure_ascii=False), timestamp),
        )
    return jsonify(
        id=document_id, name=filename, empresaRuc=company_ruc, expenseId=expense_id,
        contentType=uploaded.mimetype or "application/octet-stream", datosExtraidos=extracted,
        size=len(content), warning=warning, status="Pendiente de consulta oficial SUNAT",
        date=timestamp, url=f"/api/documents/{document_id}",
    ), 201


@app.get("/api/documents/<document_id>")
def get_document(document_id):
    user_id, error_response = login_required()
    if error_response:
        return error_response
    with database() as connection:
        document = connection.execute(
            "SELECT filename,content_type,content FROM documents WHERE id=? AND user_id=?",
            (document_id, user_id),
        ).fetchone()
    if not document:
        abort(404)
    return send_file(io.BytesIO(document["content"]), mimetype=document["content_type"],
                     as_attachment=False, download_name=document["filename"])


@app.get("/api/expense-template.xlsx")
def expense_template():
    return send_from_directory(
        TEMPLATE_DIR,
        "Tribuanalisis_Plantilla_Gastos_Vacia.xlsx",
        as_attachment=True,
        download_name="Tribuanalisis_Plantilla_Gastos_Vacia.xlsx",
    )


@app.get("/api/case-test-template.xlsx")
def case_test_template():
    path = BASE_DIR / "casos_prueba" / "Tribuanalisis_15_Casos_Gastos_Ejemplo.xlsx"
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        app.logger.error("No se encontró el Excel de casos de prueba: %s", path)
        return jsonify(error="No se encontró el archivo de casos de prueba."), 404
    except OSError:
        app.logger.exception("No se pudo leer el Excel de casos de prueba.")
        return jsonify(error="No se pudo leer el archivo de casos de prueba."), 500
    return send_file(
        io.BytesIO(content),
        as_attachment=True,
        download_name="Tribuanalisis_15_Casos_Gastos_Ejemplo.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/ruc/<ruc>")
def lookup_ruc(ruc: str):
    if not is_valid_ruc(ruc):
        return jsonify(error="Ingresa un RUC válido de 11 dígitos."), 400

    try:
        token = ruc_api_token()
    except RuntimeError as error:
        return jsonify(error=str(error)), 500
    if not token:
        return jsonify(
            error="La consulta automática aún no está activada. Configura el token del servicio en config.json."
        ), 503

    query = urlencode({"numero": ruc})
    request = Request(
        f"https://api.decolecta.com/v1/sunat/ruc/full?{query}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Referer": "https://decolecta.com/",
            "User-Agent": "Tribuanalisis/1.0",
        },
    )

    try:
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        messages = {
            401: "El token de consulta no es válido. Revisa la configuración del servicio.",
            403: "El servicio no autorizó la consulta. Revisa tu cuenta o el límite de uso.",
            404: "No se encontró ese RUC en la consulta.",
            422: "El servicio rechazó el formato del RUC.",
            429: "Se alcanzó el límite de consultas. Inténtalo más tarde.",
        }
        message = messages.get(error.code, "El servicio de consulta RUC no está disponible.")
        if error.code not in messages:
            app.logger.warning("El proveedor de consulta RUC respondió con HTTP %s.", error.code)
        return jsonify(error=message), 502 if error.code not in (404, 422) else error.code
    except (TimeoutError, socket.timeout):
        app.logger.warning("Se agotó el tiempo de espera al consultar el proveedor RUC.")
        return jsonify(error="La consulta tardó demasiado. Inténtalo nuevamente."), 504
    except URLError:
        app.logger.exception("No se pudo conectar con el proveedor de consulta RUC.")
        return jsonify(error="No se pudo conectar con el servicio de consulta RUC."), 502
    except (UnicodeDecodeError, json.JSONDecodeError):
        app.logger.exception("El proveedor RUC devolvió una respuesta inválida.")
        return jsonify(error="El servicio devolvió una respuesta que no se pudo interpretar."), 502

    if not isinstance(data, dict):
        app.logger.error("El proveedor RUC devolvió un formato de respuesta inesperado.")
        return jsonify(error="El servicio devolvió una respuesta que no se pudo interpretar."), 502

    def first_value(*keys):
        return next((data.get(key) for key in keys if data.get(key) not in (None, "")), "")

    name = first_value("razon_social", "razonSocial", "nombre")
    activity = first_value(
        "actividad_economica_principal",
        "actividadEconomicaPrincipal",
        "actividad_economica",
        "actividadEconomica",
    )
    if not name:
        return jsonify(error="El servicio no devolvió la razón social para ese RUC."), 502

    activities = data.get("actividades_economicas")
    if isinstance(activities, list):
        activity_values = [
            item.get("descripcion") or item.get("nombre") or item.get("actividad")
            for item in activities
            if isinstance(item, dict)
        ]
        activity_values = [value for value in activity_values if value]
        activity = activity or (activity_values[0] if activity_values else "")
    else:
        activity_values = []
    secondary_1 = first_value(
        "actividad_economica_secundaria_1",
        "actividadEconomicaSecundaria1",
        "actividad_secundaria_1",
        "actividadSecundaria1",
    )
    secondary_2 = first_value(
        "actividad_economica_secundaria_2",
        "actividadEconomicaSecundaria2",
        "actividad_secundaria_2",
        "actividadSecundaria2",
    )
    if not secondary_1 and len(activity_values) > 1:
        secondary_1 = activity_values[1]
    if not secondary_2 and len(activity_values) > 2:
        secondary_2 = activity_values[2]

    return jsonify(
        ruc=first_value("numero_documento", "numeroDocumento") or ruc,
        razonSocial=name,
        actividadEconomica=activity,
        actividadEconomicaPrincipal=activity,
        actividadEconomicaSecundaria1=secondary_1,
        actividadEconomicaSecundaria2=secondary_2,
        codigoCIIU=first_value("codigo_ciiu", "codigoCiiu", "ciiu", "codigo_actividad_economica"),
        estado=data.get("estado") or "",
        condicion=data.get("condicion") or "",
        tipo=data.get("tipo") or "",
        comercioExterior=data.get("comercio_exterior") or data.get("comercioExterior") or "",
        source="Proveedor externo Decolecta basado en datos SUNAT; no es una consulta oficial directa.",
        consultedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        official=False,
    )


@app.get("/<path:filename>")
def public_file(filename):
    requested_path = Path(filename)
    if (
        requested_path.suffix.lower() not in ALLOWED_EXTENSIONS
        or any(part.startswith(".") for part in requested_path.parts)
    ):
        abort(404)
    return send_from_directory(BASE_DIR, filename)


if __name__ == "__main__":
    address = "http://127.0.0.1:5000/"
    Timer(1, lambda: webbrowser.open(address)).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
