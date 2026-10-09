# Vision Portal: efectos visuales controlados por manos detectadas en la cámara.
# Flujo: captura -> detección de puntos -> gestos y geometría -> filtro local -> pantalla.
# Las imágenes de OpenCV usan canales BGR; MediaPipe recibe una copia convertida a RGB.

import cv2
import numpy as np
import mediapipe as mp
import time
import math
import os
import urllib.request
import random
from pathlib import Path


# Índice del dispositivo y configuración solicitada; la cámara puede negociar otros valores.
CAMARA = 1
ANCHO_CAMARA = 1920
ALTO_CAMARA = 1080
FPS_CAMARA = 30

# La detección procesa una copia pequeña para reducir trabajo; la salida conserva su resolución.
ANCHO_DETECCION = 1920
ALTO_DETECCION = 1080

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)

# Modelo y capturas se ubican junto a este script, independientemente de la carpeta de ejecución.
BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "hand_landmarker.task"


# Catálogo mostrado en pantalla. Sus índices también se usan en gestos, teclas y aplicar_filtro.
NOMBRES_FILTROS = [
    "NORMAL",
    "TERMICO",
    "VISION NOCTURNA",
    "NEON",
    "NEGATIVO",
    "X-RAY",
    "LAPIZ",
    "PIXELADO",
    "SEPIA",
    "PSICODELICO",
    "HOLOGRAMA",
    "GLITCH RGB",
    "PRISMA",
    "DUOTONE CYBER",
    "MATRIX",
    "EMBOSS 3D",
    "VHS",
    "SOLARIZE",
    "FROSTED GLASS",
    "RGB PULSE",
    "GHOST"
]

# Pares de índices que conectan los puntos de MediaPipe para dibujar cada dedo y la palma.
CONEXIONES_MANO = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17)
]



# Comprueba si está disponible el modelo local de MediaPipe y lo descarga si falta.
# Los errores se muestran y se propagan para detener el arranque sin un modelo utilizable.
def descargar_modelo():
    if MODEL_PATH.exists():
        return

    print("Descargando modelo de deteccion de manos...")

    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("Modelo descargado correctamente.")

    except Exception as error:
        print("No se pudo descargar el modelo.")
        print(error)
        print("\nDescargalo manualmente desde:")
        print(MODEL_URL)
        raise



# Convierte coordenadas normalizadas de MediaPipe a píxeles de la imagen de salida.
# Limita x e y a sus bordes y devuelve un vector float32 para los cálculos geométricos.
def punto_pixel(landmark, ancho, alto):
    x = int(landmark.x * ancho)
    y = int(landmark.y * alto)

    x = max(0, min(ancho - 1, x))
    y = max(0, min(alto - 1, y))

    return np.array([x, y], dtype=np.float32)


# Calcula la distancia euclídea entre dos puntos; se usa para comparar posiciones de dedos.
def distancia(p1, p2):
    return math.hypot(
        float(p1[0] - p2[0]),
        float(p1[1] - p2[1])
    )



# Dibuja el esqueleto de los 21 puntos de la mano sobre la imagen recibida.
# Resalta pulgar e índice, que definen las esquinas del portal; modifica la imagen en su lugar.
def dibujar_mano(imagen, landmarks, ancho, alto):
    puntos = [
        punto_pixel(landmark, ancho, alto).astype(int)
        for landmark in landmarks
    ]

    for inicio, fin in CONEXIONES_MANO:
        p1 = tuple(puntos[inicio])
        p2 = tuple(puntos[fin])

        cv2.line(
            imagen,
            p1,
            p2,
            (0, 255, 255),
            2,
            cv2.LINE_AA
        )

    for i, punto in enumerate(puntos):
        radio = 6 if i in (4, 8) else 3

        cv2.circle(
            imagen,
            tuple(punto),
            radio,
            (255, 255, 255),
            -1,
            cv2.LINE_AA
        )

        if i in (4, 8):
            cv2.circle(
                imagen,
                tuple(punto),
                radio + 3,
                (255, 0, 255),
                2,
                cv2.LINE_AA
            )



# Estima un puño comparando cuatro puntas de dedos con sus articulaciones respecto a la muñeca.
# Exige al menos tres dedos doblados; esta función auxiliar no se usa en el bucle actual.
def mano_cerrada(landmarks, ancho, alto):
    muneca = punto_pixel(
        landmarks[0],
        ancho,
        alto
    )

    pares = [
        (8, 6),
        (12, 10),
        (16, 14),
        (20, 18)
    ]

    dedos_doblados = 0

    for punta_id, articulacion_id in pares:
        punta = punto_pixel(
            landmarks[punta_id],
            ancho,
            alto
        )

        articulacion = punto_pixel(
            landmarks[articulacion_id],
            ancho,
            alto
        )

        if distancia(punta, muneca) < distancia(articulacion, muneca) * 1.08:
            dedos_doblados += 1

    return dedos_doblados >= 3


