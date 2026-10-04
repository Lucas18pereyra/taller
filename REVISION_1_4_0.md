# Entrega verificada 1.4.0 — 1 de octubre de 2026

Abrí `Abrir_estacionamiento.bat` o `EstacionamientoApp.exe` de esta carpeta.
La versión normal está en modo claro, no es demo y guarda los cambios.
La base está vacía: creá tu administrador y configurá tarifas y lugares reales.

## Correcciones principales

- Lugares: borrado bloqueado con cliente, contrato activo/pendiente o patente ingresada; protección inmediata, al guardar y en SQLite. Quitar un lugar libre lo desactiva sin borrar su historial.
- Mapa: renombrado mantiene el mismo ID y vínculos; cambios de tipo pendientes hasta Guardar; Limpiar descarta sin modificar la base. El mapa no cobra ni da de baja contratos automáticamente.
- Cobros/contratos: operaciones atómicas, protección ante concurrencia, validación de importes/fechas, tarifa aplicada conservada y fecha local coherente. Borrar un contrato antiguo no libera el lugar de otro cliente. Los contratos con pagos no se eliminan definitivamente: se conservan en Historial.
- Reportes/caja: patente correspondiente al contrato, filtro QR, cierres coherentes y error visible ante fallos de lectura. No se presentan falsos ceros ni importes anteriores; se bloquea guardar/exportar hasta recuperar la lectura.
- Datos: diagnóstico y migración de estructura sin borrar ni inferir registros. Rechazo de bases ajenas/corruptas/incompatibles. Restauración validada antes de reemplazar la base, con copia de la anterior y cierre de sesión.
- Visual: lateral adaptable/desplazable, diálogos con scroll, controles de fecha/monto legibles, columnas y tooltips, y mejor contraste.

## Pruebas realizadas

| Verificación | Resultado |
| --- | --- |
| Regresiones de lógica y ventanas Qt | 122 pasan, 0 errores, 0 omitidas |
| Visual: 1024×600 / 1366×768, texto grande, DPI 125/150 % | 6 perfiles pasan, 253 capturas, 24 diálogos |
| Visual básico claro y oscuro | Pasa |
| Programa normal: dueño, operador, reapertura y primer administrador | 4 escenarios pasan; operaciones, PDF, Excel, backup/restauración |
| Arranque con duplicados, SQLite ajeno, versión futura y corrupción | 4 rechazos seguros pasan, sin modificar los registros |
| EXE real copiado solo a otra carpeta temporal | 3 escenarios pasan: primer acceso, login y reapertura |
| Sintaxis Python | Pasa |
| Base vacía real y archivo original | Hashes verificados; base nueva intacta y original recuperable |

Las operaciones de QA usan bases temporales, no usuarios/clientes reales ni comunicaciones externas.
Evidencias en `preview_visual\revision_profunda\{regresiones,visual,normal,arranque,exe}`.
Comandos reproducibles en `BUILD_RELEASE.md`.

## Respaldo y recuperación

La base anterior no fue borrada. Se archivó en:

`.respaldo_visual\base-anterior-20261001-174229-654da913\estacionamiento-original.db`

En esa carpeta también están `estacionamiento-antes-vaciar.db` (copia SQLite verificada) y `REINICIO.json`.
Para recuperar el estado anterior, cerrá la app, respaldá cualquier dato nuevo y copiá el archivo anterior como `estacionamiento.db` en la raíz. No sobrescribas datos nuevos sin respaldo.
Estos archivos pueden contener credenciales y datos privados: no los compartas en la muestra.

## Identificación del ejecutable

- Versión Windows: `1.4.0.0`.
- Tamaño: `47.617.328` bytes.
- SHA256: `E1E5CB53406C06495FDF5DF20EBAD97549B885C9447FF95E6DF40F15F56F29A3`.
- La copia de la raíz y `dist\EstacionamientoApp.exe` son idénticas. Se conservaron los ejecutables anteriores.

## Límites de verificación

No se probaron impresoras físicas, comunicaciones con contactos reales ni otra PC limpia. No se generó el instalador opcional de Inno Setup. Esto es una revisión de lógica/interfaz con regresiones y empaquetado probado localmente, no una auditoría exhaustiva de seguridad ni una garantía de ausencia de todo error.
