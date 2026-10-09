# Archivos del proyecto y comentarios de main.py

Revisión: 6 de octubre de 2026. Esta revisión no eliminó ni trasladó archivos.

## Qué conviene conservar

| Archivo o carpeta | Para qué sirve |
| --- | --- |
| `EstacionamientoApp.exe` | Aplicación compilada que se abre habitualmente. |
| `Abrir_estacionamiento.bat` | Acceso que abre el ejecutable y, si falta, intenta ejecutar el código fuente. |
| `estacionamiento.db` | Datos actuales: negocio, tarifas, usuarios, mapa, clientes y operaciones. |
| `backups/` | Copias de seguridad para recuperar datos. |
| `main.py` | Diálogos, navegación, validaciones de pantalla y coordinación de operaciones. |
| `database.py` | Ubicación, conexiones, estructura e integridad de la base. |
| `servicios/` | Operaciones y reglas de contratos, cobros, espacios, reportes y respaldos. |
| `presentacion.py`, `presentacion_estilos.py` | Presentación visual de la aplicación; no son la presentación de diapositivas. |
| `ui_ventana_principal.py` | Widgets de la ventana principal generados desde el diseño de Qt. |
| `ventana_principal.ui` | Diseño editable de esa ventana para mantener y regenerar la UI. |
| `assets/` | Icono de la aplicación y recurso visual de las casillas. |
| `requirements*.txt`, `.venv/` | Dependencias y entorno para ejecutar, probar o compilar el código fuente. |
| `tests/`, `tools/` | Pruebas y utilidades de verificación y preparación. |
| `build_exe*`, `build_installer*`, `EstacionamientoApp.spec`, `installer/` | Herramientas para generar el ejecutable y el instalador. |
| Archivos `.md` | Documentación de uso, construcción y cambios. |

El ejecutable actual empaqueta los módulos Python, Qt y los recursos declarados en su configuración. Para usar esa versión compilada no hace falta llevar todo el entorno de desarrollo. La base se busca junto al ejecutable por defecto, o en la carpeta indicada por `ESTACIONAMIENTO_DATA_DIR`. Las carpetas de reportes, comprobantes y tickets también pueden estar configuradas fuera de esta carpeta.

## Archivos regenerables o que se pueden apartar

| Carpeta o archivo | Tamaño aproximado | Recomendación |
| --- | ---: | --- |
| `build/` | 51,55 MB | Archivos intermedios de compilación. Se regeneran al compilar. |
| `dist/EstacionamientoApp.exe` | 48,41 MB | Copia idéntica al ejecutable de la raíz, comprobada mediante SHA-256. Puede retirarse si se conserva el de la raíz; la compilación vuelve a generarla. |
| `__pycache__/` | 0,86 MB en la raíz | Caché de Python; se regenera. También hay cachés en subcarpetas. |
| `preview_visual/` | 47,33 MB | Evidencias de pruebas y revisiones visuales. Se pueden archivar fuera de la carpeta de uso diario. |
| `.respaldo_visual/` | 796,48 MB | Versiones anteriores y respaldos de trabajo. Conviene archivarlos y conservar una copia recuperable. |
| `material_muestra/` | 46,74 MB, sin seguir enlaces | Capturas, presentación y preparación de la muestra. Conviene conservar los entregables y apartar los archivos de preparación. |
| `.venv/` | 744,00 MB | Prescindible para abrir el ejecutable compilado; conservarla mientras se programa y se prueba la app. |
| `Mostrar_demo.bat`, `demo_muestra.py` | Pequeño | Flujo de demostración temporal. Eliminarlo del código exige ajustar también la opción `--demo`; no es parte de la limpieza de cachés. |
| `cv2/` | 14,97 MB | No se encontraron referencias desde el código de la app ni desde su configuración de compilación. Contiene material añadido recientemente; conviene revisar su finalidad antes de apartarlo. |

`material_muestra/presentacion_canva/.build/node_modules` es un enlace a dependencias externas, no una copia local. No se siguió ese enlace al medir tamaños. Los archivos de preparación de la base dentro de `material_muestra/` incluyen copias de los datos de la aplicación.

Los candidatos inmediatos a limpieza son `build/`, la copia duplicada de `dist/` y las cachés: aproximadamente 101 MB. Los respaldos y el material de la muestra ocupan más espacio, pero conservan trabajo o información útil.

## Cómo leer main.py

Los comentarios agregados explican las secciones y los pasos importantes de la lógica. Se usaron comentarios `#`, sin modificar instrucciones ni textos que utiliza el programa.

1. **Funciones auxiliares:** identidad, errores, validación, formato argentino de números y patentes, configuración, rutas y PDF.
2. **Acceso y operación rápida:** inicio de sesión, primer dueño, administración de usuarios y modo sencillo de estacionamiento.
3. **Contratos y clientes:** asignación de cochera, selección desde el mapa, primer pago, renovación, baja e historial.
4. **Mapa y administración:** tarifas, casillas, alineado, cambios pendientes, vencimientos, reportes, caja y respaldos.
5. **Ventana principal:** permisos, navegación, atajos, resumen, ingreso y salida por hora.
6. **Punto de entrada:** preparación de la base y de Qt, diagnóstico, demostración y elección del flujo de acceso.

Para buscar una parte concreta, usar nombres como `ContratosDialog`, `MapaCocheraDialog`, `_registrar_ingreso_est`, `_registrar_salida_est` o `if __name__ == "__main__"`.

Los comentarios explican el comportamiento actual, incluidos sus límites: por ejemplo, abrir un chat de WhatsApp no confirma que se haya enviado el mensaje, y crear un contrato no lo activa hasta registrar el primer pago.