# Reconoce el gesto de cambio de filtro comparando las puntas del pulgar y del meñique.
# Normaliza la separación por el tamaño aparente de la palma para adaptar el umbral a la distancia.
def menique_toca_pulgar(
    landmarks,
    ancho,
    alto
):

    pulgar = punto_pixel(
        landmarks[4],
        ancho,
        alto
    )

    menique = punto_pixel(
        landmarks[20],
        ancho,
        alto
    )

    base_indice = punto_pixel(
        landmarks[5],
        ancho,
        alto
    )

    base_menique = punto_pixel(
        landmarks[17],
        ancho,
        alto
    )

    muneca = punto_pixel(
        landmarks[0],
        ancho,
        alto
    )

    base_medio = punto_pixel(
        landmarks[9],
        ancho,
        alto
    )

    distancia_toque = distancia(
        pulgar,
        menique
    )

    ancho_palma = distancia(
        base_indice,
        base_menique
    )

    largo_palma = distancia(
        muneca,
        base_medio
    )

    escala_mano = max(
        ancho_palma,
        largo_palma,
        1.0
    )

    # El toque se acepta si la separación es menor al 42 % de la escala de la palma.
    # Aumentar este valor facilita activarlo; reducirlo exige acercar más los dedos.
    UMBRAL_TOQUE_MENIQUE = 0.42

    return (
        distancia_toque
        <
        escala_mano
        *
        UMBRAL_TOQUE_MENIQUE
    )



# Devuelve una copia sin efecto para conservar intacta la imagen de entrada.
def filtro_normal(frame, tiempo):
    return frame.copy()


# Convierte el brillo a una paleta JET de falso color; el efecto no mide temperatura.
def filtro_termico(frame, tiempo):
    gris = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    return cv2.applyColorMap(
        gris,
        cv2.COLORMAP_JET
    )


# Realza el contraste del gris y lo concentra en el canal verde para simular visión nocturna.
def filtro_vision_nocturna(frame, tiempo):
    gris = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    gris = cv2.equalizeHist(gris)

    resultado = np.zeros_like(frame)

    resultado[:, :, 1] = gris
    resultado[:, :, 0] = gris // 10

    return cv2.convertScaleAbs(
        resultado,
        alpha=1.15,
        beta=8
    )


# Extrae bordes con Canny y combina su trazo con un desenfoque para producir brillo magenta.
def filtro_neon(frame, tiempo):
    gris = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    gris = cv2.GaussianBlur(
        gris,
        (5, 5),
        0
    )

    bordes = cv2.Canny(
        gris,
        55,
        135
    )

    glow = cv2.GaussianBlur(
        bordes,
        (0, 0),
        2.3
    )

    resultado = np.zeros_like(frame)

    fuerte = np.maximum(
        bordes,
        glow
    )

    resultado[:, :, 0] = fuerte
    resultado[:, :, 2] = fuerte
    resultado[:, :, 1] = glow // 5

    return resultado


# Invierte los valores de los canales: cada intensidad pasa de v a 255 - v.
def filtro_negativo(frame, tiempo):
    return cv2.bitwise_not(frame)


# Invierte el contraste en escala de grises y aplica tonos azulados para una apariencia radiográfica.
def filtro_xray(frame, tiempo):
    gris = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    gris = cv2.equalizeHist(gris)
    gris = cv2.bitwise_not(gris)

    resultado = np.zeros_like(frame)

    resultado[:, :, 0] = gris
    resultado[:, :, 1] = gris
    resultado[:, :, 2] = gris // 4

    return resultado


# Divide el gris por el inverso de una imagen desenfocada para simular trazos de lápiz.
def filtro_lapiz(frame, tiempo):
    gris = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    invertida = cv2.bitwise_not(gris)

    blur = cv2.GaussianBlur(
        invertida,
        (15, 15),
        0
    )

    dibujo = cv2.divide(
        gris,
        cv2.bitwise_not(blur),
        scale=256.0
    )

    return cv2.cvtColor(
        dibujo,
        cv2.COLOR_GRAY2BGR
    )


# Reduce la resolución y la amplía con vecino más cercano para obtener bloques de color visibles.
def filtro_pixelado(frame, tiempo):
    alto, ancho = frame.shape[:2]

    ancho_chico = max(
        1,
        ancho // 25
    )

    alto_chico = max(
        1,
        alto // 25
    )

    chico = cv2.resize(
        frame,
        (ancho_chico, alto_chico),
        interpolation=cv2.INTER_LINEAR
    )

    return cv2.resize(
        chico,
        (ancho, alto),
        interpolation=cv2.INTER_NEAREST
    )


# Mezcla los canales BGR mediante una matriz para obtener tonos cálidos.
# Limita el resultado al rango 0–255 y devuelve píxeles de ocho bits.
def filtro_sepia(frame, tiempo):
    matriz = np.array([
        [0.272, 0.534, 0.131],
        [0.349, 0.686, 0.168],
        [0.393, 0.769, 0.189]
    ], dtype=np.float32)

    resultado = cv2.transform(
        frame,
        matriz
    )

    return np.clip(
        resultado,
        0,
        255
    ).astype(np.uint8)


# Desplaza el tono HSV con el tiempo y aumenta la saturación para animar los colores.
# OpenCV representa el tono de esta imagen de ocho bits en el intervalo 0–179.
def filtro_psicodelico(frame, tiempo):
    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    desplazamiento = int(
        (tiempo * 45) % 180
    )

    h = hsv[:, :, 0].astype(
        np.int16
    )

    hsv[:, :, 0] = (
        (h + desplazamiento) % 180
    ).astype(np.uint8)

    s = hsv[:, :, 1].astype(
        np.int16
    )

    hsv[:, :, 1] = np.clip(
        s * 1.65,
        0,
        255
    ).astype(np.uint8)

    return cv2.cvtColor(
        hsv,
        cv2.COLOR_HSV2BGR
    )


