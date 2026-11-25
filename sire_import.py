import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from openpyxl.utils.exceptions import InvalidFileException


FIELD_ALIASES = {
    "companyRuc": ("ruc", "ruc empresa", "ruc de la empresa"),
    "companyName": (
        "apellidos y nombres o razon social",
        "razon social",
        "razon social de la empresa",
        "razon social empresa",
    ),
    "period": ("periodo", "period"),
    "car": ("car sunat", "car"),
    "issueDate": ("fecha de emision", "fecha emision", "fecha operacion"),
    "dueDate": ("fecha vcto pago", "fecha vcto pago", "fecha vencimiento", "fecha pago"),
    "voucherType": ("tipo cp doc", "tipo cp doc", "tipo comprobante", "tipo de comprobante"),
    "series": ("serie del cdp", "serie cdp", "serie", "serie cp"),
    "number": (
        "nro cp o doc nro inicial rango",
        "nro cp o doc nro inicial",
        "nro cp o doc",
        "numero",
        "numero comprobante",
        "numero de comprobante",
        "nro cp doc",
    ),
    "rangeEnd": ("nro final rango", "nro cp o doc nro final rango"),
    "supplierIdType": ("tipo doc identidad", "tipo documento identidad"),
    "supplierRuc": (
        "nro doc identidad",
        "numero doc identidad",
        "ruc del proveedor",
        "ruc proveedor",
    ),
    "supplierName": (
        "apellidos nombres razon social",
        "apellidos y nombres razon social",
        "razon social del proveedor",
        "proveedor",
    ),
    "baseDG": ("bi gravado dg",),
    "baseOrdinary": ("base imponible", "importe sin igv s"),
    "igvOrdinary": ("igv",),
    "igvDG": ("igv ipm dg",),
    "baseDGNG": ("bi gravado dgng",),
    "igvDGNG": ("igv ipm dgng",),
    "baseDNG": ("bi gravado dng",),
    "igvDNG": ("igv ipm dng",),
    "nonTaxableAcquisition": ("valor adq ng",),
    "isc": ("isc",),
    "icbper": ("icbper",),
    "otherCharges": ("otros trib cargos", "otros tributos cargos"),
    "total": ("total cp", "importe total s", "importe total", "total"),
    "currency": ("moneda",),
    "exchangeRate": ("tipo de cambio",),
    "detailedDescription": (
        "descripcion detallada del gasto",
        "descripcion del gasto",
        "concepto",
    ),
    "companyActivity": (
        "actividad economica de la empresa",
        "actividad economica empresa",
        "actividad economica principal",
        "actividad economica",
    ),
    "purpose": (
        "finalidad o uso declarado",
        "finalidad empresarial",
        "finalidad del gasto",
        "finalidad y detalle de operacion",
        "finalidad y detalle",
        "uso declarado",
    ),
    "serviceDate": ("fecha de recepcion o prestacion", "fecha servicio"),
    "evidence": (
        "evidencia de recepcion del bien o servicio",
        "evidencia de la operacion",
        "evidencia de operacion",
        "sustento adicional disponible",
        "sustento adicional",
        "contrato orden de compra u otro vinculo",
        "documentos adicionales disponibles",
        "observaciones nombre del archivo sustentatorio",
    ),
    "paymentMethod": ("medio de pago",),
    "paymentReference": (
        "referencia de pago operacion bancaria",
        "referencia de pago",
    ),
    "referenceAmount": ("presupuesto o referencia", "valor de referencia"),
    "annualNetIncome": (
        "ingresos netos del ejercicio s",
        "ingresos netos del ejercicio",
        "ingresos netos anuales",
    ),
    "receiverRuc": ("ruc receptor", "ruc del receptor"),
    "operationType": ("tipo de operacion", "tipo operacion"),
}

SIRE_SIGNATURE = {
    "companyRuc",
    "period",
    "issueDate",
    "voucherType",
    "series",
    "number",
    "supplierRuc",
}

LEGACY_SIGNATURE = {
    "companyRuc",
    "companyName",
    "issueDate",
    "voucherType",
    "supplierRuc",
}

SIRE_TYPE_LABELS = {
    "01": "Factura",
    "03": "Boleta de venta",
    "04": "Liquidación de compra",
    "07": "Nota de crédito",
    "08": "Nota de débito",
    "12": "Ticket de máquina registradora",
    "14": "Recibo de servicios públicos",
    "20": "Comprobante de retención",
}


def normalize_header(value):
    normalized = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def _header_fields(headers):
    normalized = [normalize_header(value) for value in headers]
    fields = {}
    for field, aliases in FIELD_ALIASES.items():
        candidates = set(aliases)
        for index, header in enumerate(normalized):
            if header in candidates:
                fields[field] = index
                break
    return fields


