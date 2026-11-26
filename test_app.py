import json
import os
import tempfile
import unittest
from io import BytesIO
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

_test_root = tempfile.TemporaryDirectory()
os.environ["TRIBUANALISIS_INSTANCE"] = _test_root.name
os.environ["TRIBUANALISIS_DB"] = str(Path(_test_root.name) / "test.db")
os.environ["TRIBUANALISIS_UPLOAD_DIR"] = str(Path(_test_root.name) / "uploads")

from app import (
    CASE_BATCH_DIR,
    TEMPLATE_DIR,
    PostgresConnection,
    _get_instance_dir,
    _postgres_dsn,
    app,
    init_db,
    is_valid_ruc,
)
from sire_import import normalize_header, parse_purchase_workbook


VALID_RUC = "20100070970"
INVOICE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
  <IssueDate>2026-01-02</IssueDate>
  <InvoiceTypeCode>01</InvoiceTypeCode>
  <ID>F001-123</ID>
  <DocumentCurrencyCode>PEN</DocumentCurrencyCode>
  <AccountingSupplierParty><Party><PartyLegalEntity>
    <RegistrationName>Proveedor de prueba</RegistrationName><CompanyID>20100070970</CompanyID>
  </PartyLegalEntity></Party></AccountingSupplierParty>
  <AccountingCustomerParty><Party><PartyLegalEntity>
    <RegistrationName>Empresa receptora</RegistrationName><CompanyID>20100070970</CompanyID>
  </PartyLegalEntity></Party></AccountingCustomerParty>
  <LegalMonetaryTotal><PayableAmount>118.00</PayableAmount></LegalMonetaryTotal>
  <InvoiceLine><Item><Description>Mantenimiento de equipos</Description></Item></InvoiceLine>
