import re
import unicodedata
from datetime import date


LIR_CHAPTER_VI = "https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf"
LIR_CHAPTER_VIII = "https://www.sunat.gob.pe/legislacion/renta/ley/capviii.pdf"
ITF_TUO = "https://www.sunat.gob.pe/legislacion/itf/ds150_07.pdf"

REFERENCES = {
    "causalidad": ("LIR, art. 37, primer párrafo", f"{LIR_CHAPTER_VI}#page=1"),
    "fehaciencia": ("LIR, art. 37; documentación de la operación", f"{LIR_CHAPTER_VI}#page=1"),
    "razonabilidad": ("LIR, art. 37, último párrafo", f"{LIR_CHAPTER_VI}#page=12"),
    "generalidad": ("LIR, art. 37, último párrafo; incisos l), ll) y a.2)", f"{LIR_CHAPTER_VI}#page=12"),
    "no_deducible": ("LIR, art. 44", f"{LIR_CHAPTER_VI}#page=13"),
    "devengo": ("LIR, art. 57, inciso a)", f"{LIR_CHAPTER_VIII}#page=1"),
    "representacion": ("LIR, art. 37, inciso q)", f"{LIR_CHAPTER_VI}#page=9"),
    "bancarizacion": ("Ley 28194, arts. 3, 4 y 8", f"{ITF_TUO}#page=3"),
    "viajes": ("LIR, art. 37, inciso r)", f"{LIR_CHAPTER_VI}#page=9"),
    "vehiculos": ("LIR, art. 37, inciso w)", f"{LIR_CHAPTER_VI}#page=10"),
    "donaciones": ("LIR, art. 37, inciso x)", f"{LIR_CHAPTER_VI}#page=11"),
    "depreciacion": ("LIR, arts. 37 y 38", f"{LIR_CHAPTER_VI}#page=12"),
    "financieros": ("LIR, art. 37, inciso a)", f"{LIR_CHAPTER_VI}#page=2"),
}

UIT_BY_YEAR = {
    2020: 4300,
    2021: 4400,
    2022: 4600,
    2023: 4950,
    2024: 5150,
    2025: 5350,
    2026: 5500,
}

STOP_WORDS = {
    "para", "con", "por", "una", "uno", "del", "las", "los", "que",
    "empresa", "servicio", "servicios", "compra", "gasto", "actividad",
    "renta", "negocio", "operacion", "operaciones", "el", "la", "de",
}

PROHIBITED_PATTERNS = (
    (r"\b(multas?|sanciones?|recargos?|intereses moratorios?)\b", "multa o sanción"),
    (r"\b(impuesto a la renta|ir de tercera categoria)\b", "impuesto a la renta"),
    (r"\b(gasto personal|consumo personal|uso personal)\b", "gasto personal"),
    (r"\b(consumo domestico|consumo del hogar|viaje recreativo|viaje personal|vacaciones del titular)\b",
     "gasto de carácter personal"),
)

RESTRICTED_PATTERNS = (
    (r"\b(donacion|donaciones)\b", "Donaciones", "LIR, art. 37, inciso x)", "donaciones"),
    (r"\b(viaje|viajes|pasajes|viaticos)\b", "Viajes y viáticos", "LIR, art. 37, inciso r)", "viajes"),
    (r"\b(automovil|sedan|camioneta|suv|vehiculo de pasajeros|vehiculo de gerencia)\b",
     "Vehículos de uso restringido", "LIR, art. 37, inciso w)", "vehiculos"),
    (r"\b(depreciacion|activo fijo)\b", "Depreciación o activo fijo", "LIR, arts. 37 y 38", "depreciacion"),
    (r"\b(intereses|prestamo|financiamiento|gasto financiero)\b", "Gastos financieros", "LIR, art. 37, inciso a)", "financieros"),
)