def _find_header(worksheet, signature, max_rows=40):
    for row_index, row in enumerate(
        worksheet.iter_rows(min_row=1, max_row=min(worksheet.max_row or 1, max_rows), values_only=True),
        start=1,
    ):
        fields = _header_fields(row)
        if signature.issubset(fields):
            return row_index, tuple(row), fields
    return None


def _cell_value(cell):
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        number_format = str(cell.number_format or "")
        if isinstance(value, int) and re.fullmatch(r"0+", number_format):
            return str(value).zfill(len(number_format))
        if isinstance(value, float) and value.is_integer() and re.fullmatch(r"0+", number_format):
            return str(int(value)).zfill(len(number_format))
        if isinstance(value, float):
            return value
        return str(value)
    return str(value).strip()


def _as_text(value):
    if value in (None, ""):
        return ""
    return str(value).strip()


def _as_amount(value):
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    text = re.sub(r"[^\d,.\-]", "", str(value).strip())
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return 0.0
    return float(amount) if amount.is_finite() else 0.0


def _as_date(value):
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    text = _as_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d{5}", text) and 20000 <= int(text) <= 80000:
        converted = from_excel(int(text))
        if isinstance(converted, (datetime, date)):
            return converted.strftime("%Y-%m-%d")
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if pattern == "%Y-%m-%d" else text, pattern).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _period(value, issue_date):
    text = _as_text(value)
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y%m")
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 6:
        return digits[:6]
    if len(digits) == 4:
        return digits
    return issue_date[:7].replace("-", "") if issue_date else ""


def _valid_ruc(value):
    ruc = _as_text(value)
    if not re.fullmatch(r"\d{11}", ruc):
        return False
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    check = 11 - sum(int(digit) * weight for digit, weight in zip(ruc[:10], weights)) % 11
    expected = 0 if check == 10 else 1 if check == 11 else check
    return int(ruc[-1]) == expected


def _voucher_key(value):
    text = _as_text(value).upper()
    if re.fullmatch(r"\d{1,2}", text):
        text = text.zfill(2)
    if text in SIRE_TYPE_LABELS:
        return SIRE_TYPE_LABELS[text].upper()
    digits = re.sub(r"\D", "", text)
    if len(digits) == 2 and digits in SIRE_TYPE_LABELS:
        return SIRE_TYPE_LABELS[digits].upper()
    return normalize_header(text)


def _record_key(record):
    values = (
        record.get("companyRuc"),
        record.get("period"),
        _voucher_key(record.get("voucherType")),
        _normalize_document_number(record.get("series")),
        _normalize_document_number(record.get("number")),
        _as_text(record.get("supplierRuc")),
    )
    if not all(values):
        return None
    return "|".join(values)


def _normalize_document_number(value):
    text = _as_text(value).upper()
    if text.isdigit():
        return text.lstrip("0") or "0"
    return re.sub(r"\s+", "", text)


def _row_dict(worksheet, row_index, headers):
    cells = next(worksheet.iter_rows(min_row=row_index, max_row=row_index))
    return {
        str(header).strip(): _cell_value(cells[index])
        for index, header in enumerate(headers)
        if header not in (None, "") and index < len(cells)
    }


def _field_value(cells, fields, key):
    index = fields.get(key)
    if index is None or index >= len(cells):
        return ""
    return _cell_value(cells[index])


def _read_context(workbook):
    worksheet = next(
        (sheet for sheet in workbook.worksheets if normalize_header(sheet.title) == "contexto de casos"),
        None,
    )
    if worksheet is None:
        return {}, None
    header = _find_header(worksheet, SIRE_SIGNATURE | {"supplierName"})
    if header is None:
        header = _find_header(worksheet, {"companyRuc", "period", "voucherType", "series", "number", "supplierRuc"})
    if header is None:
        return {}, f"La hoja «{worksheet.title}» existe, pero no contiene las columnas necesarias para relacionar el contexto."
    header_row, headers, fields = header
    contexts = {}
    for row_index, cells in enumerate(worksheet.iter_rows(min_row=header_row + 1), start=header_row + 1):
        record = {
            field: _field_value(cells, fields, field)
            for field in FIELD_ALIASES
            if field in fields
        }
        for field in FIELD_ALIASES:
            record.setdefault(field, "")
        if not any(record.values()):
            continue
        issue_date = _as_date(record.get("issueDate"))
        record["period"] = _period(record.get("period"), issue_date)
        record["companyRuc"] = _as_text(record.get("companyRuc"))
        record["supplierRuc"] = _as_text(record.get("supplierRuc"))
        record["voucherType"] = _as_text(record.get("voucherType"))
        record["series"] = _as_text(record.get("series"))
        record["number"] = _as_text(record.get("number"))
        key = _record_key(record)
        if key:
            contexts.setdefault(key, record)
    return contexts, None


