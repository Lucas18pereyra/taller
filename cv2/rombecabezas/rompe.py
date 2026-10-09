# Rompecabezas con cámara: captura una imagen y permite ordenar sus piezas mediante gestos.
# La punta del índice funciona como cursor y la pinza índice–pulgar produce una selección.
# Se intercambian dos casillas elegidas, sin casilla vacía ni restricción de vecindad.
# El detector, la cámara y el bucle se ejecutan al cargar este archivo, incluso si se importa.

import cv2
import mediapipe as mp
import numpy as np
import random
import math



# Dispositivo de captura y resolución solicitada; el tamaño real se obtiene de cada fotograma.
CAMARA = 0

ANCHO_CAMARA = 1920
ALTO_CAMARA = 1080

# La ventana escala el vídeo al monitor; el tablero reserva espacio para los controles.
NOMBRE_VENTANA = "Rompecabezas CV2"
MARGEN_SUPERIOR = 90
MARGEN_INFERIOR = 110
MARGEN_LATERAL = 40

# Cantidad de filas y columnas: los controles permiten elegir 3×3 o 5×5.
GRID = 3



# Usa la interfaz Hands de MediaPipe para detectar y seguir una mano en vídeo.
mp_hands = mp.solutions.hands

# Con static_image_mode=False se aprovecha el seguimiento entre fotogramas.
# Los umbrales de confianza se aplican a detección y seguimiento.
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)



# Abre la cámara con el backend elegido por OpenCV y solicita las dimensiones configuradas.
cap = cv2.VideoCapture(CAMARA)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, ANCHO_CAMARA)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTO_CAMARA)



# Imagen fija capturada para el juego; permanece separada del vídeo en vivo.
imagen_rompecabezas = None

# Cada elemento indica qué pieza original ocupa esa posición del tablero.
# Por ejemplo, piezas[0]=4 coloca el recorte original número 4 en la primera casilla.
piezas = []

# False muestra el encuadre para capturar; True compone y permite resolver el rompecabezas.
jugando = False

# Recuerda el gesto del fotograma anterior para generar un clic sólo al iniciar la pinza.
pinza_anterior = False

# Índice de la primera casilla elegida; None indica que aún no hay una selección.
pieza_seleccionada = None

# El contador mide fotogramas de visibilidad del mensaje, no segundos.
mensaje = ""
contador_mensaje = 0



# Calcula la distancia euclídea en píxeles entre dos puntos de la mano.
def distancia(p1, p2):

    return math.hypot(
        p1[0] - p2[0],
        p1[1] - p2[1]
    )


# Obtiene un tablero cuadrado dentro del área libre, centrado entre los márgenes.
# Captura y dibujo comparten este cálculo para que los recortes coincidan.
def calcular_tablero(ancho, alto, grid):
    lado = min(
        ancho - MARGEN_LATERAL * 2,
        alto - MARGEN_SUPERIOR - MARGEN_INFERIOR
    )
    lado -= lado % grid
    if lado < grid:
        raise ValueError("La imagen de la camara es demasiado pequena para el tablero.")
    x = (ancho - lado) // 2
    y = MARGEN_SUPERIOR + (
        alto - MARGEN_SUPERIOR - MARGEN_INFERIOR - lado
    ) // 2
    return lado, x, y, x + lado, y + lado



# Crea los identificadores en su orden correcto, recorriendo el tablero por filas.
# La imagen se divide mediante coordenadas al dibujar; aquí sólo se genera la lista de IDs.
def crear_puzzle(grid):

    cantidad = grid * grid

    piezas = list(range(cantidad))

    return piezas



# Baraja la lista recibida en su lugar y repite si quedó en el orden correcto.
# Se utiliza con tableros de 9 o 25 piezas, donde existe más de una disposición posible.
def mezclar_puzzle(piezas):

    random.shuffle(piezas)

    while puzzle_completo(piezas):
        random.shuffle(piezas)

    return piezas



