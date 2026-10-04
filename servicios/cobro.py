from datetime import datetime
import math

from servicios.validaciones import validar_monto


def parse_fecha_db(valor):
    if isinstance(valor, datetime):
        return valor
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return datetime.strptime(texto, fmt)
            except ValueError:
                pass
    return None


def horas_cobradas_con_tolerancia(segundos, tolerancia_min=15):
    segundos = validar_monto(segundos or 0.0, permitir_cero=True, nombre="La duracion")
    try:
        tolerancia = float(tolerancia_min)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("La tolerancia debe estar entre 0 y 59 minutos.") from exc
    if not math.isfinite(tolerancia) or not 0 <= tolerancia < 60:
        raise ValueError("La tolerancia debe estar entre 0 y 59 minutos.")
    if segundos <= 0:
        return 0

    tolerancia_seg = tolerancia * 60
    horas_enteras = int(segundos // 3600)
    resto_seg = segundos - (horas_enteras * 3600)
    if horas_enteras == 0:
        return 0 if resto_seg <= tolerancia_seg else 1

    horas_cobradas = horas_enteras + (1 if resto_seg > tolerancia_seg else 0)
    return horas_cobradas


def calcular_total_estadia(dt_ingreso, dt_salida, tarifa_hora, tolerancia_min=15):
    if not isinstance(dt_ingreso, datetime) or not isinstance(dt_salida, datetime):
        raise ValueError("Las fechas de ingreso y salida no son validas.")
    try:
        segundos = (dt_salida - dt_ingreso).total_seconds()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Las fechas de ingreso y salida deben usar la misma zona horaria.") from exc
    if segundos < 0:
        raise ValueError("La salida no puede ser anterior al ingreso. Revisa la fecha y hora del equipo.")
    tarifa = validar_monto(tarifa_hora, permitir_cero=True, nombre="La tarifa")
    horas_cobradas = horas_cobradas_con_tolerancia(segundos, tolerancia_min=tolerancia_min)
    total = round(horas_cobradas * tarifa, 2)
    if not math.isfinite(total):
        raise ValueError("El importe calculado es demasiado grande.")
    return horas_cobradas, total
