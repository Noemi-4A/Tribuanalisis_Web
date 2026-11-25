# Casos de prueba Excel

`Tribuanalisis_15_Casos_Gastos_Ejemplo.xlsx` contiene operaciones de ejemplo para subir desde **Carga masiva Excel**. La hoja `Gastos` usa los mismos campos que la plantilla y no incluye resultados tributarios ingresados manualmente; Tribuanálisis los calcula al importar.

El archivo original de cada importación web se conserva en `instance/casos_prueba/<id_usuario>/<id_lote>.xlsx` o `.xls`. La aplicación almacena los gastos por usuario y permite eliminar un gasto, un lote completo o todo el historial.

La hoja de prueba incluye una multa identificable como concepto no deducible y operaciones empresariales que permanecen condicionadas hasta que se adjunte el comprobante y se verifique el sustento correspondiente. El texto declarado en Excel no se considera prueba documental autenticada.