# Genera una base cian y añade franjas y una línea móvil para simular un barrido holográfico.
def filtro_holograma(frame, tiempo):
    gris = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    gris = cv2.equalizeHist(gris)

    resultado = np.zeros_like(frame)

    resultado[:, :, 0] = gris

    resultado[:, :, 1] = np.clip(
        gris.astype(np.int16) * 1.15,
        0,
        255
    ).astype(np.uint8)

    resultado[:, :, 2] = gris // 5

    alto, ancho = frame.shape[:2]

    offset = int(
        (tiempo * 80) % 12
    )

    if alto > 0:
        resultado[offset::12, :, :] = np.maximum(
            resultado[offset::12, :, :],
            np.array(
                [180, 220, 60],
                dtype=np.uint8
            )
        )

        y = int(
            (tiempo * 150) % alto
        )

        cv2.line(
            resultado,
            (0, y),
            (ancho - 1, y),
            (255, 255, 255),
            2
        )

    return resultado


# Separa espacialmente los canales rojo y azul y desplaza bandas aleatorias del recorte.
# El tiempo anima la separación de canales; la aleatoriedad cambia las bandas entre fotogramas.
def filtro_glitch_rgb(frame, tiempo):
    alto, ancho = frame.shape[:2]

    b, g, r = cv2.split(frame)

    mov_r = int(
        7
        +
        abs(
            math.sin(tiempo * 8)
        ) * 16
    )

    mov_b = int(
        5
        +
        abs(
            math.cos(tiempo * 6)
        ) * 12
    )

    resultado = cv2.merge([
        np.roll(
            b,
            -mov_b,
            axis=1
        ),
        g,
        np.roll(
            r,
            mov_r,
            axis=1
        )
    ])

    if alto > 12:
        for _ in range(4):
            y = random.randint(
                0,
                alto - 2
            )

            max_grosor = max(
                2,
                min(12, alto - y)
            )

            grosor = random.randint(
                2,
                max_grosor
            )

            mov = random.randint(
                -30,
                30
            )

            resultado[
                y:y + grosor
            ] = np.roll(
                resultado[
                    y:y + grosor
                ],
                mov,
                axis=1
            )

    return resultado


# Refleja la mitad izquierda para producir simetría y anima ligeramente el tono.
# Si el ancho es impar, ajusta el resultado al tamaño original del recorte.
def filtro_prisma(frame, tiempo):
    alto, ancho = frame.shape[:2]

    mitad = max(
        1,
        ancho // 2
    )

    izquierda = frame[
        :,
        :mitad
    ]

    derecha = cv2.flip(
        izquierda,
        1
    )

    resultado = np.hstack([
        izquierda,
        derecha
    ])

    if resultado.shape[1] != ancho:
        resultado = cv2.resize(
            resultado,
            (ancho, alto),
            interpolation=cv2.INTER_LINEAR
        )

    hsv = cv2.cvtColor(
        resultado,
        cv2.COLOR_BGR2HSV
    )

    cambio = int(
        10 * math.sin(
            tiempo * 2
        )
    )

    hsv[:, :, 0] = (
        hsv[:, :, 0].astype(np.int16)
        +
        cambio
    ) % 180

    return cv2.cvtColor(
        hsv.astype(np.uint8),
        cv2.COLOR_HSV2BGR
    )


# Interpola entre dos colores BGR según la luminosidad: violeta en sombras y cian en luces.
def filtro_duotone_cyber(frame, tiempo):
    gris = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    ).astype(np.float32) / 255.0

    oscuro = np.array(
        [120, 0, 90],
        dtype=np.float32
    )

    claro = np.array(
        [255, 255, 20],
        dtype=np.float32
    )

    mezcla = gris[:, :, None]

    resultado = (
        oscuro * (1.0 - mezcla)
        +
        claro * mezcla
    )

    return np.clip(
        resultado,
        0,
        255
    ).astype(np.uint8)


# Conserva el brillo en verde, oscurece filas periódicas y dibuja trazos que descienden.
def filtro_matrix(frame, tiempo):
    gris = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    gris = cv2.equalizeHist(gris)

    resultado = np.zeros_like(frame)

    resultado[:, :, 1] = gris

    alto, ancho = frame.shape[:2]

    resultado[::5, :, 1] //= 2

    paso = max(
        18,
        ancho // 28
    )

    for x in range(
        0,
        ancho,
        paso
    ):
        y = int(
            (
                tiempo * 120
                +
                x * 1.7
            )
            %
            max(alto, 1)
        )

        largo = min(
            55,
            alto
        )

        cv2.line(
            resultado,
            (x, max(0, y - largo)),
            (x, y),
            (20, 255, 20),
            1
        )

    return resultado


# Aplica una convolución direccional para destacar cambios de intensidad con aspecto de relieve.
def filtro_emboss(frame, tiempo):
    kernel = np.array([
        [-2, -1, 0],
        [-1,  1, 1],
        [ 0,  1, 2]
    ], dtype=np.float32)

    relieve = cv2.filter2D(
        frame,
        -1,
        kernel
    )

    return cv2.convertScaleAbs(
        relieve,
        alpha=1.05,
        beta=90
    )


# Desplaza canales, oscurece líneas y añade una banda móvil y ruido para imitar una cinta VHS.
def filtro_vhs(frame, tiempo):
    alto, ancho = frame.shape[:2]

    b, g, r = cv2.split(frame)

    resultado = cv2.merge([
        np.roll(
            b,
            -4,
            axis=1
        ),
        g,
        np.roll(
            r,
            4,
            axis=1
        )
    ])

    resultado[::4, :, :] = (
        resultado[::4, :, :]
        *
        0.72
    ).astype(np.uint8)

    if alto > 0:
        y = int(
            (tiempo * 95) % alto
        )

        grosor = min(
            18,
            alto - y
        )

        if grosor > 0:
            resultado[
                y:y + grosor
            ] = np.roll(
                resultado[
                    y:y + grosor
                ],
                15,
                axis=1
            )

    ruido = np.random.randint(
        0,
        18,
        frame.shape,
        dtype=np.uint8
    )

    return cv2.add(
        resultado,
        ruido
    )