ORDINARY_EXPENSE_PATTERNS = (
    (r"\b(insumos? de oficina|utiles de oficina|articulos de oficina|papeleria|papel bond|toner|cartucho de tinta)\b",
     "Gasto administrativo: insumos y útiles de oficina"),
    (r"\b(internet|telefonia|energia electrica|consumo electrico|electricidad|agua potable|servicio de agua)\b",
     "Servicio básico para la operación"),
    (r"\b(alquiler de local|arrendamiento de local|local comercial)\b",
     "Alquiler de local de negocio"),
    (r"\b(publicidad|marketing|promocion|campana publicitaria|anuncios)\b",
     "Publicidad y promoción"),
    (r"\b(flete|transporte de mercaderia|logistica|reparto|combustible)\b",
     "Logística y distribución"),
    (r"\b(servicio contable|contabilidad|consultoria|asesoria profesional|honorarios profesionales)\b",
     "Servicio profesional"),
    (r"\b(mantenimiento|reparacion)\b",
     "Mantenimiento y reparación"),
)

FIXED_ASSET_PURCHASE_PATTERN = re.compile(
    r"\b(compra|adquisicion|adquirir|incorporacion)\b.{0,70}"
    r"\b(maquinaria|computadora|portatil|laptop|servidor|impresora|mobiliario|"
    r"muebles|estantes|equipo de produccion|equipo|vehiculo|automovil|camioneta|"
    r"camion|activo fijo)\b"
)

BUSINESS_USE_PATTERNS = (
    r"\b(local comercial|establecimiento comercial|tienda|punto de venta|almacen)\b",
    r"\b(facturacion|inventario|atencion al cliente|pedido|mercaderia|reparto|"
    r"ruta de transporte|carga|produccion|equipo de trabajo|area administrativa|"
    r"insumos? de oficina|utiles de oficina|articulos de oficina|papeleria|"
    r"papel bond|toner|cartucho de tinta)\b",
    r"\b(comision de servicio|servicio contratado|operaciones de la empresa|"
    r"operacion comercial|actividad comercial|reunion comercial|negociar condiciones)\b",
)


def _normalize(value):
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _valid_ruc(value):
    ruc = str(value or "").strip()
    if not re.fullmatch(r"\d{11}", ruc):
        return False
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    check = 11 - sum(int(digit) * weight for digit, weight in zip(ruc[:10], weights)) % 11
    expected = 0 if check == 10 else 1 if check == 11 else check
    return int(ruc[-1]) == expected


def _tokens(value):
    tokens = set()
    for token in re.findall(r"[a-z0-9]{3,}", _normalize(value)):
        if token.endswith("es") and len(token) > 5:
            token = token[:-2]
        elif token.endswith("s") and len(token) > 4:
            token = token[:-1]
        if token not in STOP_WORDS:
            tokens.add(token)
    return tokens


def _criteria_item(key, label, status, detail):
    reference, url = REFERENCES[key]
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "reference": reference,
        "url": url,
    }


def _infer_category(expense):
    concept = _normalize(" ".join((
        str(expense.get("denominacion") or expense.get("denomination") or ""),
        str(expense.get("descripcionGasto") or ""),
        str(expense.get("descripcionDetalladaGasto") or ""),
        str(expense.get("concepto") or ""),
        str(expense.get("descripcion") or ""),
        str(expense.get("tipoOperacion") or ""),
    )))
    for pattern, reason in PROHIBITED_PATTERNS:
        if re.search(pattern, concept):
            return "prohibido", reason, "no_deducible"
    if re.search(r"\b(representacion|agasajo|atencion.{0,40}clientes)\b", concept):
        return "representacion", "Gastos de representación", "representacion"
    if re.search(r"\b(bono|gasto de personal|beneficio al personal|beneficios del personal|uniforme|gratificacion|aguinaldo|remuneracion|bonificacion|planilla)\b", concept):
        return "beneficio_personal", "Beneficio al personal", "generalidad"
    if FIXED_ASSET_PURCHASE_PATTERN.search(concept) and not re.search(
        r"\b(reparacion|mantenimiento|repuesto|alquiler)\b", concept
    ):
        return "activo_fijo", "Posible adquisición de un activo fijo", "depreciacion"
    for pattern, category, legal_basis, reference_key in RESTRICTED_PATTERNS:
        if re.search(pattern, concept):
            return "condicionado", f"{category} ({legal_basis})", reference_key
    for pattern, description in ORDINARY_EXPENSE_PATTERNS:
        if re.search(pattern, concept):
            return "ordinario", description, None
    return "ordinario", "Gasto empresarial ordinario", None