</Invoice>"""


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        database_path = Path(os.environ["TRIBUANALISIS_DB"])
        if database_path.exists():
            database_path.unlink()
        init_db()
        app.config.update(TESTING=True, SECRET_KEY="test-session-secret")
        self.client = app.test_client()

    def register(self, email):
        response = self.client.post("/api/register", json={
            "name": "Usuario de prueba",
            "email": email,
            "password": "contrasena123",
        })
        self.assertEqual(response.status_code, 201)

    def test_vercel_uses_writable_temporary_instance_directory(self):
        configured_instance = os.environ.pop("TRIBUANALISIS_INSTANCE", None)
        try:
            with patch.dict(os.environ, {"VERCEL": "1"}):
                self.assertEqual(_get_instance_dir(), Path("/tmp/tribuanalisis"))
        finally:
            if configured_instance is not None:
                os.environ["TRIBUANALISIS_INSTANCE"] = configured_instance

    def test_postgres_adapter_uses_driver_placeholders_and_pooler_ssl(self):
        class FakeConnection:
            def execute(self, query, parameters):
                self.query = query
                self.parameters = parameters
                return self

        fake_connection = FakeConnection()
        PostgresConnection(fake_connection).execute(
            "SELECT id FROM users WHERE email=?",
            ("user@example.test",),
        )
        self.assertEqual(fake_connection.query, "SELECT id FROM users WHERE email=%s")
        self.assertEqual(fake_connection.parameters, ("user@example.test",))

        dsn = _postgres_dsn(
            "postgresql://user:password@db.example.test:6543/app?pgbouncer=true"
        )
        self.assertNotIn("pgbouncer", dsn)
        self.assertIn("sslmode=require", dsn)

    def test_login_banner_is_served_from_the_deployed_app(self):
        response = self.client.get("/assets/images/login-tributario.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.mimetype.startswith("image/"))
        self.assertGreater(len(response.data), 0)
        response.close()

    def test_excel_preview_requires_a_server_session(self):
        guest_client = app.test_client()
        denied = guest_client.post("/api/expense-import-preview")
        self.assertEqual(denied.status_code, 401)

        self.register("excel-session@example.test")
        authorized = self.client.post("/api/expense-import-preview")
        self.assertEqual(authorized.status_code, 400)
        self.assertIn("Adjunta el archivo Excel", authorized.json["error"])

    def test_workspace_is_persisted_per_account(self):
        self.register("first@example.test")
        response = self.client.put("/api/workspace", json={
            "profile": {"name": "Usuario de prueba", "email": "first@example.test"},
            "empresa": {},
            "fin": {},
            "receipts": [],
            "cases": [{
                "id": "CAS-1",
                "empresaRuc": VALID_RUC,
                "empresa": "Empresa A",
                "proveedorRuc": VALID_RUC,
                "proveedor": "Proveedor",
                "numero": "F001-123",
                "fecha": "2026-01-02",
                "monto": 118,
                "concepto": "Servicio de mantenimiento",
                "descripcion": "Mantenimiento de equipos de producción",
                "clasificacion": "Deducible",
                "estado": "deducible",
            }],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["cases"][0]["evaluation"]["status"], "condicionado")

        self.client.post("/api/logout")
        self.register("second@example.test")
        other_workspace = self.client.get("/api/workspace")
        self.assertEqual(other_workspace.status_code, 200)
        self.assertEqual(other_workspace.json["cases"], [])

    def test_workspace_read_recalculates_saved_evaluations(self):
        self.register("reevaluate@example.test")
        case = {
            "id": "CAS-OFFICE-SUPPLIES",
            "empresaRuc": VALID_RUC,
            "empresa": "Empresa A",
            "empresaActividad": "Comercio",
            "proveedorRuc": VALID_RUC,
            "proveedor": "Proveedor A",
            "numero": "F001-460",
            "tipoComprobante": "Factura",
            "fecha": "2026-11-23",
            "fechaServicio": "2026-11-23",
            "monto": 118,
            "concepto": "Compra de insumos de oficina",
            "descripcionDetalladaGasto": "Compra de insumos de oficina",
            "descripcion": "Insumos utilizados por el área administrativa en tareas de gestión.",
            "evidencia": "Orden interna y constancia de recepción disponibles.",
            "rucReceptor": VALID_RUC,
        }
        saved = self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "receipts": [],
            "cases": [case],
        })
        self.assertEqual(saved.status_code, 200)

        with app.app_context():
            from app import database

            with database() as connection:
                row = connection.execute(
                    "SELECT user_id,data_json FROM expenses WHERE expense_id=?",
                    (case["id"],),
                ).fetchone()
                old_record = json.loads(row["data_json"])
                old_record["evaluation"]["status"] = "condicionado"
                old_record["evaluation"]["label"] = "Condicionado"
                connection.execute(
                    "UPDATE expenses SET data_json=? WHERE user_id=? AND expense_id=?",
                    (json.dumps(old_record), row["user_id"], case["id"]),
                )

        loaded = self.client.get("/api/workspace")
        self.assertEqual(loaded.status_code, 200)
        refreshed_case = loaded.json["cases"][0]
        self.assertEqual(refreshed_case["evaluation"]["status"], "deducible")
        self.assertIn("oficina", refreshed_case["evaluation"]["expenseCategory"].lower())

    def test_saving_an_edited_case_updates_the_existing_record_and_reevaluates_it(self):
        self.register("edit-expense@example.test")
        case = {
            "id": "CAS-EDIT",
            "empresaRuc": VALID_RUC,
            "empresa": "Empresa A",
            "empresaActividad": "Comercio",
            "proveedorRuc": VALID_RUC,
            "proveedor": "Proveedor A",
            "numero": "F001-460",
            "tipoComprobante": "Factura",
            "fecha": "2026-11-23",
            "monto": 118,
            "concepto": "Compra de insumos de oficina",
            "descripcionDetalladaGasto": "Compra de insumos de oficina",
            "descripcion": "Insumos utilizados por el área administrativa en tareas de gestión.",
            "evidencia": "Orden interna y constancia de recepción.",
            "rucReceptor": VALID_RUC,
        }
        workspace = {
            "profile": {},
            "empresa": {},
            "fin": {},
            "receipts": [],
            "cases": [case],
        }
        first_save = self.client.put("/api/workspace", json=workspace)
        self.assertEqual(first_save.status_code, 200)
        self.assertEqual(first_save.json["cases"][0]["evaluation"]["status"], "deducible")

        edited_case = {
            **case,
            "concepto": "Multa administrativa municipal",
            "descripcionDetalladaGasto": "Multa administrativa municipal",
            "monto": 250,
        }
        second_save = self.client.put("/api/workspace", json={**workspace, "cases": [edited_case]})
        self.assertEqual(second_save.status_code, 200)
        self.assertEqual(second_save.json["cases"][0]["evaluation"]["status"], "no_deducible")

        saved_cases = self.client.get("/api/workspace").json["cases"]
        self.assertEqual(len(saved_cases), 1)
        self.assertEqual(saved_cases[0]["id"], "CAS-EDIT")
        self.assertEqual(saved_cases[0]["monto"], 250)
        self.assertEqual(saved_cases[0]["concepto"], "Multa administrativa municipal")

    def test_server_overrides_client_classification(self):
        self.register("classification@example.test")
        response = self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "receipts": [],
            "cases": [{
                "id": "CAS-PROHIBITED",
                "empresaRuc": VALID_RUC,
                "empresa": "Empresa A",
                "fecha": "2026-01-02",
                "monto": 250,
                "concepto": "Multa municipal",
                "clasificacion": "Deducible",
                "estado": "deducible",
            }],
        })

        self.assertEqual(response.status_code, 200)
        item = response.json["cases"][0]
        self.assertEqual(item["evaluation"]["status"], "no_deducible")
        self.assertEqual(item["clasificacion"], "No deducible")

    def test_company_is_persisted_without_expenses_and_workspace_saves_do_not_drop_records(self):
        self.register("companies@example.test")
        company = {
            "ruc": VALID_RUC,
            "name": "Empresa independiente",
            "activity": "Servicios de consultoría",
        }
        response = self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "companies": [company],
            "cases": [],
            "receipts": [],
        })

        self.assertEqual(response.status_code, 200)
        workspace = self.client.get("/api/workspace").json
        self.assertEqual(workspace["companies"][0]["ruc"], VALID_RUC)
        self.assertEqual(workspace["cases"], [])

        first_expense = {
            "id": "CAS-PERSIST",
            "empresaRuc": VALID_RUC,
            "empresa": "Empresa independiente",
            "proveedorRuc": VALID_RUC,
            "proveedor": "Proveedor",
            "numero": "F001-321",
            "fecha": "2026-02-01",
            "monto": 50,
            "concepto": "Mantenimiento",
            "descripcion": "Mantenimiento de equipos para la actividad empresarial",
        }
        response = self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "companies": [],
            "cases": [first_expense],
            "receipts": [],
        })
        self.assertEqual(response.status_code, 200)

        response = self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "companies": [],
            "cases": [first_expense],
            "receipts": [],
        })
        self.assertEqual(response.status_code, 200)

        response = self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "companies": [],
            "cases": [],
            "receipts": [],
        })
        self.assertEqual(response.status_code, 200)
        workspace = self.client.get("/api/workspace").json
        self.assertEqual([item["id"] for item in workspace["cases"]], ["CAS-PERSIST"])
        self.assertEqual(workspace["companies"][0]["name"], "Empresa independiente")
        self.client.post("/api/logout")
        self.register("other-company@example.test")
        self.assertEqual(self.client.get("/api/workspace").json["companies"], [])
        self.assertEqual(self.client.get("/api/workspace").json["cases"], [])

    def test_company_with_eleven_digit_invalid_checksum_ruc_is_persisted_for_manual_review(self):
        invalid_checksum_ruc = "20412345678"
        self.assertFalse(is_valid_ruc(invalid_checksum_ruc))
        self.register("invalid-checksum@example.test")

        response = self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "companies": [{
                "ruc": invalid_checksum_ruc,
                "name": "Empresa de prueba con RUC pendiente",
                "activity": "Servicios empresariales",
            }],
            "cases": [{
                "id": "CAS-RUC-PENDIENTE",
                "empresaRuc": invalid_checksum_ruc,
                "empresa": "Empresa de prueba con RUC pendiente",
                "fecha": "2026-03-10",
                "monto": 500,
                "concepto": "Servicio empresarial",
            }],
            "receipts": [],
        })

        self.assertEqual(response.status_code, 200)
        workspace = self.client.get("/api/workspace").json
        self.assertEqual(workspace["companies"][0]["ruc"], invalid_checksum_ruc)
        self.assertEqual(workspace["cases"][0]["empresaRuc"], invalid_checksum_ruc)
        self.assertEqual(workspace["cases"][0]["evaluation"]["status"], "condicionado")

    def test_expense_delete_is_explicit_and_account_scoped(self):
        self.register("delete-expense@example.test")
        self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "cases": [{
                "id": "CAS-DELETE",
                "empresaRuc": VALID_RUC,
                "empresa": "Empresa A",
                "fecha": "2026-01-02",
                "monto": 250,
                "concepto": "Multa municipal",
            }],
            "receipts": [],
        })

        self.assertEqual(self.client.delete("/api/expenses/CAS-MISSING").status_code, 404)
        self.assertEqual(self.client.delete("/api/expenses/CAS-DELETE").status_code, 200)
        self.assertEqual(self.client.get("/api/workspace").json["cases"], [])

    def test_batch_delete_removes_only_its_expenses_and_private_excel(self):
        self.register("delete-batch@example.test")
        upload = self.client.post("/api/case-batches", data={
            "file": (BytesIO(b"Excel de prueba"), "lote.xlsx"),
        }, content_type="multipart/form-data")
        self.assertEqual(upload.status_code, 201)
        batch_id = upload.json["id"]
        with app.app_context():
            from app import database

            with database() as connection:
                owner_id = connection.execute(
                    "SELECT id FROM users WHERE email=?",
                    ("delete-batch@example.test",),
                ).fetchone()["id"]
        stored_file = CASE_BATCH_DIR / str(owner_id) / f"{batch_id}.xlsx"
        self.assertTrue(stored_file.is_file())

        make_case = lambda expense_id, case_batch: {
            "id": expense_id,
            "empresaRuc": VALID_RUC,
            "empresa": "Empresa A",
            "fecha": "2026-01-02",
            "monto": 250,
            "concepto": "Multa municipal",
            "origen": "Importación Excel",
            "loteExcel": {"id": case_batch, "nombre": "lote.xlsx", "fila": 2},
        }
        response = self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "cases": [
                make_case("CAS-BATCH-1", batch_id),
                make_case("CAS-BATCH-2", batch_id),
                make_case("CAS-OTHER-BATCH", "1" * 32),
            ],
            "receipts": [],
        })
        self.assertEqual(response.status_code, 200)

        deleted = self.client.delete(f"/api/expense-batches/{batch_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json["deleted"], 2)
        self.assertEqual(
            [item["id"] for item in self.client.get("/api/workspace").json["cases"]],
            ["CAS-OTHER-BATCH"],
        )
        self.assertFalse(stored_file.exists())
        self.client.post("/api/logout")
        self.register("other-delete-batch@example.test")
        self.assertEqual(self.client.delete(f"/api/expense-batches/{batch_id}").status_code, 404)

    def test_delete_all_expenses_keeps_companies_and_unlinks_documents(self):
        self.register("delete-all@example.test")
        upload = self.client.post("/api/case-batches", data={
            "file": (BytesIO(b"Excel de prueba"), "todos.xlsx"),
        }, content_type="multipart/form-data")
        self.assertEqual(upload.status_code, 201)
        batch_id = upload.json["id"]
        with app.app_context():
            from app import database

            with database() as connection:
                owner_id = connection.execute(
                    "SELECT id FROM users WHERE email=?",
                    ("delete-all@example.test",),
                ).fetchone()["id"]
        stored_file = CASE_BATCH_DIR / str(owner_id) / f"{batch_id}.xlsx"
        company = {"ruc": VALID_RUC, "name": "Empresa de prueba", "activity": "Servicios"}
        cases = [
            {
                "id": "CAS-ALL-BATCH",
                "empresaRuc": VALID_RUC,
                "empresa": "Empresa de prueba",
                "fecha": "2026-01-02",
                "monto": 118,
                "concepto": "Mantenimiento",
                "origen": "Importación Excel",
                "loteExcel": {"id": batch_id, "nombre": "todos.xlsx", "fila": 2},
            },
            {
                "id": "CAS-ALL-MANUAL",
                "empresaRuc": VALID_RUC,
                "empresa": "Empresa de prueba",
                "fecha": "2026-01-03",
                "monto": 250,
                "concepto": "Multa municipal",
            },
        ]
        saved = self.client.put("/api/workspace", json={
            "profile": {}, "empresa": {}, "fin": {}, "companies": [company],
            "cases": cases, "receipts": [],
        })
        self.assertEqual(saved.status_code, 200)
        document = self.client.post("/api/documents", data={
            "companyRuc": VALID_RUC,
            "expenseId": "CAS-ALL-BATCH",
            "document": (BytesIO(INVOICE_XML), "invoice.xml"),
        }, content_type="multipart/form-data")
        self.assertEqual(document.status_code, 201)

        deleted = self.client.delete("/api/expenses")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json["deleted"], 2)
        workspace = self.client.get("/api/workspace").json
        self.assertEqual(workspace["cases"], [])
        self.assertEqual(workspace["companies"][0]["ruc"], VALID_RUC)
        receipt = next(item for item in workspace["receipts"] if item["id"] == document.json["id"])
        self.assertIsNone(receipt["expenseId"])
        self.assertFalse(stored_file.exists())

    def test_document_is_extracted_stored_and_accessible_to_owning_user(self):
        self.register("documents@example.test")
        self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "receipts": [],
            "cases": [{
                "id": "CAS-DOC",
                "empresaRuc": VALID_RUC,
                "empresa": "Empresa receptora",
                "fecha": "2026-01-02",
                "monto": 118,
            }],
        })
        response = self.client.post("/api/documents", data={
            "companyRuc": VALID_RUC,
            "expenseId": "CAS-DOC",
            "document": (BytesIO(INVOICE_XML), "invoice.xml"),
        }, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["datosExtraidos"]["tipoComprobante"], "Factura")
        self.assertEqual(response.json["datosExtraidos"]["moneda"], "PEN")
        opened = self.client.get(response.json["url"])
        self.assertEqual(opened.data, INVOICE_XML)

        updated_case = {
            "id": "CAS-DOC",
            "empresaRuc": "20654321098",
            "empresa": "Empresa editada",
            "fecha": "2026-01-02",
            "monto": 118,
        }
        updated = self.client.put("/api/workspace", json={
            "profile": {},
            "empresa": {},
            "fin": {},
            "receipts": [],
            "cases": [updated_case],
        })
        self.assertEqual(updated.status_code, 200)
        workspace = self.client.get("/api/workspace")
        self.assertEqual(len(workspace.json["receipts"]), 1)
        self.assertEqual(workspace.json["receipts"][0]["id"], response.json["id"])
        self.assertEqual(workspace.json["receipts"][0]["empresaRuc"], "20654321098")
        self.client.post("/api/logout")
        self.register("other-documents@example.test")
        self.assertEqual(self.client.get(response.json["url"]).status_code, 404)

    def test_text_pdf_extracts_invoice_fields_without_claiming_sunat_validation(self):
        import pymupdf

        from app import extract_document

        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_text((50, 50), "R.U.C.: 20100070970\nR.U.C.: 20100070970\n02/01/2026\nFACTURA F001-123\nTotal S/ 118.00\nIGV S/ 18.00")
        content = pdf.tobytes()
        pdf.close()

        _, fields, warning = extract_document("invoice.pdf", content)

        self.assertEqual(fields["fecha"], "2026-01-02")
        self.assertEqual(fields["numero"], "F001-123")
        self.assertEqual(fields["proveedorRuc"], VALID_RUC)
        self.assertEqual(fields["importeTotal"], 118)
        self.assertEqual(fields["igv"], 18)
        self.assertFalse(fields.get("validadoPorSunat", False))
        self.assertEqual(warning, "")

    def test_template_has_complete_fields_without_classification_column(self):
        self.register("template@example.test")
        response = self.client.get("/api/expense-template.xlsx")

        self.assertEqual(response.status_code, 200)
        from openpyxl import load_workbook

        template_bytes = response.data
        response.close()
        workbook = load_workbook(BytesIO(template_bytes), read_only=True)
        worksheet = workbook["Registro de Compras"]
        rows = list(worksheet.iter_rows(values_only=True))
        header_index = next(
            index for index, row in enumerate(rows)
            if "RUC" in row and "Periodo" in row
        )
        headers = list(rows[header_index])
        self.assertIn("RUC", headers)
        self.assertIn("Nro Doc Identidad", headers)
        self.assertIn("Total CP", headers)
        self.assertIn("Descripción detallada del gasto", headers)
        self.assertEqual(len([header for header in headers if header]), 81)
        self.assertFalse(any("deducible" in str(header).lower() for header in headers))
        self.assertIn("Instrucciones", workbook.sheetnames)
        self.assertFalse(any(
            value not in (None, "")
            for row in rows[header_index + 1:]
            for value in row
        ))
        workbook.close()
        self.assertTrue((TEMPLATE_DIR / "Tribuanalisis_Plantilla_Gastos_Vacia.xlsx").is_file())
        parsed_template = parse_purchase_workbook(template_bytes)
        self.assertEqual(parsed_template["operationCount"], 0)

        sample = self.client.get("/api/case-test-template.xlsx")
        self.assertEqual(sample.status_code, 200)
        sample_bytes = sample.data
        sample.close()
        sample_workbook = load_workbook(BytesIO(sample_bytes), read_only=True)
        self.assertEqual(sample_workbook.sheetnames[0], "Registro de Compras")
        self.assertIn("Contexto de casos", sample_workbook.sheetnames)
        sample_sheet = sample_workbook["Registro de Compras"]
        sample_rows = list(sample_sheet.iter_rows(values_only=True))
        sample_header_index = next(
            index for index, row in enumerate(sample_rows)
            if "RUC" in row and "Periodo" in row
        )
        sample_headers = list(sample_rows[sample_header_index])
        sample_cases = [
            row for row in sample_rows[sample_header_index + 1:]
            if any(value not in (None, "") for value in row)
        ]
        self.assertEqual(len(sample_cases), 15)
        self.assertFalse(any("deducible" in str(header).lower() for header in sample_headers))
        sample_workbook.close()

    def test_sire_original_80_headers_accepts_blank_car_and_missing_description(self):
        from openpyxl import Workbook

        source = load_workbook(TEMPLATE_DIR / "Tribuanalisis_Plantilla_Gastos_Vacia.xlsx", read_only=True)
        original_headers = [
            cell.value for cell in next(source["Registro de Compras"].iter_rows(min_row=1, max_row=1))
            if cell.value != "Descripción detallada del gasto"
        ]
        source.close()
        self.assertEqual(len(original_headers), 80)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Registro de Compras"
        sheet.append(original_headers)
        values = {
            "RUC": "20100070970",
            "Apellidos y Nombres o Razón social": "Empresa de prueba S.A.C.",
            "Periodo": 202601,
            "Fecha de emisión": datetime(2026, 1, 15),
            "Tipo CP/Doc.": 1,
            "Serie del CDP": "001",
            "Nro CP o Doc. Nro Inicial (Rango)": 12,
            "Tipo Doc Identidad": 6,
            "Nro Doc Identidad": "20555555556",
            "Apellidos Nombres/ Razón  Social": "Proveedor de prueba",
            "BI Gravado DG": 100,
            "IGV / IPM DG": 18,
            "Total CP": 118,
            "Moneda": "PEN",
        }
        normalized_headers = {normalize_header(header): index + 1 for index, header in enumerate(original_headers)}
        for header, value in values.items():
            sheet.cell(row=2, column=normalized_headers[normalize_header(header)], value=value)
        number_cell = sheet.cell(row=2, column=normalized_headers[normalize_header("Nro CP o Doc. Nro Inicial (Rango)")])
        number_cell.number_format = "000000"
        output = BytesIO()
        workbook.save(output)
        workbook.close()

        result = parse_purchase_workbook(output.getvalue())

        self.assertTrue(result["isSire"])
        self.assertEqual(result["headerCount"], 80)
        self.assertEqual(result["operationCount"], 1)
        operation = result["operations"][0]
        self.assertEqual(operation["companyRuc"], VALID_RUC)
        self.assertEqual(operation["supplierRuc"], "20555555556")
        self.assertEqual(operation["car"], "")
        self.assertEqual(operation["fecha"], "2026-01-15")
        self.assertEqual(operation["number"], "001-000012")
        self.assertEqual(operation["total"], 118)
        self.assertEqual(operation["detailedDescription"], "")
        self.assertTrue(any("Descripción detallada" in issue for issue in operation["issues"]))

    def test_custom_81_column_workbook_links_context_and_separates_companies(self):
        from openpyxl import Workbook

        template = load_workbook(TEMPLATE_DIR / "Tribuanalisis_Plantilla_Gastos_Vacia.xlsx", read_only=True)
        headers = [cell.value for cell in next(template["Registro de Compras"].iter_rows(min_row=1, max_row=1))]
        template.close()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Datos"
        sheet.append(headers)
        header_index = {normalize_header(header): index + 1 for index, header in enumerate(headers)}

        source_rows = [
            {
                "RUC": VALID_RUC,
                "Apellidos y Nombres o Razón social": "Empresa Uno S.A.C.",
                "Periodo": 202601,
                "Fecha de emisión": datetime(2026, 1, 2),
                "Tipo CP/Doc.": 1,
                "Serie del CDP": "F001",
                "Nro CP o Doc. Nro Inicial (Rango)": 125,
                "Tipo Doc Identidad": 6,
                "Nro Doc Identidad": "20555555556",
                "Apellidos Nombres/ Razón  Social": "Proveedor A",
                "BI Gravado DG": 100,
                "IGV / IPM DG": 18,
                "Total CP": 118,
            },
            {
                "RUC": VALID_RUC,
                "Apellidos y Nombres o Razón social": "Empresa Uno S.A.C.",
                "Periodo": 202601,
                "Fecha de emisión": datetime(2026, 1, 2),
                "Tipo CP/Doc.": 1,
                "Serie del CDP": "F001",
                "Nro CP o Doc. Nro Inicial (Rango)": 125,
                "Tipo Doc Identidad": 6,
                "Nro Doc Identidad": "20555555556",
                "Apellidos Nombres/ Razón  Social": "Proveedor A",
                "BI Gravado DG": 100,
                "IGV / IPM DG": 18,
                "Total CP": 118,
            },
            {
                "RUC": "20600000005",
                "Apellidos y Nombres o Razón social": "Empresa Dos S.A.C.",
                "Periodo": 202601,
                "Fecha de emisión": datetime(2026, 1, 3),
                "Tipo CP/Doc.": 1,
                "Serie del CDP": "F002",
                "Nro CP o Doc. Nro Inicial (Rango)": 7,
                "Tipo Doc Identidad": 6,
                "Nro Doc Identidad": "20100070970",
                "Apellidos Nombres/ Razón  Social": "Proveedor B",
                "BI Gravado DG": 200,
                "IGV / IPM DG": 36,
                "Total CP": 236,
                "Descripción detallada del gasto": "Servicio de mantenimiento de maquinaria",
            },
        ]
        for row_number, values in enumerate(source_rows, start=2):
            for header, value in values.items():
                sheet.cell(row=row_number, column=header_index[normalize_header(header)], value=value)

        context = workbook.create_sheet("Contexto de casos")
        context_headers = [
            "RUC de la empresa", "Periodo", "Tipo CP/Doc.", "Serie del CDP", "Nro CP o Doc.",
            "RUC del proveedor", "Descripción del gasto", "Actividad económica de la empresa",
            "Finalidad o uso declarado", "Evidencia de recepción del bien o servicio",
        ]
        context.append(context_headers)
        context.append([
            VALID_RUC, 202601, 1, "F001", "000125", "20555555556", "Alquiler del local comercial",
            "Comercio al por menor", "Uso del inmueble como tienda y punto de venta",
            "Contrato de arrendamiento y constancia de recepción",
        ])
        context.append([
            "20600000005", 202601, 1, "F002", "000007", "20100070970",
            "Servicio de mantenimiento de maquinaria", "Mantenimiento y reparación de equipos",
            "Servicio aplicado a maquinaria usada en producción",
            "Orden de servicio y acta de conformidad",
        ])
        output = BytesIO()
        workbook.save(output)
        workbook.close()

        result = parse_purchase_workbook(output.getvalue())

        self.assertTrue(result["isSire"])
        self.assertEqual(result["headerCount"], 81)
        self.assertEqual(result["operationCount"], 3)
        self.assertEqual(result["duplicateCount"], 1)
        self.assertEqual({company["ruc"] for company in result["companies"]}, {VALID_RUC, "20600000005"})
        first, duplicate, second_company = result["operations"]
        self.assertTrue(first["contextMatched"])
        self.assertEqual(first["number"], "F001-000125")
        self.assertEqual(first["purpose"], "Uso del inmueble como tienda y punto de venta")
        self.assertTrue(duplicate["duplicateWithinFile"])
        self.assertEqual(second_company["companyRuc"], "20600000005")
        self.assertEqual(second_company["detailedDescription"], "Servicio de mantenimiento de maquinaria")
        self.assertTrue(second_company["contextMatched"])

        self.register("sire-import@example.test")
        cases = [{
            "id": f"SIRE-{index}",
            "empresaRuc": operation["companyRuc"],
            "empresa": operation["companyName"],
            "empresaActividad": operation["companyActivity"],
            "proveedorRuc": operation["supplierRuc"],
            "proveedor": operation["supplierName"],
            "numero": operation["number"],
            "fecha": operation["fecha"],
            "monto": operation["total"],
            "concepto": operation["detailedDescription"],
            "descripcionDetalladaGasto": operation["detailedDescription"],
            "descripcion": operation["purpose"],
            "evidencia": operation["evidence"],
        } for index, operation in enumerate((first, second_company))]
        companies = [
            {"ruc": operation["companyRuc"], "name": operation["companyName"], "activity": operation["companyActivity"]}
            for operation in (first, second_company)
        ]
        saved = self.client.put("/api/workspace", json={
            "profile": {}, "empresa": {}, "fin": {}, "receipts": [], "companies": companies, "cases": cases,
        })
        self.assertEqual(saved.status_code, 200)
        workspace = self.client.get("/api/workspace").json
        self.assertEqual(len(workspace["companies"]), 2)
        counts = {}
        for case in workspace["cases"]:
            ruc = case["empresaRuc"]
            counts[ruc] = counts.get(ruc, 0) + 1
        self.assertEqual(counts, {VALID_RUC: 1, "20600000005": 1})

    def test_example_workbook_preview_reads_all_cases_and_context(self):
        self.register("preview@example.test")
        sample_path = Path(__file__).resolve().parents[1] / "casos_prueba" / "Tribuanalisis_15_Casos_Gastos_Ejemplo.xlsx"
        response = self.client.post(
            "/api/expense-import-preview",
            data={"file": (BytesIO(sample_path.read_bytes()), sample_path.name)},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["operationCount"], 15)
        self.assertEqual(response.json["headerCount"], 81)
        self.assertEqual(len(response.json["companies"]), 2)
        self.assertTrue(all(operation["contextMatched"] for operation in response.json["operations"]))
        self.assertTrue(all(operation["car"] == "" for operation in response.json["operations"]))

    def test_ruc_lookup_returns_secondary_activities_ciiu_and_source(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return (
                    '{"numero_documento":"20100070970","razon_social":"EMPRESA DE PRUEBA S.A.C.",'
                    '"actividad_economica_principal":"Comercio","actividad_economica_secundaria_1":"Servicios",'
                    '"actividad_economica_secundaria_2":"Transporte","codigo_ciiu":"4719",'
                    '"estado":"ACTIVO","condicion":"HABIDO"}'
                ).encode("utf-8")

        with patch.dict(os.environ, {"DECOLECTA_API_TOKEN": "test-token"}):
            with patch("app.urlopen", return_value=FakeResponse()):
                response = self.client.get(f"/api/ruc/{VALID_RUC}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["razonSocial"], "EMPRESA DE PRUEBA S.A.C.")
        self.assertEqual(response.json["actividadEconomicaPrincipal"], "Comercio")
        self.assertEqual(response.json["actividadEconomicaSecundaria1"], "Servicios")
        self.assertEqual(response.json["actividadEconomicaSecundaria2"], "Transporte")
        self.assertEqual(response.json["codigoCIIU"], "4719")
        self.assertFalse(response.json["official"])
        self.assertIn("Decolecta", response.json["source"])
        self.assertTrue(response.json["consultedAt"])


if __name__ == "__main__":
    unittest.main()
