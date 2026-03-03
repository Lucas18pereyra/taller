from database import init_db
from servicios.estacionamiento import ingresar_vehiculo, salir_vehiculo

init_db()

print("Ingreso:", ingresar_vehiculo("BBB222"))
print("Salida:", salir_vehiculo("BBB222"))
