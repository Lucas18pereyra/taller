# Proyectos de cámara

Estos programas son independientes de la aplicación de cocheras y estacionamiento.
Utilizan Python, OpenCV, MediaPipe y NumPy. Sus dependencias se encuentran en
`default/requirements_vision_portal.txt`; el rompecabezas usa la interfaz
`mp.solutions.hands` de MediaPipe, por lo que necesita una versión que incluya esa API.

Desde la raíz del proyecto:

```powershell
py .\cv2\default\vision_portal_FINAL.py
py .\cv2\rombecabezas\rompe.py
```

Para ejecutarlos simultáneamente, usar una terminal distinta para cada programa.
La configuración actual asigna la cámara **1** al portal y la **0** al rompecabezas.
Los índices dependen de los dispositivos conectados; revisar `CAMARA` en cada script.
Se necesitan dos cámaras disponibles para ese uso; la ejecución simultánea con ambos
dispositivos no se ha verificado.

## Vision Portal

Aplica filtros dentro de la zona delimitada por los índices y pulgares de dos manos.
El toque entre pulgar y meñique cambia el filtro según el lado de la pantalla.
También permite seleccionarlos por teclado, ocultar el esqueleto con **L**, guardar
una captura con **S** y salir con **Q** o **Esc**.

Descarga automáticamente `hand_landmarker.task` desde la dirección de MediaPipe
definida en el script si el archivo no existe. La primera descarga requiere Internet.
El modelo y las capturas no se publican en este repositorio.

`default/XD.PY` es una utilidad para identificar cámaras y comparar los backends
DSHOW y MSMF. Espera una tecla para continuar entre dispositivos.

## Rompecabezas

Se abre a pantalla completa, solicita captura en 1920×1080 y ajusta el tablero al
tamaño real del fotograma. En Full HD el tablero mide aproximadamente 880 píxeles
de lado, dejando lugar para botones y mensajes.

- **3 / 5:** elegir cuadrícula de 3×3 o 5×5.
- **Espacio:** capturar una fotografía y crear el juego.
- **Pinza índice–pulgar:** seleccionar una casilla y después otra para intercambiarlas.
- **R:** mezclar la fotografía actual.
- **N:** volver al encuadre para una nueva foto.
- **Q / Esc:** salir.

La fotografía se toma desde el vídeo limpio, sin incorporar botones ni cursor.
