# Tribuanálisis — Matriz de evaluación de gastos empresariales

Aplicación académica Flask para registrar operaciones por empresa, extraer datos disponibles de comprobantes, evaluar criterios tributarios y mantener una matriz empresarial por usuario y RUC.

## Inicio local

```powershell
python -m pip install -r requirements.txt
python app.py
```

La aplicación abre `http://127.0.0.1:5000/`. Sin una URL PostgreSQL, los datos se guardan localmente en `instance/tribuanalisis.db` y los documentos como contenido binario en SQLite. Define `TRIBUANALISIS_DB` o `TRIBUANALISIS_INSTANCE` para cambiar la ubicación. Para conservar sesiones entre reinicios, configura una clave privada estable en `TRIBUANALISIS_SECRET_KEY`.

## Supabase y Vercel

En Vercel, configura estas variables en **Project → Settings → Environment Variables** para Production, Preview y Development:

- `SUPABASE_DB_URL`: cadena de conexión PostgreSQL de Supabase. Se recomienda la conexión **Transaction pooler** para funciones serverless. No la publiques ni la subas a GitHub.
- `TRIBUANALISIS_SECRET_KEY`: una clave aleatoria privada, estable entre despliegues e instancias. Sin ambas variables, la aplicación falla explícitamente al iniciar en Vercel; no guarda datos en SQLite temporal como alternativa.

La aplicación crea el esquema privado `tribuanalisis` y sus tablas al iniciar. En Supabase, consulta las cuentas en **Table Editor → schema `tribuanalisis` → `users`**. Las contraseñas se guardan como hashes. El esquema no necesita exponerse mediante la API REST de Supabase: la conexión es directa desde Flask. La URL y la clave deben guardarse solo como variables de entorno de Vercel.

Las cuentas nuevas y los datos guardados después de configurar PostgreSQL quedan persistidos en Supabase. No se migran automáticamente cuentas ni registros de una base SQLite anterior; no subas `instance/tribuanalisis.db` a GitHub. Los documentos adjuntos se guardan como BLOB en PostgreSQL. El archivo Excel de origen de cada importación se mantiene como archivo temporal en `/tmp/tribuanalisis` en Vercel; las operaciones importadas y sus matrices sí se guardan en PostgreSQL.

## Funcionalidad

- Registro e inicio de sesión de servidor, con contraseñas guardadas mediante hash y espacios de trabajo aislados por cuenta.
- Registro persistente de empresas por usuario y RUC, independiente de que ya tengan gastos; las operaciones y documentos se agrupan por la empresa propietaria.
- Registro manual sin cuestionarios de deducibilidad: la plataforma analiza automáticamente los datos disponibles.
- Carga de XML, PDF, JPG y PNG. El contenido se conserva y se extraen campos disponibles para sugerir datos al formulario; revisa siempre esos valores.
- Importación masiva Excel: cada fila con datos se procesa como una operación independiente y se asocia a su RUC. Las filas incompletas se conservan con observaciones; el motor asigna su resultado.
- Historial y ficha por gasto, ficha de empresa, comprobantes relacionados, matriz acumulativa por empresa, filtros por empresa/clasificación/ejercicio, resumen visual, tabla paginada y exportación XLSX.
- Evaluación explicable con referencias a la Ley del Impuesto a la Renta, incluidos los artículos 37, 44 y 57, y requisitos como devengo y bancarización.

El importador detecta encabezados por nombre, no por posición, e identifica la hoja de Registro de Compras en los archivos SIRE. Admite el formato SIRE original de 80 columnas y el formato personalizado de 81 columnas con «Descripción detallada del gasto», conserva los valores no vacíos de otras columnas y no exige que CAR SUNAT esté informado. La hoja opcional «Contexto de casos» se relaciona por RUC empresa, periodo, tipo y número de comprobante, serie y RUC proveedor. Las filas sin contexto suficiente quedan sujetas a evaluación condicionada; la aplicación no importa una clasificación desde Excel.

La plantilla descargable se conserva en `plantillas_excel/Tribuanalisis_Plantilla_Gastos_Vacia.xlsx`; el libro demostrativo está en `casos_prueba/Tribuanalisis_15_Casos_Gastos_Ejemplo.xlsx`. La aplicación calcula la categoría en lugar de leerla de una columna de clasificación. Los Excel importados se archivan de forma privada por usuario y lote.

Las ilustraciones temáticas de la página **Guía y normativa** están en `assets/images/normativa/`; cada archivo SVG se usa únicamente en su criterio correspondiente. Se pueden agregar allí nuevos recursos visuales y enlazarlos desde esa sección.

Cada Excel importado se archiva de forma privada en `instance/casos_prueba/<id_usuario>/` localmente (en Vercel, bajo `/tmp/tribuanalisis/casos_prueba/`) y se vincula con su lote. Desde **Historial de análisis** se puede eliminar un gasto, un lote importado o todos los gastos; eliminar el historial conserva las empresas y los comprobantes independientes.

## Extracción y consulta de RUC

- XML: lectura de campos estructurados del comprobante.
- PDF: extracción de texto con PyMuPDF. Para documentos escaneados e imágenes se requiere el ejecutable Tesseract y el paquete de idioma español, además de Pillow y pytesseract. Si Tesseract no está en `PATH`, define `TESSERACT_CMD`.
- OCR y extracción no certifican la autenticidad del documento ni acreditan por sí solos la realidad de la operación.
- La búsqueda automática de RUC requiere `DECOLECTA_API_TOKEN` (variable de entorno) o el valor local en `config.json`, basado en `config.example.json`. Es un proveedor externo con datos basados en SUNAT, **no una consulta oficial directa**. Se muestran y guardan, cuando la respuesta las incluye, la actividad principal y secundaria, código CIIU, estado, condición, fuente y fecha de consulta.
- No se ha configurado una integración oficial de SUNAT para estado/condición de RUC ni consulta de validez CPE. Esos estados permanecen explícitamente pendientes; el enlace permite abrir la consulta pública de SUNAT manualmente.
- SheetJS se carga desde CDN para exportar Excel y convertir archivos `.xls`; se requiere conexión a Internet para esa biblioteca. Los `.xlsx` se procesan en el servidor.

## Alcance legal

Los resultados —Deducible, No deducible, Limitado o Condicionado— son una preevaluación automática y no reemplazan la revisión profesional ni la normativa vigente aplicable al ejercicio. Cuando los datos o verificaciones no bastan, el motor debe dejar el gasto condicionado y mostrar lo pendiente. La clasificación de un documento no se considera validación de SUNAT.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```
