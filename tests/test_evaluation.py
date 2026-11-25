import unittest

from evaluation import REFERENCES, evaluate_expense


class ExpenseEvaluationTests(unittest.TestCase):
    def test_legal_references_link_to_official_article_pages(self):
        expected_pages = {
            "causalidad": "capvi.pdf#page=1",
            "fehaciencia": "capvi.pdf#page=1",
            "razonabilidad": "capvi.pdf#page=12",
            "generalidad": "capvi.pdf#page=12",
            "no_deducible": "capvi.pdf#page=13",
            "devengo": "capviii.pdf#page=1",
            "representacion": "capvi.pdf#page=9",
            "bancarizacion": "ds150_07.pdf#page=3",
            "viajes": "capvi.pdf#page=9",
            "vehiculos": "capvi.pdf#page=10",
            "donaciones": "capvi.pdf#page=11",
            "depreciacion": "capvi.pdf#page=12",
            "financieros": "capvi.pdf#page=2",
        }

        for key, suffix in expected_pages.items():
            with self.subTest(reference=key):
                reference, url = REFERENCES[key]
                self.assertIn(suffix, url)
                self.assertTrue(url.startswith("https://www.sunat.gob.pe/"))
                self.assertTrue(reference)

    def test_restricted_expense_links_to_its_specific_lir_inciso(self):
        result = evaluate_expense({
            "monto": 500,
            "concepto": "Pasajes por viaje de trabajo",
        })

        criterion = next(item for item in result["criteria"] if item["label"] == "Regla específica del concepto")
        self.assertIn("art. 37, inciso r)", criterion["reference"])
        self.assertTrue(criterion["url"].endswith("capvi.pdf#page=9"))

    def test_explicitly_prohibited_expense_is_not_deductible(self):
        result = evaluate_expense({"monto": 250, "concepto": "Multa municipal"})

        self.assertEqual(result["status"], "no_deducible")
        self.assertEqual(result["deductibleAmount"], 0)
        self.assertEqual(result["nonDeductibleAmount"], 250)
        self.assertIn("art. 44", result["legalBasis"][0])

    def test_explicit_personal_travel_and_household_expenses_are_not_deductible(self):
        examples = (
            ("Hospedaje y pasajes por viaje recreativo del titular", "Viaje personal durante vacaciones"),
            ("Compra de víveres y artículos de consumo doméstico", "Consumo del hogar del titular"),
        )
        for concept, description in examples:
            with self.subTest(concept=concept):
                result = evaluate_expense({
                    "monto": 500,
                    "concepto": concept,
                    "descripcion": description,
                })

                self.assertEqual(result["status"], "no_deducible")
                self.assertEqual(result["deductibleAmount"], 0)
                self.assertEqual(result["nonDeductibleAmount"], 500)
                self.assertIn("art. 44", result["legalBasis"][0])

    def test_representative_expense_calculates_annual_limit_and_excess(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa de prueba",
            "empresaActividad": "Servicios profesionales",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor de prueba",
            "fecha": "2025-03-10",
            "fechaServicio": "2025-03-10",
            "monto": 1000,
            "tipoComprobante": "Factura",
            "concepto": "Gastos de representación",
            "descripcion": "Atención a clientes de los servicios profesionales de ventas de la empresa",
            "evidencia": "Orden de atención y reporte de visita a clientes",
            "ingresosNetosAnuales": 100000,
            "documentos": [{
                "datosExtraidos": {
                    "proveedorRuc": "20100070970",
                    "numero": "F001-123",
                }
            }],
            "numero": "F001-123",
        })

        self.assertEqual(result["status"], "limitado")
        self.assertEqual(result["deductibleAmount"], 500)
        self.assertEqual(result["nonDeductibleAmount"], 500)

    def test_complete_ordinary_expense_is_not_conditioned_by_optional_fields(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa de prueba",
            "empresaActividad": "Servicios profesionales",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor de prueba",
            "numero": "F001-456",
            "tipoComprobante": "Factura",
            "fecha": "2026-03-10",
            "fechaServicio": "2026-03-10",
            "monto": 750,
            "concepto": "Servicio de consultoría profesional",
            "descripcion": "Consultoría profesional para operaciones y gestión comercial de la empresa",
            "evidencia": "Orden de servicio y acta de conformidad del servicio",
            "documentos": [{
                "datosExtraidos": {
                    "proveedorRuc": "20100070970",
                    "numero": "F001-456",
                }
            }],
        })

        self.assertEqual(result["status"], "deducible")
        self.assertEqual(result["deductibleAmount"], 750)
        self.assertEqual(result["nonDeductibleAmount"], 0)
        self.assertTrue(any("referencia cuantitativa" in item for item in result["observations"]))

    def test_office_supplies_are_inferred_from_description_without_an_attached_invoice(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa de prueba",
            "empresaActividad": "Comercio",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor de prueba",
            "numero": "F001-460",
            "tipoComprobante": "Factura",
            "fecha": "2026-11-23",
            "fechaServicio": "2026-11-23",
            "monto": 118,
            "concepto": "Compra de insumos de oficina",
            "descripcionDetalladaGasto": "Compra de insumos de oficina",
            "descripcion": "Insumos utilizados por el área administrativa en tareas de gestión.",
            "evidencia": "Orden interna y constancia de recepción disponibles.",
            "rucReceptor": "20100070970",
        })

        causality = next(item for item in result["criteria"] if item["key"] == "causalidad")
        document = next(
            item for item in result["criteria"]
            if item["label"] == "Documento y datos de la operación"
        )
        self.assertIn("oficina", result["expenseCategory"].lower())
        self.assertEqual(causality["status"], "cumple")
        self.assertEqual(document["status"], "cumple")
        self.assertIn("No se adjuntó", document["detail"])
        self.assertEqual(result["status"], "deducible")

    def test_description_infers_expense_type_while_missing_requirements_stay_conditional(self):
        result = evaluate_expense({
            "concepto": "Compra de insumos de oficina",
            "descripcionDetalladaGasto": "Compra de insumos de oficina",
        })

        self.assertIn("oficina", result["expenseCategory"].lower())
        self.assertEqual(result["status"], "condicionado")
        self.assertTrue(result["missing"])

    def test_invalid_demo_ruc_checksums_warn_without_masking_a_supported_expense(self):
        result = evaluate_expense({
            "empresaRuc": "20123456789",
            "empresa": "COMERCIAL DEMO DEL NORTE S.A.C.",
            "empresaActividad": "Comercio al por menor de artículos de ferretería",
            "proveedorRuc": "20111122223",
            "proveedor": "CONECTIVIDAD EMPRESARIAL DEMO S.A.C.",
            "rucReceptor": "20123456789",
            "numero": "F001-000002",
            "tipoComprobante": "Factura",
            "fecha": "2026-03-10",
            "fechaServicio": "2026-03-10",
            "monto": 341.02,
            "concepto": "Servicio mensual de internet del establecimiento",
            "descripcionDetalladaGasto": "Servicio mensual de internet del establecimiento",
            "descripcion": "Conectividad para caja, facturación electrónica, inventario y atención al cliente",
            "evidencia": "Orden de servicio OS-014",
            "sireFields": ["RUC", "Fecha de emisión", "Tipo CP/Doc.", "Total CP"],
        })

        self.assertEqual(result["status"], "deducible")
        self.assertTrue(any("RUC de la empresa no supera" in item for item in result["observations"]))
        self.assertTrue(any("RUC del proveedor no supera" in item for item in result["observations"]))

    def test_customer_meeting_food_is_limited_representation_and_calculates_excess(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa de prueba",
            "empresaActividad": "Comercio",
            "proveedorRuc": "20100017491",
            "proveedor": "Proveedor de eventos",
            "rucReceptor": "20100070970",
            "numero": "F001-461",
            "tipoComprobante": "Factura",
            "fecha": "2026-03-10",
            "fechaServicio": "2026-03-10",
            "monto": 8024,
            "concepto": "Servicio de atención y alimentación en reunión con clientes",
            "descripcionDetalladaGasto": "Servicio de atención y alimentación en reunión con clientes",
            "descripcion": "Reunión comercial para presentar catálogo y negociar condiciones de suministro",
            "evidencia": "Orden de servicio OS-044",
            "sireFields": ["RUC", "Fecha de emisión", "Tipo CP/Doc.", "Total CP"],
            "medioPago": "Transferencia",
            "referenciaPago": "OP-TRX-0006",
            "ingresosNetosAnuales": 850000,
        })

        self.assertEqual(result["status"], "limitado")
        self.assertEqual(result["deductibleAmount"], 4250)
        self.assertEqual(result["nonDeductibleAmount"], 3774)

    def test_sire_detailed_description_uses_secondary_activity_as_context(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa de prueba",
            "empresaActividad": "Venta de repuestos",
            "empresaActividadSecundaria1": "Mantenimiento y reparación de maquinaria",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor de prueba",
            "numero": "F001-457",
            "tipoComprobante": "Factura",
            "fecha": "2026-03-10",
            "fechaServicio": "2026-03-10",
            "monto": 750,
            "concepto": "Registro de compras SIRE",
            "descripcionDetalladaGasto": "Servicio de mantenimiento de maquinaria de planta",
            "descripcion": "Mantenimiento programado de la maquinaria utilizada en la producción de la empresa",
            "evidencia": "Orden de servicio y acta de conformidad",
            "documentos": [{
                "datosExtraidos": {
                    "proveedorRuc": "20100070970",
                    "numero": "F001-457",
                }
            }],
        })

        causality = next(item for item in result["criteria"] if item["key"] == "causalidad")
        self.assertEqual(causality["status"], "cumple")
        self.assertEqual(result["status"], "deducible")

    def test_sire_denominacion_identifies_an_ordinary_operating_expense(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa de prueba",
            "empresaActividad": "Comercio al por menor",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor de prueba",
            "numero": "F001-458",
            "tipoComprobante": "Factura",
            "fecha": "2026-03-10",
            "fechaServicio": "2026-03-10",
            "monto": 750,
            "concepto": "Registro de compras SIRE",
            "descripcionDetalladaGasto": "Servicio mensual de internet para facturación e inventario de la tienda",
            "descripcion": "Conectividad utilizada para la facturación de ventas y el control del inventario",
            "evidencia": "Contrato del servicio y recibo de conformidad",
            "sireFields": ["RUC", "Fecha de emisión", "Tipo CP/Doc.", "Total CP"],
        })

        causality = next(item for item in result["criteria"] if item["key"] == "causalidad")
        document = next(item for item in result["criteria"] if item["label"] == "Documento y datos de la operación")
        self.assertEqual(causality["status"], "cumple")
        self.assertEqual(document["status"], "cumple")
        self.assertIn("no valida el CPE", document["detail"])
        self.assertEqual(result["status"], "deducible")

    def test_asset_purchase_denominacion_requires_asset_and_depreciation_review(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa de prueba",
            "empresaActividad": "Servicios profesionales",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor de prueba",
            "numero": "F001-459",
            "tipoComprobante": "Factura",
            "fecha": "2026-03-10",
            "fechaServicio": "2026-03-10",
            "monto": 750,
            "concepto": "Compra de una computadora portátil para el área administrativa",
            "descripcionDetalladaGasto": "Adquisición de una computadora portátil",
            "descripcion": "Equipo destinado a las labores administrativas de la empresa",
            "evidencia": "Orden de compra",
            "sireFields": ["RUC", "Fecha de emisión", "Tipo CP/Doc.", "Total CP"],
        })

        asset_criterion = next(
            item for item in result["criteria"]
            if item["label"] == "Tratamiento de posible activo fijo"
        )
        self.assertEqual(result["status"], "condicionado")
        self.assertEqual(asset_criterion["status"], "pendiente")
        self.assertIn("pertenece a la empresa", asset_criterion["detail"])

    def test_invoice_fields_without_operation_support_remain_conditional(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa de prueba",
            "empresaActividad": "Servicios profesionales",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor de prueba",
            "numero": "F001-789",
            "tipoComprobante": "Factura",
            "fecha": "2026-03-10",
            "fechaServicio": "2026-03-10",
            "monto": 750,
            "concepto": "Servicio de consultoría profesional",
            "descripcion": "Consultoría profesional para operaciones y gestión comercial de la empresa",
            "documentos": [{
                "datosExtraidos": {
                    "proveedorRuc": "20100070970",
                    "numero": "F001-789",
                }
            }],
        })

        self.assertEqual(result["status"], "condicionado")
        self.assertTrue(any("sustento disponible" in item for item in result["missing"]))

    def test_extracted_invoice_compares_actual_supplier_receiver_and_total_fields(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa receptora",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor",
            "rucReceptor": "20100070970",
            "numero": "F001-123",
            "fecha": "2026-01-02",
            "fechaServicio": "2026-01-02",
            "monto": 118,
            "concepto": "Servicio de mantenimiento",
            "descripcion": "Mantenimiento periódico de equipos del área de producción",
            "documentos": [{
                "datosExtraidos": {
                    "proveedorRuc": "20100070970",
                    "rucReceptor": "20100070970",
                    "numero": "F001-123",
                    "importeTotal": 118,
                }
            }],
        })

        document_criterion = next(
            item for item in result["criteria"]
            if item["label"] == "Documento y datos de la operación"
        )
        self.assertEqual(document_criterion["status"], "cumple")
        self.assertIn("no acredita", document_criterion["detail"])

    def test_string_evidence_is_not_iterated_as_characters(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor",
            "fecha": "2026-01-02",
            "monto": 100,
            "tipoOperacion": "Gasto de personal",
            "concepto": "Seguro médico del equipo",
            "descripcion": "Cobertura médica para trabajadores de la empresa",
            "evidencia": "Política interna y planilla",
        })

        generality = next(item for item in result["criteria"] if item["key"] == "generalidad")
        self.assertEqual(generality["status"], "pendiente")
        self.assertIn("política o planilla", generality["detail"])

    def test_bancarization_is_not_marked_met_when_payment_is_unrecorded(self):
        result = evaluate_expense({
            "empresaRuc": "20100070970",
            "empresa": "Empresa",
            "proveedorRuc": "20100070970",
            "proveedor": "Proveedor",
            "fecha": "2026-01-02",
            "monto": 2500,
            "moneda": "PEN",
            "concepto": "Servicio de transporte",
            "descripcion": "Traslado de productos para distribución comercial",
            "medioPago": "No registrado",
            "referenciaPago": "OP-123",
        })

        payment_criterion = next(
            item for item in result["criteria"]
            if item["key"] == "bancarizacion"
        )
        self.assertEqual(payment_criterion["status"], "pendiente")


if __name__ == "__main__":
    unittest.main()
