import pyodbc
from datetime import datetime, timedelta

# Configurar la conexión a la base de datos
server = 'servidormanifiesto.database.windows.net'
database = 'bdmanifiestos'
username = 'serveradmin'
password = '!admin123'
driver = '{ODBC Driver 17 for SQL Server}'

# Establecer la cadena de conexión
conn_str = f'DRIVER={driver};SERVER={server};PORT=1433;DATABASE={database};UID={username};PWD={password}'
conn = pyodbc.connect(conn_str)

# Obtener la fecha y hora actual
now = datetime.now()
seconds = round(now.second / 5) * 5  # Redondear segundos a múltiplos de 5
rounded_time = now.replace(second=seconds, microsecond=0)

# Actualizar la columna fecha_subida en la tabla Manifiesto2
cursor = conn.cursor()
cursor.execute("""
    UPDATE bdmanifiestos.dbo.Manifiesto2
    SET fecha_hora_subida = ?
    WHERE fecha_hora_subida IS NULL
""", rounded_time)
conn.commit()

# Cerrar la conexión a la base de datos
conn.close()