# Invierte únicamente los píxeles cuyo brillo supera un umbral que oscila con el tiempo.
def filtro_solarize(frame, tiempo):
    umbral = int(
        115
        +
        25
        *
        math.sin(
            tiempo * 1.7
        )
    )

    invertido = cv2.bitwise_not(
        frame
    )

    gris = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    mascara = (
        gris > umbral
    ).astype(np.uint8) * 255

    resultado = frame.copy()

    cv2.copyTo(
        invertido,
        mascara,
        resultado
    )

    return resultado


# Mezcla la imagen con un desenfoque gaussiano para simular la difusión del vidrio esmerilado.
def filtro_frosted_glass(frame, tiempo):
    blur = cv2.GaussianBlur(
        frame,
        (15, 15),
        0
    )

    return cv2.addWeighted(
        frame,
        0.25,
        blur,
        0.75,
        10
    )


# Modula la intensidad de cada canal con ondas de distinta fase para animar pulsos de color.
def filtro_rgb_pulse(frame, tiempo):
    b, g, r = cv2.split(frame)

    pulso_r = (
        0.75
        +
        0.45
        *
        (
            math.sin(
                tiempo * 3.0
            )
            +
            1
        )
        / 2
    )

    pulso_g = (
        0.75
        +
        0.45
        *
        (
            math.sin(
                tiempo * 3.0 + 2.1
            )
            +
            1
        )
        / 2
    )

    pulso_b = (
        0.75
        +
        0.45
        *
        (
            math.sin(
                tiempo * 3.0 + 4.2
            )
            +
            1
        )
        / 2
    )

    b = np.clip(
        b.astype(np.float32) * pulso_b,
        0,
        255
    ).astype(np.uint8)

    g = np.clip(
        g.astype(np.float32) * pulso_g,
        0,
        255
    ).astype(np.uint8)

    r = np.clip(
        r.astype(np.float32) * pulso_r,
        0,
        255
    ).astype(np.uint8)

    return cv2.merge([
        b,
        g,
        r
    ])


# Superpone una copia desplazada y desenfocada del mismo fotograma con un tono frío.
# El efecto es espacial; no utiliza imágenes de fotogramas anteriores.
def filtro_ghost(frame, tiempo):
    desplazamiento = int(
        12
        +
        abs(
            math.sin(
                tiempo * 2.5
            )
        )
        *
        18
    )

    fantasma = np.roll(
        frame,
        desplazamiento,
        axis=1
    )

    fantasma = cv2.GaussianBlur(
        fantasma,
        (7, 7),
        0
    )

    resultado = cv2.addWeighted(
        frame,
        0.62,
        fantasma,
        0.38,
        0
    )

    b, g, r = cv2.split(
        resultado
    )

    b = cv2.convertScaleAbs(
        b,
        alpha=1.18,
        beta=8
    )

    r = cv2.convertScaleAbs(
        r,
        alpha=0.82,
        beta=0
    )

    return cv2.merge([
        b,
        g,
        r
    ])


# Selecciona y ejecuta el efecto por su índice. El orden debe coincidir con NOMBRES_FILTROS.
# Todos los filtros reciben el recorte BGR y el tiempo transcurrido, aunque algunos no usan el tiempo.
def aplicar_filtro(
    frame,
    filtro,
    tiempo
):
    filtros = [
        filtro_normal,
        filtro_termico,
        filtro_vision_nocturna,
        filtro_neon,
        filtro_negativo,
        filtro_xray,
        filtro_lapiz,
        filtro_pixelado,
        filtro_sepia,
        filtro_psicodelico,
        filtro_holograma,
        filtro_glitch_rgb,
        filtro_prisma,
        filtro_duotone_cyber,
        filtro_matrix,
        filtro_emboss,
        filtro_vhs,
        filtro_solarize,
        filtro_frosted_glass,
        filtro_rgb_pulse,
        filtro_ghost
    ]

    return filtros[filtro](
        frame,
        tiempo
    )



# Devuelve las puntas del índice (punto 8) y del pulgar (punto 4), conservando su identidad.
# No las reordena por altura: al girar una mano, el portal puede adoptar la forma cruzada.
def obtener_puntos_portal_mano(
    landmarks,
    ancho,
    alto
):

    indice = punto_pixel(
        landmarks[8],
        ancho,
        alto
    )

    pulgar = punto_pixel(
        landmarks[4],
        ancho,
        alto
    )

    return indice, pulgar


# Comprueba si el orden vertical de índice y pulgar difiere entre las dos manos.
# quad conserva este orden: índice izquierdo, índice derecho, pulgar derecho y pulgar izquierdo.
# Ese cambio de signo es el criterio de cruce usado por el programa.
def portal_esta_cruzado(quad):

    izq_indice = quad[0]
    der_indice = quad[1]
    der_pulgar = quad[2]
    izq_pulgar = quad[3]

    diferencia_izq = (
        izq_indice[1]
        -
        izq_pulgar[1]
    )

    diferencia_der = (
        der_indice[1]
        -
        der_pulgar[1]
    )

    return (
        diferencia_izq
        *
        diferencia_der
        <
        0
    )


