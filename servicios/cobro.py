from datetime import datetime


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
    segundos = max(float(segundos or 0.0), 0.0)
    if segundos <= 0:
        return 0

    tolerancia_seg = int(tolerancia_min) * 60
    horas_enteras = int(segundos // 3600)
    resto_seg = segundos - (horas_enteras * 3600)
    if horas_enteras == 0:
        return 0 if resto_seg <= tolerancia_seg else 1

    horas_cobradas = horas_enteras + (1 if resto_seg > tolerancia_seg else 0)
    return horas_cobradas


def calcular_total_estadia(dt_ingreso, dt_salida, tarifa_hora, tolerancia_min=15):
    segundos = max((dt_salida - dt_ingreso).total_seconds(), 0.0)
    horas_cobradas = horas_cobradas_con_tolerancia(segundos, tolerancia_min=tolerancia_min)
    total = round(horas_cobradas * float(tarifa_hora), 2)
    return horas_cobradas, total
