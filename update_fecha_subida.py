import pyodbc
from datetime import datetime, timedelta
import database as db 

conn = db.conn 

now = datetime.now()
seconds = round(now.second / 5) * 5  # Redondear segundos a múltiplos de 5

if seconds >= 60:
    seconds = 0
    now = now.replace(minute=now.minute + 1)
rounded_time = now.replace(second=seconds, microsecond=0)
print(rounded_time)

cursor = conn.cursor()
cursor.execute("""
    UPDATE bdmanifiestos.dbo.Manifiesto2
    SET fecha_hora_subida = ?
    WHERE fecha_hora_subida IS NULL
""", rounded_time)
conn.commit()

cursor.close()
