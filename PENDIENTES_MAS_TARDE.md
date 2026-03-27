# Pendientes Guardados

Este archivo guarda mejoras acordadas para retomar mas adelante.

## Trigger acordado

Cuando digas: `Hagamos lo que te dije que guardes para mas tarde`

se retoma este bloque.

## 8) Empaquetado profesional del .exe (base implementada)

1. Icono `.ico` agregado en `assets/app_icon.ico` (reemplazable por uno final).
2. Metadatos de version listos en `installer/version_info.txt`.
3. Script de instalador Inno Setup listo en `installer/EstacionamientoApp.iss`.
4. Build reproducible listo en `build_exe.ps1` y `build_exe.bat`.
5. Falta pendiente solo la prueba en maquina limpia.

## Modo facil (pendiente)

1. Disenar un "modo facil" para operacion diaria con interfaz simplificada.
2. Definir exactamente que botones se muestran y que flujos quedan ocultos.
3. Permitir activar/desactivar desde Configuracion sin perder funciones avanzadas.
