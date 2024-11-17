import csv
from database import conn 

# Abrir el archivo CSV y leer los datos
with open('archivo.csv', mode='r', encoding='utf-8') as file:
    reader = csv.reader(file, delimiter=';')

    # Iterar sobre las filas del archivo CSV e insertar los datos en la base de datos
    for row in reader:
        # Verificar si todos los campos de la fila están vacíos
        if not all(field == '' for field in row):
            # Verificar que la fila tenga el número esperado de valores
            if len(row) == 6:
                item, codigo, cliente, direccion, distrito, servicio = row

                # Ejecutar la consulta SQL para insertar los datos en la tabla
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO Manifiesto (codigo, cliente, direccion, distrito, servicio) VALUES (?, ?, ?, ?, ?)",
                                codigo, cliente, direccion, distrito, servicio)
                    conn.commit()
            else:
                print("La fila no tiene el número esperado de valores:", row)
        else:
            print("La fila tiene todos los campos en blanco, se omite la inserción:", row)

# Cerrar la conexión a la base de datos
conn.close()