def _locate_purchase_sheet(workbook):
    candidates = []
    for worksheet in workbook.worksheets:
        header = _find_header(worksheet, SIRE_SIGNATURE)
        if header:
            row_index, headers, fields = header
            candidates.append((2, worksheet, row_index, headers, fields))
            continue
        header = _find_header(worksheet, LEGACY_SIGNATURE)
        if header:
            row_index, headers, fields = header
            candidates.append((1, worksheet, row_index, headers, fields))
    if not candidates:
        raise ValueError("No se encontró una hoja de Registro de Compras SIRE ni encabezados de Tribuanálisis reconocibles.")
    _, worksheet, row_index, headers, fields = max(candidates, key=lambda item: item[0])
    return worksheet, row_index, headers, fields


def parse_purchase_workbook(content):
    try:
        workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
    except (OSError, ValueError, TypeError, BadZipFile, InvalidFileException) as error:
        raise ValueError("No se pudo abrir el Excel. Verifica que sea un archivo XLSX válido.") from error
    try:
        worksheet, header_row, headers, fields = _locate_purchase_sheet(workbook)
        contexts, context_warning = _read_context(workbook)
        is_sire = SIRE_SIGNATURE.issubset(fields)
        operations = []
        errors = []
        seen_keys = set()
        duplicate_count = 0
        for row_index, cells in enumerate(worksheet.iter_rows(min_row=header_row + 1), start=header_row + 1):
            row_values = [_cell_value(cell) for cell in cells[:len(headers)]]
            if not any(value not in ("", None) for value in row_values):
                continue
            record = {
                field: _field_value(cells, fields, field)
                for field in FIELD_ALIASES
                if field in fields
            }
            for field in FIELD_ALIASES:
                record.setdefault(field, "")
            issue_date = _as_date(record.get("issueDate"))
            period = _period(record.get("period"), issue_date)
            company_ruc = _as_text(record.get("companyRuc"))
            supplier_ruc = _as_text(record.get("supplierRuc"))
            record["companyRuc"] = company_ruc
            record["supplierRuc"] = supplier_ruc
            record["issueDate"] = issue_date
            record["period"] = period
            record["dueDate"] = _as_date(record.get("dueDate"))
            record["serviceDate"] = _as_date(record.get("serviceDate"))
            record["voucherType"] = _as_text(record.get("voucherType"))
            if re.fullmatch(r"\d{1,2}", record["voucherType"]):
                record["voucherType"] = record["voucherType"].zfill(2)
            record["series"] = _as_text(record.get("series"))
            record["number"] = _as_text(record.get("number"))
            record["rangeEnd"] = _as_text(record.get("rangeEnd"))
            record["car"] = _as_text(record.get("car"))
            record["currency"] = _as_text(record.get("currency")).upper()
            record["exchangeRate"] = _as_amount(record.get("exchangeRate"))
            record["supplierName"] = _as_text(record.get("supplierName"))
            record["companyName"] = _as_text(record.get("companyName"))

            key = _record_key(record)
            context = contexts.get(key, {}) if key else {}
            for field in (
                "detailedDescription", "companyActivity", "purpose", "evidence",
                "serviceDate", "paymentMethod", "paymentReference", "referenceAmount",
                "annualNetIncome", "receiverRuc", "operationType",
            ):
                if not record.get(field) and context.get(field) not in (None, ""):
                    record[field] = context[field]

            if not company_ruc:
                errors.append({"row": row_index, "message": "No se puede identificar la empresa: falta el RUC de la operación."})
                continue
            if not re.fullmatch(r"\d{11}", company_ruc):
                errors.append({"row": row_index, "message": f"El RUC de empresa «{company_ruc}» debe tener 11 dígitos para identificar la operación."})
                continue

            if context and record["number"].isdigit() and str(context.get("number") or "").isdigit():
                context_number = str(context["number"])
                if len(context_number) > len(record["number"]):
                    record["number"] = context_number

            if record["voucherType"] in SIRE_TYPE_LABELS:
                voucher_label = SIRE_TYPE_LABELS[record["voucherType"]]
            else:
                voucher_label = record["voucherType"]
            series_number = record["number"]
            if record["rangeEnd"] and record["rangeEnd"] != record["number"]:
                series_number = f"{series_number}-{record['rangeEnd']}" if series_number else record["rangeEnd"]
            invoice_number = f"{record['series']}-{series_number}" if record["series"] and series_number else series_number or record["series"]

            amount_fields = ("baseDG", "igvDG", "baseDGNG", "igvDGNG", "baseDNG", "igvDNG",
                             "nonTaxableAcquisition", "isc", "icbper", "otherCharges")
            amounts = {name: _as_amount(record.get(name)) for name in amount_fields}
            amounts["baseOrdinary"] = _as_amount(record.get("baseOrdinary"))
            amounts["igvOrdinary"] = _as_amount(record.get("igvOrdinary"))
            total = _as_amount(record.get("total"))
            if total <= 0:
                total = sum(amounts.values())
            base = sum(amounts[name] for name in ("baseDG", "baseDGNG", "baseDNG", "nonTaxableAcquisition", "baseOrdinary"))
            igv = sum(amounts[name] for name in ("igvDG", "igvDGNG", "igvDNG", "igvOrdinary"))

            issues = []
            if not _valid_ruc(company_ruc):
                issues.append("El RUC de empresa no supera el dígito verificador; la evaluación lo marcará como pendiente.")
            if supplier_ruc and not _valid_ruc(supplier_ruc):
                issues.append("El RUC o documento del proveedor no supera el dígito verificador; requiere verificación.")
            if not issue_date:
                issues.append("Fecha de emisión pendiente o con formato no reconocido.")
            if not invoice_number:
                issues.append("Número de comprobante pendiente.")
            if not _as_text(record["detailedDescription"]):
                issues.append("Descripción detallada del gasto pendiente de complementar.")
            if not _as_text(record["companyActivity"]):
                issues.append("Actividad económica no informada en el archivo; se intentará consultar por RUC.")
            duplicate_within_file = bool(key and key in seen_keys)
            if duplicate_within_file:
                duplicate_count += 1
                errors.append({"row": row_index, "message": "Posible comprobante duplicado dentro del archivo; se omitirá."})
            else:
                if key:
                    seen_keys.add(key)

            raw_fields = [
                {"header": str(header).strip(), "value": _cell_value(cells[index])}
                for index, header in enumerate(headers)
                if header not in (None, "") and index < len(cells) and _cell_value(cells[index]) not in ("", None)
            ]
            operations.append({
                "row": row_index,
                "companyRuc": company_ruc,
                "companyName": record["companyName"],
                "companyActivity": _as_text(record.get("companyActivity")),
                "period": period,
                "car": record["car"],
                "fecha": issue_date,
                "fechaVencimientoPago": record["dueDate"],
                "fechaServicio": _as_date(record.get("serviceDate")),
                "codigoTipoComprobante": _as_text(record["voucherType"]),
                "tipoComprobante": voucher_label,
                "tipoDocumentoIdentidadProveedor": _as_text(record.get("supplierIdType")),
                "supplierRuc": supplier_ruc,
                "supplierName": record["supplierName"],
                "series": record["series"],
                "number": invoice_number,
                "voucherNumber": record["number"],
                "rangeEnd": record["rangeEnd"],
                "receiverRuc": _as_text(record.get("receiverRuc")),
                "detailedDescription": _as_text(record.get("detailedDescription")),
                "purpose": _as_text(record.get("purpose")),
                "evidence": _as_text(record.get("evidence")),
                "operationType": _as_text(record.get("operationType")),
                "paymentMethod": _as_text(record.get("paymentMethod")),
                "paymentReference": _as_text(record.get("paymentReference")),
                "referenceAmount": _as_amount(record.get("referenceAmount")),
                "annualNetIncome": _as_amount(record.get("annualNetIncome")),
                "currency": record["currency"] or "PEN",
                "exchangeRate": _as_amount(record.get("exchangeRate")),
                "base": base,
                "igv": igv,
                "total": total,
                "amountBreakdown": amounts,
                "sireFields": raw_fields,
                "contextMatched": bool(context),
                "dedupeKey": key or "",
                "issues": issues,
                "duplicateWithinFile": duplicate_within_file,
            })

        unique_companies = {}
        for operation in operations:
            unique_companies.setdefault(operation["companyRuc"], operation["companyName"])
        if context_warning:
            errors.append({"row": None, "message": context_warning})
        return {
            "sheetName": worksheet.title,
            "isSire": is_sire,
            "headerCount": sum(1 for header in headers if header not in (None, "")),
            "operationCount": len(operations),
            "companies": [{"ruc": ruc, "name": name} for ruc, name in unique_companies.items()],
            "duplicateCount": duplicate_count,
            "errors": errors,
            "operations": operations,
        }
    finally:
        workbook.close()