# Comprueba si cada posición contiene la pieza de igual identificador, que es el orden original.
def puzzle_completo(piezas):

    solucion = list(range(len(piezas)))

    return piezas == solucion



# Intercambia dos posiciones de la lista; los recortes de la imagen original permanecen intactos.
def intercambiar_piezas(piezas, posicion_1, posicion_2):

    piezas[posicion_1], piezas[posicion_2] = (
        piezas[posicion_2],
        piezas[posicion_1]
    )



# Dibuja fondo, borde y texto centrado directamente sobre el fotograma.
# activo destaca el modo elegido; los colores de OpenCV se expresan en orden BGR.
def dibujar_boton(frame, texto, x1, y1, x2, y2, activo=False):

    if activo:
        color = (0, 180, 70)
    else:
        color = (70, 70, 70)

    cv2.rectangle(
        frame,
        (x1, y1),
        (x2, y2),
        color,
        -1
    )

    cv2.rectangle(
        frame,
        (x1, y1),
        (x2, y2),
        (255, 255, 255),
        2
    )

    tamaño = cv2.getTextSize(
        texto,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        2
    )[0]

    tx = x1 + ((x2 - x1) - tamaño[0]) // 2
    ty = y1 + ((y2 - y1) + tamaño[1]) // 2

    cv2.putText(
        frame,
        texto,
        (tx, ty),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )



# Comprueba si el cursor está dentro del botón, incluyendo sus bordes.
def punto_en_rectangulo(punto, rect):

    x, y = punto

    x1, y1, x2, y2 = rect

    return (
        x1 <= x <= x2
        and
        y1 <= y <= y2
    )



