# Plantilla de carga

`Tribuanalisis_Plantilla_Gastos_Vacia.xlsx` es el archivo vacío que entrega la página en **Carga masiva Excel** mediante `/api/expense-template.xlsx`.

Actualiza este archivo junto con los encabezados que reconoce `readBulkExcel` en `js/app.js`. No agregues una columna de clasificación: el motor evalúa cada fila.