def _file_data(expense):
    files = expense.get("documentos")
    if not isinstance(files, list):
        files = expense.get("archivos")
    return [item for item in files or [] if isinstance(item, dict)]


def _has_invoice_document(files, expense):
    for item in files:
        extracted = item.get("datosExtraidos") or item.get("extractedData") or {}
        if not isinstance(extracted, dict):
            continue
        if not any(extracted.values()):
            continue
        comparisons = (
            ("proveedorRuc", "proveedorRuc"),
            ("empresaRuc", "rucReceptor"),
            ("numero", "numero"),
            ("monto", "importeTotal"),
        )
        matched = 0
        for expense_key, document_key in comparisons:
            value = extracted.get(document_key)
            expected = expense.get(expense_key)
            if value in (None, "") or expected in (None, ""):
                continue
            if expense_key == "monto":
                try:
                    if abs(float(value) - float(expected)) <= 0.01:
                        matched += 1
                except (TypeError, ValueError):
                    continue
            elif str(value).strip().casefold() == str(expected).strip().casefold():
                matched += 1
        if matched >= 2:
            return True
    return False


def evaluate_expense(expense, previous_expenses=()):
    amount = float(expense.get("monto") or 0)
    currency = str(expense.get("moneda") or "PEN").upper()
    issue_date = str(expense.get("fecha") or "")
    year_match = re.match(r"(\d{4})", issue_date)
    year = int(year_match.group(1)) if year_match else None
    company_ruc = str(expense.get("empresaRuc") or expense.get("ruc") or "").strip()
    supplier_ruc = str(expense.get("proveedorRuc") or "").strip()
    receiver_ruc = str(expense.get("rucReceptor") or "").strip()
    files = _file_data(expense)
    category, category_reason, category_reference = _infer_category(expense)
    criteria = []
    missing = []
    observations = []
    negative = []
    legal_basis = []

    def add(key, label, status, detail, blocks_classification=True):
        item = _criteria_item(key, label, status, detail)
        criteria.append(item)
        if item["reference"] not in legal_basis:
            legal_basis.append(item["reference"])
        if status == "pendiente":
            (missing if blocks_classification else observations).append(detail)
        if status == "no_cumple":
            negative.append(detail)

    if category == "prohibido":
        add(category_reference, "Concepto comprendido en una exclusión", "no_cumple",
            f"El concepto describe {category_reason}; revisar la exclusión prevista en el artículo 44.")
        return _result("no_deducible", amount, 0, amount, criteria, missing, negative,
                       legal_basis, "La información ingresada identifica un concepto que la LIR excluye.",
                       expense_category=category_reason)

    if not re.fullmatch(r"\d{11}", company_ruc):
        add("causalidad", "Identificación de la empresa", "pendiente",
            "Falta un RUC de empresa con 11 dígitos.")
    elif not _valid_ruc(company_ruc):
        add("causalidad", "Identificación de la empresa", "pendiente",
            "El RUC de la empresa no supera el dígito verificador; la evaluación es preliminar y requiere corregir la identificación.",
            blocks_classification=False)
    if not expense.get("empresa"):
        add("causalidad", "Identificación de la empresa", "pendiente",
            "Falta la razón social de la empresa.")
    if not re.fullmatch(r"\d{11}", supplier_ruc) or not expense.get("proveedor"):
        add("fehaciencia", "Identificación del proveedor", "pendiente",
            "Falta una razón social o un RUC de proveedor con 11 dígitos.")
    elif not _valid_ruc(supplier_ruc):
        add("fehaciencia", "Identificación del proveedor", "pendiente",
            "El RUC del proveedor no supera el dígito verificador; corrige el dato antes de cerrar la revisión.",
            blocks_classification=False)
    if not expense.get("numero"):
        add("fehaciencia", "Identificación del comprobante", "pendiente",
            "Falta la serie o el número del comprobante.")
    if not expense.get("tipoComprobante"):
        add("fehaciencia", "Tipo de comprobante", "pendiente",
            "Falta identificar el tipo de comprobante.")
    if not issue_date or not year:
        add("devengo", "Periodo de la operación", "pendiente",
            "Falta la fecha de emisión u operación para identificar el ejercicio.")
    if amount <= 0:
        add("fehaciencia", "Importe de la operación", "pendiente",
            "El importe debe ser mayor que cero.")

    activity = _tokens(" ".join(str(expense.get(field) or "") for field in (
        "empresaActividad",
        "empresaActividadSecundaria1",
        "empresaActividadSecundaria2",
    )))
    business_description = _tokens(
        f"{expense.get('denominacion', '')} {expense.get('descripcionGasto', '')} "
        f"{expense.get('concepto', '')} {expense.get('descripcionDetalladaGasto', '')} "
        f"{expense.get('descripcion', '')}"
    )
    detailed_description = _normalize(" ".join((
        str(expense.get("denominacion") or ""),
        str(expense.get("descripcionGasto") or ""),
        str(expense.get("concepto") or ""),
        str(expense.get("descripcionDetalladaGasto") or ""),
        str(expense.get("descripcion") or ""),
    )))
    has_operational_use = any(re.search(pattern, detailed_description) for pattern in BUSINESS_USE_PATTERNS)
    if not expense.get("concepto") or not expense.get("descripcion"):
        if activity and (
            expense.get("denominacion")
            or expense.get("descripcionDetalladaGasto")
            or expense.get("descripcionGasto")
        ) and has_operational_use:
            add("causalidad", "Vínculo con la actividad empresarial", "cumple",
                "La denominación y el uso descrito indican una finalidad operativa relacionada; es un indicio automático, no prueba concluyente.")
        else:
            add("causalidad", "Vínculo con la actividad empresarial", "pendiente",
                "Falta describir el bien o servicio y su finalidad empresarial.")
    elif activity and (
        activity.intersection(business_description) or has_operational_use
    ) and len(str(expense.get("descripcion") or expense.get("descripcionDetalladaGasto") or "").strip()) >= 18:
        add("causalidad", "Vínculo con la actividad empresarial", "cumple",
            "La denominación, el uso descrito y la actividad declarada muestran una relación empresarial probable; es un indicio automático, no prueba concluyente.")
    else:
        add("causalidad", "Vínculo con la actividad empresarial", "pendiente",
            "No se pudo establecer una relación suficiente entre la descripción, la finalidad y la actividad declarada.")

    raw_evidence = expense.get("evidencia") or []
    if isinstance(raw_evidence, str):
        evidence = _normalize(raw_evidence)
    elif isinstance(raw_evidence, (list, tuple, set)):
        evidence = _normalize(" ".join(str(item) for item in raw_evidence))
    else:
        evidence = ""

    extracted_invoice = _has_invoice_document(files, expense)
    document_data_complete = (
        _valid_ruc(supplier_ruc)
        and bool(expense.get("proveedor"))
        and bool(expense.get("numero"))
        and bool(expense.get("tipoComprobante"))
        and bool(issue_date and year)
        and amount > 0
    )
    if extracted_invoice:
        add("fehaciencia", "Documento y datos de la operación", "cumple",
            "Se encontraron datos extraídos que coinciden con campos del comprobante; esto no acredita por sí solo la entrega o prestación.")
    elif isinstance(expense.get("sireFields"), list) and expense.get("sireFields"):
        add("fehaciencia", "Documento y datos de la operación", "cumple",
            "El Registro de Compras SIRE identifica un comprobante y sus datos; el asiento registral no valida el CPE ni acredita por sí solo la entrega o prestación.")
    elif document_data_complete and evidence.strip():
        add("fehaciencia", "Documento y datos de la operación", "cumple",
            "Se registraron los datos del comprobante y se declaró sustento adicional. No se adjuntó el documento para cotejarlo ni se consultó su validez ante SUNAT.")
    else:
        add("fehaciencia", "Documento y datos de la operación", "pendiente",
            "Adjunta un comprobante legible con datos que coincidan con el registro y sustento de la operación.")

    if not receiver_ruc:
        add("fehaciencia", "RUC receptor declarado", "pendiente",
            "No se proporcionó el RUC receptor para contrastarlo con la empresa.",
            blocks_classification=False)
    elif not re.fullmatch(r"\d{11}", receiver_ruc) or not _valid_ruc(receiver_ruc):
        add("fehaciencia", "RUC receptor declarado", "pendiente",
            "El RUC receptor no supera la validación de formato o dígito; corrígelo antes de confirmar la coincidencia.",
            blocks_classification=False)
    elif _valid_ruc(receiver_ruc) and receiver_ruc == company_ruc:
        add("fehaciencia", "RUC receptor declarado", "cumple",
            "El RUC receptor coincide con el de la empresa; esta comparación no valida el comprobante ante SUNAT.")
    elif not _valid_ruc(company_ruc):
        add("fehaciencia", "RUC receptor declarado", "pendiente",
            "No se puede contrastar el RUC receptor mientras el RUC de la empresa no sea válido.",
            blocks_classification=False)
    else:
        add("fehaciencia", "RUC receptor declarado", "no_cumple",
            "El RUC receptor declarado no coincide con el RUC de la empresa evaluada.")

    reference_amount = float(expense.get("importeReferencia") or 0)
    if reference_amount > 0 and amount <= reference_amount:
        add("razonabilidad", "Proporcionalidad y razonabilidad", "cumple",
            "El importe no excede el presupuesto o referencia ingresada; la plataforma no valida la fuente de esa referencia.")
    else:
        add("razonabilidad", "Proporcionalidad y razonabilidad", "pendiente",
            "No se registró una referencia cuantitativa; el importe debe contrastarse con el giro y las circunstancias de la operación.",
            blocks_classification=False)

    if evidence.strip():
        add("fehaciencia", "Sustento de la entrega o prestación", "cumple",
            "Se declaró sustento adicional de la operación; la plataforma no comprueba su autenticidad ni suficiencia.")
    else:
        add("fehaciencia", "Sustento de la entrega o prestación", "pendiente",
            "Registra el sustento disponible de la entrega o prestación (por ejemplo, orden, contrato, informe o conformidad).")

    service_date = str(expense.get("fechaServicio") or issue_date)
    service_year_match = re.match(r"(\d{4})", service_date)
    if year and service_year_match and int(service_year_match.group(1)) == year:
        add("devengo", "Imputación temporal (devengo)", "cumple",
            "La fecha de la operación o servicio cae en el mismo ejercicio de la emisión; el devengo contable requiere revisar las condiciones del contrato.")
    else:
        add("devengo", "Imputación temporal (devengo)", "pendiente",
            "La fecha del comprobante no permite confirmar por sí sola el ejercicio de devengo; revisa la fecha de recepción o prestación.")

    if category == "beneficio_personal":
        if re.search(r"\b(politica|planilla|convenio|criterio objetivo|reglamento interno)\b", evidence):
            add("generalidad", "Generalidad de beneficios al personal", "pendiente",
                "Se identificó una referencia a política o planilla, pero su aplicación general requiere verificar la documentación.")
        else:
            add("generalidad", "Generalidad de beneficios al personal", "pendiente",
                "El concepto puede corresponder a un beneficio al personal; no se encontró evidencia para evaluar generalidad.")
    else:
        add("generalidad", "Generalidad", "no_aplica",
            "Este requisito se evalúa únicamente en los supuestos de beneficios al personal previstos por la ley.")

    if category == "condicionado":
        add(category_reference, "Regla específica del concepto", "pendiente",
            f"El concepto puede estar sujeto a requisitos o límites adicionales: {category_reason}.")
    elif category == "activo_fijo":
        add(category_reference, "Tratamiento de posible activo fijo", "pendiente",
            "La denominación indica una posible adquisición de activo fijo. Verifica que el bien fue recibido y pertenece a la empresa, su uso empresarial, vida útil y registro contable antes de determinar si corresponde capitalizarlo y deducirlo mediante depreciación.")

    if currency == "PEN":
        bank_threshold = 2000
    elif currency == "USD":
        bank_threshold = 500
    else:
        bank_threshold = None
    if bank_threshold is None:
        add("bancarizacion", "Medios de pago", "pendiente",
            "La moneda no permite aplicar automáticamente el umbral de bancarización.")
    elif amount >= bank_threshold:
        payment_method = _normalize(expense.get("medioPago") or "")
        payment_reference = str(expense.get("referenciaPago") or "").strip()
        if payment_method not in {"", "no registrado", "no informado", "pendiente"} and payment_reference:
            add("bancarizacion", "Medios de pago", "cumple",
                "Se registró medio y referencia de pago para una operación que alcanza el umbral aplicable; no se verificó con la entidad financiera.")
        else:
            add("bancarizacion", "Medios de pago", "pendiente",
                "El importe alcanza el umbral de bancarización; registra medio y referencia de pago verificables.")
    else:
        add("bancarizacion", "Medios de pago", "no_aplica",
            "El importe está por debajo del umbral general de bancarización, sujeto a excepciones normativas.")

    if category == "representacion":
        annual_net_income = float(expense.get("ingresosNetosAnuales") or 0)
        uit = UIT_BY_YEAR.get(year or 0)
        if annual_net_income <= 0 or not uit:
            add("representacion", "Límite de gastos de representación", "pendiente",
                "Se requiere el ingreso neto del ejercicio y el valor UIT de ese año para calcular el límite.")
        else:
            legal_limit = min(annual_net_income * 0.005, uit * 40)
            spent_before = sum(
                float(item.get("monto") or 0)
                for item in previous_expenses
                if _infer_category(item)[0] == "representacion"
                and str(item.get("empresaRuc") or item.get("ruc") or "") == company_ruc
                and str(item.get("fecha") or "").startswith(str(year))
            )
            accepted = min(amount, max(0, legal_limit - spent_before))
            excess = max(0, amount - accepted)
            add("representacion", "Límite de gastos de representación", "cumple",
                f"Tope anual estimado: S/ {legal_limit:.2f} (0.5% de ingresos netos, máximo 40 UIT). Gasto previo registrado: S/ {spent_before:.2f}.")
            if negative:
                return _result("no_deducible", amount, 0, amount, criteria, missing, negative,
                               legal_basis, "Se identificó un incumplimiento esencial además del límite aplicable.",
                               observations, category_reason)
            if missing:
                return _result("condicionado", amount, None, None, criteria, missing, negative,
                               legal_basis, "El límite puede estimarse, pero faltan requisitos esenciales para determinar el importe aceptado.",
                               observations, category_reason)
            return _result("limitado", amount, accepted, excess, criteria, missing, negative,
                           legal_basis, "Gasto sujeto al límite anual de representación; el excedente no se acepta en esta evaluación preliminar.",
                           observations, category_reason)

    pending = bool(missing)
    if negative:
        status = "no_deducible"
    elif pending:
        status = "condicionado"
    else:
        status = "deducible"
    deductible = amount if status == "deducible" else 0 if status == "no_deducible" else None
    non_deductible = 0 if status == "deducible" else amount if status == "no_deducible" else None
    summary = {
        "deducible": "Los criterios disponibles no muestran observaciones; resultado preliminar sujeto a verificación documental y normativa.",
        "no_deducible": "Se identificó un incumplimiento o exclusión expresa; revisa los fundamentos aplicables.",
        "condicionado": "Faltan datos o verificaciones para determinar la deducibilidad; el sistema no presume que el gasto sea aceptado.",
    }[status]
    return _result(status, amount, deductible, non_deductible, criteria, missing, negative,
                   legal_basis, summary, observations, category_reason)


def _result(status, amount, deductible, non_deductible, criteria, missing, negative, legal_basis, summary,
            observations=(), expense_category=None):
    labels = {
        "deducible": "Deducible",
        "no_deducible": "No deducible",
        "limitado": "Limitado",
        "condicionado": "Condicionado",
    }
    return {
        "status": status,
        "label": labels[status],
        "expenseCategory": expense_category or "Gasto empresarial",
        "summary": summary,
        "amount": amount,
        "deductibleAmount": deductible,
        "nonDeductibleAmount": non_deductible,
        "criteria": criteria,
        "missing": list(dict.fromkeys(missing)),
        "observations": list(dict.fromkeys(observations)),
        "negative": list(dict.fromkeys(negative)),
        "legalBasis": legal_basis,
        "evaluatedAt": date.today().isoformat(),
        "version": 2,
    }