# En cada ciclo: lee la cámara, detecta el gesto, compone la vista y procesa el teclado.
# Un fallo de lectura o la tecla q termina el bucle.
# WINDOW_NORMAL permite ajustar el vídeo al monitor, conservando su proporción.
cv2.namedWindow(NOMBRE_VENTANA, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
cv2.setWindowProperty(NOMBRE_VENTANA, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

while True:

    ret, frame = cap.read()

    if not ret:
        print("No se pudo abrir la camara")
        break


    # Refleja la imagen horizontalmente para que el movimiento resulte similar al de un espejo.
    frame = cv2.flip(frame, 1)

    # Conserva una copia del vídeo sin botones, cuadrícula ni cursor para la fotografía del juego.
    frame_original = frame.copy()


    alto, ancho = frame.shape[:2]



    # Aprovecha el tamaño del vídeo y deja libres las franjas de botones y mensajes.
    tamaño_tablero, tablero_x, tablero_y, tablero_x2, tablero_y2 = calcular_tablero(
        ancho, alto, GRID
    )



    # MediaPipe necesita RGB; la cámara y el dibujo de OpenCV utilizan BGR.
    rgb = cv2.cvtColor(
        frame_original,
        cv2.COLOR_BGR2RGB
    )

    resultados = hands.process(rgb)


    # Reinicia los puntos y el gesto en cada ciclo: si no hay mano, no se conserva un cursor antiguo.
    indice = None
    pulgar = None

    pinza = False


    if resultados.multi_hand_landmarks:

        mano = resultados.multi_hand_landmarks[0]

        landmarks = mano.landmark


        # Convierte la punta del índice (landmark 8) desde coordenadas normalizadas a píxeles.
        indice = (
            int(landmarks[8].x * ancho),
            int(landmarks[8].y * alto)
        )


        # La punta del pulgar (landmark 4) se compara con el índice para reconocer la pinza.
        pulgar = (
            int(landmarks[4].x * ancho),
            int(landmarks[4].y * alto)
        )


        # Las bases del índice (5) y del meñique (17) sirven para estimar el ancho aparente de la mano.
        punto_5 = (
            int(landmarks[5].x * ancho),
            int(landmarks[5].y * alto)
        )


        punto_17 = (
            int(landmarks[17].x * ancho),
            int(landmarks[17].y * alto)
        )


        dist_pinza = distancia(
            indice,
            pulgar
        )

        ancho_mano = distancia(
            punto_5,
            punto_17
        )


        # Normaliza la separación de los dedos por el ancho de la mano para adaptarse a su distancia.
        # Sólo divide si el ancho es positivo; una proporción menor a 0,38 activa la pinza.
        if ancho_mano > 0:

            ratio = dist_pinza / ancho_mano

            if ratio < 0.38:
                pinza = True



    # Detecta el comienzo del gesto: mantener la pinza no produce selecciones repetidas.
    # Para otro clic hay que separar los dedos y volver a juntarlos.
    click = pinza and not pinza_anterior



    # Define los rectángulos de los modos en coordenadas de pantalla para dibujarlos y detectar clics.
    boton_3 = (
        tablero_x,
        15,
        tablero_x + 120,
        60
    )

    boton_5 = (
        tablero_x + 140,
        15,
        tablero_x + 260,
        60
    )


    dibujar_boton(
        frame,
        "3 x 3",
        *boton_3,
        GRID == 3
    )

    dibujar_boton(
        frame,
        "5 x 5",
        *boton_5,
        GRID == 5
    )



    # Un clic sobre un botón cambia el tamaño del juego y vuelve a la captura de una nueva foto.
    if indice is not None and click:

        if punto_en_rectangulo(
            indice,
            boton_3
        ):

            GRID = 3

            jugando = False

            imagen_rompecabezas = None

            pieza_seleccionada = None

            mensaje = "Modo 3 x 3"
            contador_mensaje = 40


        elif punto_en_rectangulo(
            indice,
            boton_5
        ):

            GRID = 5

            jugando = False

            imagen_rompecabezas = None

            pieza_seleccionada = None

            mensaje = "Modo 5 x 5"
            contador_mensaje = 40



    # Antes de jugar muestra el marco del recorte y la instrucción para capturar con ESPACIO.
    if not jugando:

        cv2.rectangle(
            frame,
            (tablero_x, tablero_y),
            (tablero_x2, tablero_y2),
            (0, 255, 100),
            3
        )


        cv2.putText(
            frame,
            "ESPACIO = capturar",
            (tablero_x, tablero_y2 + 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )



    else:

        # Durante el juego crea un tablero BGR donde cada casilla recibe su recorte de la foto fija.
        tamaño_pieza = tamaño_tablero // GRID


        tablero = np.zeros(
            (
                tamaño_tablero,
                tamaño_tablero,
                3
            ),
            dtype=np.uint8
        )


        # La casilla bajo el dedo se calcula de nuevo cada fotograma; fuera del tablero queda en None.
        casilla_hover = None



        if indice is not None:

            ix, iy = indice


            if (
                tablero_x <= ix < tablero_x2
                and
                tablero_y <= iy < tablero_y2
            ):

                # Resta el origen del tablero para obtener coordenadas locales y las divide por el lado de la pieza.
                columna = (
                    ix - tablero_x
                ) // tamaño_pieza

                fila = (
                    iy - tablero_y
                ) // tamaño_pieza


                # Convierte fila y columna al índice lineal usado por piezas y pieza_seleccionada.
                casilla_hover = int(
                    fila * GRID + columna
                )



        # Reconstruye la imagen usando la permutación actual de piezas, sin alterar la fotografía original.
        for posicion in range(GRID * GRID):

            # La división entera obtiene la fila y el resto obtiene la columna de la casilla destino.
            fila_destino = posicion // GRID
            columna_destino = posicion % GRID


            x1 = columna_destino * tamaño_pieza
            y1 = fila_destino * tamaño_pieza

            x2 = x1 + tamaño_pieza
            y2 = y1 + tamaño_pieza


            # El ID indica qué recorte original debe copiarse en esta posición del tablero.
            pieza_id = piezas[posicion]


            # Calcula fila y columna en la fotografía original a partir del identificador de la pieza.
            fila_origen = pieza_id // GRID
            columna_origen = pieza_id % GRID


            ox1 = columna_origen * tamaño_pieza
            oy1 = fila_origen * tamaño_pieza

            ox2 = ox1 + tamaño_pieza
            oy2 = oy1 + tamaño_pieza


            pieza = imagen_rompecabezas[
                oy1:oy2,
                ox1:ox2
            ]


            tablero[
                y1:y2,
                x1:x2
            ] = pieza



        # Dibuja las divisiones de la cuadrícula y sus límites sobre las piezas ya compuestas.
        for i in range(GRID + 1):

            pos = i * tamaño_pieza

            cv2.line(
                tablero,
                (pos, 0),
                (pos, tamaño_tablero),
                (220, 220, 220),
                2
            )

            cv2.line(
                tablero,
                (0, pos),
                (tamaño_tablero, pos),
                (220, 220, 220),
                2
            )



        # Resalta en amarillo la primera casilla seleccionada, a la espera de la segunda pinza.
        if pieza_seleccionada is not None:

            fila = pieza_seleccionada // GRID
            columna = pieza_seleccionada % GRID


            x1 = columna * tamaño_pieza
            y1 = fila * tamaño_pieza

            x2 = x1 + tamaño_pieza
            y2 = y1 + tamaño_pieza


            cv2.rectangle(
                tablero,
                (x1 + 3, y1 + 3),
                (x2 - 3, y2 - 3),
                (0, 255, 255),
                5
            )



        # El borde verde señala dónde apunta el índice; apuntar por sí solo no intercambia piezas.
        if casilla_hover is not None:

            fila = casilla_hover // GRID
            columna = casilla_hover % GRID


            x1 = columna * tamaño_pieza
            y1 = fila * tamaño_pieza

            x2 = x1 + tamaño_pieza
            y2 = y1 + tamaño_pieza


            cv2.rectangle(
                tablero,
                (x1 + 5, y1 + 5),
                (x2 - 5, y2 - 5),
                (0, 255, 0),
                3
            )



        # La primera pinza selecciona; la segunda intercambia con otra casilla o cancela si es la misma.
        if (
            click
            and
            casilla_hover is not None
        ):

            if pieza_seleccionada is None:

                pieza_seleccionada = casilla_hover

                mensaje = "Pieza seleccionada"
                contador_mensaje = 20


            else:

                if casilla_hover != pieza_seleccionada:

                    # Actualiza la permutación; la nueva distribución se dibujará en el siguiente fotograma.
                    intercambiar_piezas(
                        piezas,
                        pieza_seleccionada,
                        casilla_hover
                    )

                    pieza_seleccionada = None

                    mensaje = "Piezas intercambiadas"
                    contador_mensaje = 20


                else:

                    pieza_seleccionada = None

                    mensaje = "Seleccion cancelada"
                    contador_mensaje = 20



        # Superpone el tablero en el vídeo en vivo, conservando el entorno visible fuera del recuadro.
        frame[
            tablero_y:tablero_y2,
            tablero_x:tablero_x2
        ] = tablero


        cv2.rectangle(
            frame,
            (tablero_x, tablero_y),
            (tablero_x2, tablero_y2),
            (255, 255, 255),
            2
        )



        # Comprueba el orden después de procesar la selección y muestra la indicación de victoria.
        # El juego sigue activo, por lo que se puede mezclar nuevamente o capturar otra imagen.
        if puzzle_completo(piezas):

            cv2.rectangle(
                frame,
                (tablero_x, tablero_y),
                (tablero_x2, tablero_y2),
                (0, 255, 0),
                6
            )


            texto = "ROMPECABEZAS COMPLETADO"


            tamaño_texto = cv2.getTextSize(
                texto,
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                3
            )[0]


            tx = (
                ancho - tamaño_texto[0]
            ) // 2


            ty = tablero_y + tamaño_tablero // 2


            cv2.rectangle(
                frame,
                (tx - 15, ty - 45),
                (
                    tx + tamaño_texto[0] + 15,
                    ty + 15
                ),
                (0, 0, 0),
                -1
            )


            cv2.putText(
                frame,
                texto,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                3
            )



    # Muestra la última acción durante el número de ciclos indicado y reduce su contador.
    if contador_mensaje > 0:

        cv2.putText(
            frame,
            mensaje,
            (20, alto - 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2
        )

        contador_mensaje -= 1



    cv2.putText(
        frame,
        "Pinza: seleccionar / intercambiar | R: mezclar | N: nueva foto | Q / ESC: salir",
        (20, alto - 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1
    )



    # Dibuja el cursor después del tablero para mantenerlo visible: amarillo al apuntar y verde al pinzar.
    if indice is not None:

        cv2.circle(
            frame,
            indice,
            13,
            (0, 0, 0),
            -1
        )

        cv2.circle(
            frame,
            indice,
            9,
            (0, 255, 255),
            -1
        )


        if pinza:

            cv2.circle(
                frame,
                indice,
                9,
                (0, 255, 0),
                -1
            )



    cv2.imshow(
        NOMBRE_VENTANA,
        frame
    )


    # Procesa eventos de la ventana y toma el byte bajo de la tecla pulsada para comparar los controles.
    tecla = cv2.waitKey(1) & 0xFF



    # Las teclas 3 y 5 cambian el modo y descartan la foto y selección del juego anterior.
    if tecla == ord("3"):

        GRID = 3

        jugando = False

        imagen_rompecabezas = None

        pieza_seleccionada = None



    elif tecla == ord("5"):

        GRID = 5

        jugando = False

        imagen_rompecabezas = None

        pieza_seleccionada = None



    # ESPACIO captura el encuadre actual; recalcula sus dimensiones con el GRID vigente.
    # Esto también permite crear un juego nuevo mientras hay otro en marcha.
    elif tecla == 32:

        tamaño_tablero, tablero_x, tablero_y, tablero_x2, tablero_y2 = calcular_tablero(
            ancho, alto, GRID
        )


        # Recorta desde la copia limpia para que botones, cursor y tablero no formen parte del rompecabezas.
        # copy() conserva la fotografía aunque lleguen nuevos fotogramas de la cámara.
        imagen_rompecabezas = frame_original[
            tablero_y:tablero_y2,
            tablero_x:tablero_x2
        ].copy()


        # Genera la lista de piezas y la mezcla antes de activar el modo de juego.
        piezas = crear_puzzle(GRID)

        piezas = mezclar_puzzle(piezas)


        pieza_seleccionada = None

        jugando = True

        mensaje = "Rompecabezas creado"
        contador_mensaje = 40



    # r vuelve a mezclar la misma fotografía; sólo tiene efecto cuando hay un juego activo.
    elif tecla == ord("r"):

        if jugando:

            piezas = crear_puzzle(GRID)

            piezas = mezclar_puzzle(piezas)

            pieza_seleccionada = None



    # n abandona la foto actual y vuelve al encuadre de captura.
    elif tecla == ord("n"):

        jugando = False

        imagen_rompecabezas = None

        pieza_seleccionada = None



    # ESC o Q permite salir de pantalla completa; acepta ambas variantes de la letra.
    elif tecla in (27, ord("q"), ord("Q")):

        break


    # Guarda el gesto de este ciclo como referencia para el siguiente comienzo de pinza.
    pinza_anterior = pinza



# Después de salir del bucle libera la cámara, cierra las ventanas y finaliza el detector.
# Este código de cierre se alcanza en las salidas normales del bucle.
cap.release()

cv2.destroyAllWindows()

hands.close()