# Calcula el cruce de las rectas p1–p2 y p3–p4 mediante sus determinantes.
# Si son casi paralelas, devuelve el promedio de los cuatro puntos para evitar dividir por casi cero.
def interseccion_lineas(
    p1,
    p2,
    p3,
    p4
):

    x1, y1 = map(float, p1)
    x2, y2 = map(float, p2)
    x3, y3 = map(float, p3)
    x4, y4 = map(float, p4)

    denominador = (
        (x1 - x2)
        *
        (y3 - y4)
        -
        (y1 - y2)
        *
        (x3 - x4)
    )

    if abs(denominador) < 0.0001:
        return (
            np.array(
                p1,
                dtype=np.float32
            )
            +
            np.array(
                p2,
                dtype=np.float32
            )
            +
            np.array(
                p3,
                dtype=np.float32
            )
            +
            np.array(
                p4,
                dtype=np.float32
            )
        ) / 4.0

    determinante_12 = (
        x1 * y2
        -
        y1 * x2
    )

    determinante_34 = (
        x3 * y4
        -
        y3 * x4
    )

    px = (
        determinante_12
        *
        (x3 - x4)
        -
        (x1 - x2)
        *
        determinante_34
    ) / denominador

    py = (
        determinante_12
        *
        (y3 - y4)
        -
        (y1 - y2)
        *
        determinante_34
    ) / denominador

    return np.array(
        [px, py],
        dtype=np.float32
    )


# Calcula el área en píxeles cuadrados que se utilizará para aceptar o descartar el portal.
# En modo normal usa el cuadrilátero; en modo cruzado suma las áreas de sus dos triángulos.
def calcular_area_portal(quad):

    if not portal_esta_cruzado(quad):
        return abs(
            cv2.contourArea(
                quad.astype(np.int32)
            )
        )

    indice_izq = quad[0]
    indice_der = quad[1]
    pulgar_der = quad[2]
    pulgar_izq = quad[3]

    centro = interseccion_lineas(
        indice_izq,
        indice_der,
        pulgar_izq,
        pulgar_der
    )

    triangulo_izq = np.float32([
        indice_izq,
        pulgar_izq,
        centro
    ])

    triangulo_der = np.float32([
        indice_der,
        pulgar_der,
        centro
    ])

    return (
        abs(
            cv2.contourArea(
                triangulo_izq.astype(np.int32)
            )
        )
        +
        abs(
            cv2.contourArea(
                triangulo_der.astype(np.int32)
            )
        )
    )



# Filtra el rectángulo que contiene el portal y copia el efecto sólo dentro de su máscara.
# Devuelve una imagen nueva; las zonas exteriores conservan el fotograma original.
def crear_portal(
    frame,
    quad,
    filtro,
    tiempo
):
    alto_frame, ancho_frame = frame.shape[:2]

    puntos = quad.astype(
        np.float32
    )

    # La región de interés (ROI) abarca las cuatro esquinas y un pequeño margen.
    # Los límites se recortan a la imagen para evitar índices fuera del fotograma.
    x, y, w, h = cv2.boundingRect(
        puntos.astype(np.int32)
    )

    margen = 3

    x1 = max(0, x - margen)
    y1 = max(0, y - margen)

    x2 = min(
        ancho_frame,
        x + w + margen
    )

    y2 = min(
        alto_frame,
        y + h + margen
    )

    if (
        x2 <= x1
        or
        y2 <= y1
    ):
        return frame.copy()

    roi = frame[
        y1:y2,
        x1:x2
    ]

    if roi.size == 0:
        return frame.copy()

    filtrado = aplicar_filtro(
        roi,
        filtro,
        tiempo
    )

    offset = np.array(
        [x1, y1],
        dtype=np.float32
    )

    # Traslada las esquinas al sistema de coordenadas del recorte para construir su máscara.
    local = (
        puntos - offset
    )

    mascara = np.zeros(
        roi.shape[:2],
        dtype=np.uint8
    )

    if portal_esta_cruzado(
        puntos
    ):
        # Cuando el portal está cruzado, rellena dos triángulos que comparten el punto de intersección.
        indice_izq = local[0]
        indice_der = local[1]
        pulgar_der = local[2]
        pulgar_izq = local[3]

        centro = interseccion_lineas(
            indice_izq,
            indice_der,
            pulgar_izq,
            pulgar_der
        )

        tri_izq = np.array([
            indice_izq,
            pulgar_izq,
            centro
        ], dtype=np.int32)

        tri_der = np.array([
            indice_der,
            pulgar_der,
            centro
        ], dtype=np.int32)

        cv2.fillPoly(
            mascara,
            [
                tri_izq,
                tri_der
            ],
            255
        )

    else:
        cv2.fillPoly(
            mascara,
            [
                local.astype(
                    np.int32
                )
            ],
            255
        )

    resultado = frame.copy()

    # destino es una vista del resultado: copyTo modifica sólo los píxeles habilitados por la máscara.
    destino = resultado[
        y1:y2,
        x1:x2
    ]

    cv2.copyTo(
        filtrado,
        mascara,
        destino
    )

    return resultado



# Dibuja un halo magenta desenfocado, un contorno nítido y marcas en las cuatro esquinas.
# Modifica directamente la imagen que recibirá la ventana de OpenCV.
def dibujar_borde_portal(
    imagen,
    quad
):
    puntos = quad.astype(
        np.int32
    ).reshape(
        (-1, 1, 2)
    )

    glow = np.zeros_like(
        imagen
    )

    cv2.polylines(
        glow,
        [puntos],
        True,
        (255, 0, 255),
        16,
        cv2.LINE_AA
    )

    glow = cv2.GaussianBlur(
        glow,
        (0, 0),
        sigmaX=14,
        sigmaY=14
    )

    # Suma el halo a la imagen existente; [:] mantiene el mismo objeto recibido por la función.
    imagen[:] = cv2.addWeighted(
        imagen,
        1.0,
        glow,
        0.8,
        0
    )

    cv2.polylines(
        imagen,
        [puntos],
        True,
        (255, 255, 255),
        2,
        cv2.LINE_AA
    )

    cv2.polylines(
        imagen,
        [puntos],
        True,
        (255, 0, 255),
        1,
        cv2.LINE_AA
    )

    for punto in quad.astype(int):
        cv2.circle(
            imagen,
            tuple(punto),
            8,
            (255, 255, 255),
            -1,
            cv2.LINE_AA
        )

        cv2.circle(
            imagen,
            tuple(punto),
            14,
            (255, 0, 255),
            2,
            cv2.LINE_AA
        )



