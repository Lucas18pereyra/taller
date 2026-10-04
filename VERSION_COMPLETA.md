# Versión 1.4.0 completa en modo claro y con base vacía

Abrí **EstacionamientoApp.exe** de esta carpeta, o hacé doble clic en **Abrir_estacionamiento.bat**. Este acceso no usa `--demo`: muestra el login real, utiliza `estacionamiento.db` y conserva los cambios al cerrar.

Por tu pedido, esta entrega comienza con una base nueva y vacía: sin usuarios, clientes, patentes, lugares, tarifas, contratos ni cobros. Al abrirla, creá tu primer administrador. No usa cuentas demo. El tema inicial es Claro.

La aplicación contiene los módulos originales de clientes y vehículos, contratos, estacionamiento, mapa, cobros, caja, vencimientos, usuarios, configuración y reportes. El ejecutable incluye PySide6 y XlsxWriter: no requiere Python instalado para abrir ni para exportar Excel.

## Datos reales y puesta en marcha

No se agregaron clientes, tarifas, espacios, contratos ni cobros ficticios. Antes de registrar operaciones, definí los datos de tu negocio, las tarifas reales y los espacios desde Configuración, Administración y Mapa. Las comunicaciones externas usan las acciones existentes del programa; deben revisarse con tus contactos reales antes de enviarlas.

Los datos se guardan en `estacionamiento.db` junto al ejecutable. Los destinos predeterminados de reportes, comprobantes y tickets también quedan junto a esa base, no dentro de carpetas temporales. Podés seleccionar otros destinos desde Configuración. Copiar solamente el EXE a una carpeta distinta crea una base independiente; no borra ni traslada la original.

Conservá la carpeta en una ubicación con permiso de escritura, como el Escritorio o Documentos; no la ubiques en Program Files. Para pasar tus datos a otra computadora, cerrá el programa y trasladá el EXE junto con `estacionamiento.db` y tus carpetas de documentos. No reemplaces una base existente en destino sin respaldarla antes.

La base anterior se conserva en `.respaldo_visual\base-anterior-...\estacionamiento-original.db`, junto a una copia SQLite verificada y `REINICIO.json`. También se conserva el respaldo previo a la revisión en `.respaldo_visual\20261001-revision`. Esos archivos pueden contener tus usuarios y datos anteriores: mantenelos privados y no los compartas en la muestra. La demo continúa separada en `Mostrar_demo.bat` y usa sólo una base temporal.

## Correcciones de esta revisión

- No se puede eliminar un lugar con cliente asignado, contrato activo o pendiente, o patente con ingreso abierto. Se comprueba en la pantalla, al guardar y en la propia base.
- Eliminar un lugar libre lo desactiva y conserva su historial. Renombrar conserva su identidad, sus contratos y sus movimientos.
- Los cambios de tipo en el mapa sólo se guardan al confirmar; Limpiar o descartar no cambia la base.
- Se evitan ingresos/cobros duplicados por operaciones simultáneas. Los pagos de estacionamiento usan la misma fecha local que la salida.
- Fechas e importes inválidos no producen un cierre o cobro silencioso. Se corrigieron renovaciones, reportes de clientes con varias patentes y cálculos de caja.
- Los contratos con pagos permanecen en Historial. Borrar un contrato antiguo sin pagos no libera el lugar del cliente actual.
- Una base incompatible se informa sin borrar ni reparar registros automáticamente. Un respaldo inválido se rechaza antes de sustituir la base actual.
- Ventanas desplazables, controles de fecha y monto legibles, lateral adaptable y contraste mejorado para pantallas pequeñas o texto grande.

## Alcance

Se verifican lógica e interfaz con bases aisladas; las evidencias están en `preview_visual\revision_profunda` y las regresiones en `tests`. Esto no equivale a una auditoría exhaustiva de seguridad ni garantiza ausencia de cualquier error. No se verificaron impresoras físicas, comunicaciones con contactos reales ni otra PC limpia. El instalador de Inno Setup es opcional y no se generó; el EXE portable funciona sin él.
