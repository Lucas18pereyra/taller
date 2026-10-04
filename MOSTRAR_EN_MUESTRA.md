# Abrir la demostración

Hacé doble clic en **Mostrar_demo.bat**. También podés ejecutar `python main.py --demo` desde esta carpeta.

El modo muestra abre una base temporal nueva con datos ficticios: 24 cocheras, 16 contratos, 12 espacios por hora, seis visitas activas, cobros e historial. Los vencimientos se calculan según el día en que abrís el programa. El acceso de muestra utiliza el usuario `demo`, con rol de dueño; si se muestra el login, su contraseña es `demo`.

Los cambios de esa sesión y los reportes generados se guardan en una carpeta temporal. Al cerrar el programa se descartan y la siguiente apertura vuelve al escenario inicial. La base habitual `estacionamiento.db` no se abre, copia ni modifica en este modo.

Los nombres, documentos, patentes, direcciones y pagos son de demostración. Los teléfonos están marcados sin contacto para evitar usar números de personas reales.

Para mostrarlo en otra computadora hace falta Python con PySide6 y las dependencias habituales del programa. Este acceso inicia el código actualizado de la carpeta; un ejecutable compilado anteriormente conserva su interfaz anterior.

## Diseño y verificación

La demo abre con el nuevo tema oscuro inspirado en VS Code Dark+: fondo gris carbón, paneles neutros y acentos azules. Para volver al diseño claro con navegación azul oscuro y acentos verde agua, elegí Claro en Configuración. Se actualizaron el resumen de cocheras, la pantalla de estacionamiento, el acceso y la presentación de clientes, contratos, reportes y mapa, conservando sus acciones existentes.

Las capturas de las pantallas reales están en `preview_visual`. Para repetir las comprobaciones ejecutá `python tools\verificar_visual.py`; usa exclusivamente otra base demo temporal y comprueba navegación, filtros, selección de clientes/contratos, login, temas, tamaños de pantalla y visibilidad según rol. Las pruebas visuales se renderizan con Qt fuera de pantalla.

El archivo principal anterior al rediseño está respaldado en `.respaldo_visual\20261001\main.py`. La revisión y las mejoras del backend quedan pendientes para una etapa posterior.

Los archivos anteriores al cambio del tema oscuro están respaldados en `.respaldo_visual\20261001-vscode`.
