import pyodbc

# Definir la cadena de conexión
server = 'servidormanifiesto.database.windows.net'
database = 'bdmanifiestos'
username = 'serveradmin'
password = '!admin123'
connection_string = 'Driver={ODBC Driver 17 for SQL Server};Server=tcp:servidormanifiesto.database.windows.net,1433;Database=bdmanifiestos;Uid=serveradmin;Pwd=!admin123;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'

# Conectarse a la base de datos
conn = pyodbc.connect(connection_string)