# Superpone el nombre del filtro, los FPS calculados y la cantidad de manos detectadas.
# Cuando faltan dos manos, muestra la indicación necesaria para formar el portal.
def dibujar_hud(
    imagen,
    fps,
    filtro,
    manos_detectadas
):
    alto, ancho = imagen.shape[:2]

    cv2.rectangle(
        imagen,
        (15, 15),
        (455, 165),
        (0, 0, 0),
        -1
    )

    cv2.rectangle(
        imagen,
        (15, 15),
        (455, 165),
        (255, 0, 255),
        2
    )

    cv2.putText(
        imagen,
        "VISION PORTAL",
        (30, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        imagen,
        f"FPS: {fps:.0f}",
        (30, 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 255),
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        imagen,
        f"MANOS: {manos_detectadas}/2",
        (30, 103),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 255),
        2,
        cv2.LINE_AA
    )

    cv2.putText(
        imagen,
        f"FILTRO: {NOMBRES_FILTROS[filtro]}",
        (30, 131),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (255, 255, 255),
        2,
        cv2.LINE_AA
    )

    if manos_detectadas < 2:
        texto = "MOSTRA LAS DOS MANOS"

        tamaño, _ = cv2.getTextSize(
            texto,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            2
        )

        x = (
            ancho - tamaño[0]
        ) // 2

        cv2.putText(
            imagen,
            texto,
            (x, alto - 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )



# Coordina el ciclo de captura, detección, gestos, composición del portal y controles.
# Inicializa el modelo y la cámara antes de procesar fotogramas de forma continua.
def main():
    cv2.setUseOptimized(True)

    descargar_modelo()

    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    # El modo VIDEO usa el tiempo de cada fotograma para realizar el seguimiento de hasta dos manos.
    # Los umbrales controlan la confianza mínima de detección, presencia y seguimiento.
    opciones = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(
            model_asset_path=str(
                MODEL_PATH
            )
        ),

        running_mode=vision.RunningMode.VIDEO,

        num_hands=2,

        min_hand_detection_confidence=0.55,

        min_hand_presence_confidence=0.55,

        min_tracking_confidence=0.50
    )

    detector = (
        vision.HandLandmarker.create_from_options(
            opciones
        )
    )

    # En Windows se selecciona Media Foundation (MSMF) como interfaz de captura.
    if os.name == "nt":
        camara = cv2.VideoCapture(
            CAMARA,
            cv2.CAP_MSMF
        )
    else:
        camara = cv2.VideoCapture(
            CAMARA
        )

    camara.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        ANCHO_CAMARA
    )

    camara.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        ALTO_CAMARA
    )

    camara.set(
        cv2.CAP_PROP_FPS,
        FPS_CAMARA
    )

    # Solicita MJPG como formato de captura; su aceptación depende del dispositivo y del backend.
    camara.set(
        cv2.CAP_PROP_FOURCC,
        cv2.VideoWriter_fourcc(*"MJPG")
    )

    if not camara.isOpened():
        print("No se pudo abrir la camara.")

        detector.close()

        return

    # Consulta los valores negociados con la cámara; pueden diferir de los pedidos.
    ancho_real = int(
        camara.get(cv2.CAP_PROP_FRAME_WIDTH)
    )

    alto_real = int(
        camara.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )

    fps_reportados = camara.get(
        cv2.CAP_PROP_FPS
    )

    print(
        f"Camara activa: {ancho_real}x{alto_real} "
        f"@ {fps_reportados:.1f} FPS (backend MSMF en Windows)"
    )

    filtro_actual = 0

    quad_suavizado = None

    # Cada posición nueva aporta el 30 % al suavizado y la anterior conserva el 70 %.
    # Un factor mayor sigue más rápido los dedos; uno menor reduce más la vibración.
    factor_suavizado = 0.30

    mostrar_esqueleto = True

    tiempo_inicio = (
        time.perf_counter()
    )

    tiempo_fps_anterior = (
        time.perf_counter()
    )

    fps = 0.0

    # Guarda el último tiempo enviado al detector para asegurar valores estrictamente crecientes.
    ultimo_timestamp = 0

    # Estos estados distinguen un toque nuevo de uno mantenido y evitan repetir el cambio.
    toque_izquierdo_anterior = False
    toque_derecho_anterior = False

    ultimo_cambio_gesto = 0.0

    # Intervalo mínimo entre cambios de filtro activados por gestos, expresado en segundos.
    cooldown_gesto = 0.45

    print("\n==============================================")
    print("              VISION PORTAL FINAL")
    print("==============================================")
    print("1 = NORMAL")
    print("2 = TERMICO")
    print("3 = VISION NOCTURNA")
    print("4 = NEON")
    print("5 = NEGATIVO")
    print("6 = X-RAY")
    print("7 = LAPIZ")
    print("8 = PIXELADO")
    print("9 = SEPIA")
    print("0 = PSICODELICO")
    print("H = HOLOGRAMA")
    print("G = GLITCH RGB")
    print("P = PRISMA")
    print("D = DUOTONE CYBER")
    print("M = MATRIX")
    print("E = EMBOSS 3D")
    print("V = VHS")
    print("Y = SOLARIZE")
    print("F = FROSTED GLASS")
    print("R = RGB PULSE")
    print("O = GHOST")
    print("----------------------------------------------")
    print("pulgar + menique derecha   = siguiente")
    print("pulgar + menique izquierda = anterior")
    print("L = mostrar / ocultar manos")
    print("S = guardar captura")
    print("Q o ESC = salir")
    print("==============================================\n")

    try:
        while True:
            lectura_correcta, frame = (
                camara.read()
            )

            if (
                not lectura_correcta
                or frame is None
            ):
                print(
                    "La camara no entrego imagen."
                )
                break

            # Refleja horizontalmente la imagen para que el movimiento se vea como en un espejo.
            frame = cv2.flip(
                frame,
                1
            )

            alto, ancho = (
                frame.shape[:2]
            )

            # Los puntos detectados son normalizados: pueden trasladarse de la copia pequeña
            # a la imagen completa mediante punto_pixel, sin multiplicadores adicionales.
            frame_deteccion = cv2.resize(
                frame,
                (
                    ANCHO_DETECCION,
                    ALTO_DETECCION
                ),
                interpolation=cv2.INTER_AREA
            )

            rgb = cv2.cvtColor(
                frame_deteccion,
                cv2.COLOR_BGR2RGB
            )

            imagen_mp = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb
            )

            timestamp = int(
                (
                    time.perf_counter()
                    -
                    tiempo_inicio
                )
                * 1000
            )

            # VIDEO requiere tiempos crecientes en milisegundos, incluso si dos lecturas resultan muy próximas.
            if timestamp <= ultimo_timestamp:
                timestamp = (
                    ultimo_timestamp + 1
                )

            ultimo_timestamp = timestamp

            resultado = (
                detector.detect_for_video(
                    imagen_mp,
                    timestamp
                )
            )

            manos = list(
                resultado.hand_landmarks
            )

            # Ordena por posición horizontal en pantalla, no por mano izquierda o derecha anatómica.
            manos.sort(
                key=lambda mano:
                sum(
                    landmark.x
                    for landmark in mano
                )
                /
                len(mano)
            )

            salida = frame.copy()

            # El tiempo transcurrido anima los filtros de manera independiente del índice del fotograma.
            tiempo_efecto = (
                time.perf_counter()
                -
                tiempo_inicio
            )


            ahora_gesto = (
                time.perf_counter()
            )

            toque_izquierdo_actual = False
            toque_derecho_actual = False

            # Con una mano, su lado de la pantalla determina si el toque avanza o retrocede.
            # Con dos, se evalúan la mano más a la izquierda y la más a la derecha.
            if len(manos) == 1:
                mano_unica = manos[0]

                promedio_x = (
                    sum(
                        landmark.x
                        for landmark in mano_unica
                    )
                    /
                    len(mano_unica)
                )

                toque_actual = menique_toca_pulgar(
                    mano_unica,
                    ancho,
                    alto
                )

                if promedio_x < 0.5:
                    toque_izquierdo_actual = (
                        toque_actual
                    )
                else:
                    toque_derecho_actual = (
                        toque_actual
                    )

            elif len(manos) >= 2:
                mano_izquierda_pantalla = (
                    manos[0]
                )

                mano_derecha_pantalla = (
                    manos[-1]
                )

                toque_izquierdo_actual = (
                    menique_toca_pulgar(
                        mano_izquierda_pantalla,
                        ancho,
                        alto
                    )
                )

                toque_derecho_actual = (
                    menique_toca_pulgar(
                        mano_derecha_pantalla,
                        ancho,
                        alto
                    )
                )

            # Retrocede sólo al comenzar un toque y una vez transcurrida la pausa entre gestos.
            # El módulo permite pasar del primer filtro al último.
            if (
                toque_izquierdo_actual
                and
                not toque_izquierdo_anterior
                and
                (
                    ahora_gesto
                    -
                    ultimo_cambio_gesto
                )
                >
                cooldown_gesto
            ):
                filtro_actual = (
                    filtro_actual - 1
                ) % len(
                    NOMBRES_FILTROS
                )

                ultimo_cambio_gesto = (
                    ahora_gesto
                )

                print(
                    "<-",
                    NOMBRES_FILTROS[
                        filtro_actual
                    ]
                )

            # El toque derecho avanza; si ambos comienzan juntos, la rama izquierda tiene prioridad.
            elif (
                toque_derecho_actual
                and
                not toque_derecho_anterior
                and
                (
                    ahora_gesto
                    -
                    ultimo_cambio_gesto
                )
                >
                cooldown_gesto
            ):
                filtro_actual = (
                    filtro_actual + 1
                ) % len(
                    NOMBRES_FILTROS
                )

                ultimo_cambio_gesto = (
                    ahora_gesto
                )

                print(
                    "->",
                    NOMBRES_FILTROS[
                        filtro_actual
                    ]
                )

            # Recuerda el estado de este fotograma para exigir un nuevo comienzo de toque en el siguiente.
            toque_izquierdo_anterior = (
                toque_izquierdo_actual
            )

            toque_derecho_anterior = (
                toque_derecho_actual
            )


            if len(manos) >= 2:
                mano_izquierda = (
                    manos[0]
                )

                mano_derecha = (
                    manos[1]
                )

                (
                    izq_indice,
                    izq_pulgar
                ) = obtener_puntos_portal_mano(
                    mano_izquierda,
                    ancho,
                    alto
                )

                (
                    der_indice,
                    der_pulgar
                ) = obtener_puntos_portal_mano(
                    mano_derecha,
                    ancho,
                    alto
                )

                # Fija las esquinas por dedo y lado de pantalla, manteniendo el mismo orden en toda la geometría.
                quad_actual = np.float32([
                    izq_indice,
                    der_indice,
                    der_pulgar,
                    izq_pulgar
                ])

                area = calcular_area_portal(
                    quad_actual
                )

                # Descarta áreas de hasta 1200 píxeles cuadrados para evitar dibujar portales demasiado pequeños.
                if area > 1200:
                    if (
                        quad_suavizado
                        is None
                    ):
                        quad_suavizado = (
                            quad_actual.copy()
                        )

                    else:
                        # Promedia posiciones de forma gradual para disminuir saltos en el contorno del portal.
                        quad_suavizado = (
                            (
                                1.0
                                -
                                factor_suavizado
                            )
                            *
                            quad_suavizado
                            +
                            factor_suavizado
                            *
                            quad_actual
                        )

                    salida = crear_portal(
                        frame,
                        quad_suavizado,
                        filtro_actual,
                        tiempo_efecto
                    )

                    dibujar_borde_portal(
                        salida,
                        quad_suavizado
                    )

            # Al perder alguna mano, reinicia el suavizado para no reutilizar una geometría antigua.
            else:
                quad_suavizado = None


            # El esqueleto se dibuja después del filtro, de modo que permanezca visible sobre el efecto.
            if mostrar_esqueleto:
                for mano in manos:
                    dibujar_mano(
                        salida,
                        mano,
                        ancho,
                        alto
                    )


            ahora_fps = (
                time.perf_counter()
            )

            delta = (
                ahora_fps
                -
                tiempo_fps_anterior
            )

            tiempo_fps_anterior = (
                ahora_fps
            )

            # Estima la frecuencia del ciclo completo y suaviza el indicador con 90 % anterior y 10 % nuevo.
            # Este valor refleja el procesamiento del programa, no sólo los FPS solicitados a la cámara.
            if delta > 0:
                fps_instantaneo = (
                    1.0 / delta
                )

                if fps == 0:
                    fps = fps_instantaneo

                else:
                    fps = (
                        fps * 0.90
                        +
                        fps_instantaneo * 0.10
                    )

            dibujar_hud(
                salida,
                fps,
                filtro_actual,
                len(manos)
            )

            cv2.imshow(
                "Vision Portal",
                salida
            )

            # waitKey procesa los eventos de la ventana y devuelve la tecla pulsada; 0xFF conserva el byte bajo.
            tecla = (
                cv2.waitKey(1)
                &
                0xFF
            )


            # ESC o Q termina el bucle; números y letras seleccionan filtros directamente.
            if tecla in (
                27,
                ord("q"),
                ord("Q")
            ):
                break

            elif tecla == ord("1"):
                filtro_actual = 0

            elif tecla == ord("2"):
                filtro_actual = 1

            elif tecla == ord("3"):
                filtro_actual = 2

            elif tecla == ord("4"):
                filtro_actual = 3

            elif tecla == ord("5"):
                filtro_actual = 4

            elif tecla == ord("6"):
                filtro_actual = 5

            elif tecla == ord("7"):
                filtro_actual = 6

            elif tecla == ord("8"):
                filtro_actual = 7

            elif tecla == ord("9"):
                filtro_actual = 8

            elif tecla == ord("0"):
                filtro_actual = 9

            elif tecla in (
                ord("h"),
                ord("H")
            ):
                filtro_actual = 10

            elif tecla in (
                ord("g"),
                ord("G")
            ):
                filtro_actual = 11

            elif tecla in (
                ord("p"),
                ord("P")
            ):
                filtro_actual = 12

            elif tecla in (
                ord("d"),
                ord("D")
            ):
                filtro_actual = 13

            elif tecla in (
                ord("m"),
                ord("M")
            ):
                filtro_actual = 14

            elif tecla in (
                ord("e"),
                ord("E")
            ):
                filtro_actual = 15

            elif tecla in (
                ord("v"),
                ord("V")
            ):
                filtro_actual = 16

            elif tecla in (
                ord("y"),
                ord("Y")
            ):
                filtro_actual = 17

            elif tecla in (
                ord("f"),
                ord("F")
            ):
                filtro_actual = 18

            elif tecla in (
                ord("r"),
                ord("R")
            ):
                filtro_actual = 19

            elif tecla in (
                ord("o"),
                ord("O")
            ):
                filtro_actual = 20

            # L alterna las marcas de las manos sin desactivar su detección ni los gestos.
            elif tecla in (
                ord("l"),
                ord("L")
            ):
                mostrar_esqueleto = (
                    not mostrar_esqueleto
                )

            # S guarda la imagen compuesta, incluidos portal, borde y HUD, como PNG con fecha y hora.
            elif tecla in (
                ord("s"),
                ord("S")
            ):
                nombre = time.strftime(
                    "captura_portal_"
                    "%Y%m%d_%H%M%S.png"
                )

                ruta = (
                    BASE_DIR / nombre
                )

                cv2.imwrite(
                    str(ruta),
                    salida
                )

                print(
                    "captura:",
                    ruta.name
                )

    # Al salir del bucle, incluso por una excepción, libera cámara, detector y ventanas.
    finally:
        camara.release()
        detector.close()
        cv2.destroyAllWindows()


# Ejecuta la aplicación sólo al abrir el script directamente, no al importarlo como módulo.
if __name__ == "__main__":
    main()
