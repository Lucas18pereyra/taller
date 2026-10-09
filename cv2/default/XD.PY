import cv2

backends = [
    ("DSHOW", cv2.CAP_DSHOW),
    ("MSMF", cv2.CAP_MSMF)
]

for nombre_backend, backend in backends:

    print(f"\n===== {nombre_backend} =====")

    for i in range(10):

        camara = cv2.VideoCapture(
            i,
            backend
        )

        if not camara.isOpened():
            camara.release()
            continue

        ret, frame = camara.read()

        if ret and frame is not None:

            ancho = int(
                camara.get(
                    cv2.CAP_PROP_FRAME_WIDTH
                )
            )

            alto = int(
                camara.get(
                    cv2.CAP_PROP_FRAME_HEIGHT
                )
            )

            fps = camara.get(
                cv2.CAP_PROP_FPS
            )

            print(
                f"Camara {i}: "
                f"{ancho}x{alto} "
                f"@ {fps:.1f} FPS"
            )

            cv2.imshow(
                f"{nombre_backend} - CAMARA {i}",
                frame
            )

            print(
                "Mira la ventana. "
                "Presiona una tecla para continuar."
            )

            cv2.waitKey(0)

            cv2.destroyAllWindows()

        camara.release()

cv2.destroyAllWindows()