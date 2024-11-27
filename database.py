from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import pyodbc
import googlemaps
from azure.mgmt.datafactory import DataFactoryManagementClient
from cachetools import LRUCache, cached  # Import necesario para el caché

# URL fija del Key Vault
key_vault_url = "https://clavetesis-keyvault.vault.azure.net/"

# Crear credenciales y cliente del Key Vault
credential = DefaultAzureCredential()
client = SecretClient(vault_url=key_vault_url, credential=credential)

# Configurar caché sin TTL
cache = LRUCache(maxsize=100)  # Caché limitado por tamaño, sin vencimiento de tiempo

@cached(cache)
def get_secret_cached(secret_name):
    """Función para recuperar secretos con almacenamiento temporal en caché."""
    return client.get_secret(secret_name).value

# Recuperar secretos desde el Key Vault y almacenarlos en caché
try:
    server = get_secret_cached("server")
    database = get_secret_cached("database")
    username = get_secret_cached("username")
    password = get_secret_cached("password")
    subscription = get_secret_cached("subscription")
    resourcegroupname = get_secret_cached("resourcegroupname")
    datafactoryname = get_secret_cached("datafactoryname")
    pipelinename = get_secret_cached("pipelinename")
    googlemapsapikey2 = get_secret_cached("googlemapsapikey2")
    endpoint = get_secret_cached("endpoint")
    modelid = get_secret_cached("modelid")
    keyocr = get_secret_cached("keyocr")
    secretkey = get_secret_cached("secretkey")
except Exception as e:
    raise ValueError(f"Error al recuperar los secretos del Key Vault: {e}")

# Validar que los secretos esenciales estén presentes
required_secrets = [server, database, username, password, subscription, resourcegroupname, 
                    datafactoryname, pipelinename, googlemapsapikey2, endpoint, modelid,
                    keyocr, secretkey]
if not all(required_secrets):
    raise ValueError("No se pudieron recuperar todas las credenciales requeridas.")

# Crear la cadena de conexión
driver = '{ODBC Driver 17 for SQL Server}'
connection_string = (
    f'Driver={driver};'
    f'Server=tcp:{server},1433;'
    f'Database={database};'
    f'Uid={username};'
    f'Pwd={password};'
    f'Encrypt=yes;'
    f'TrustServerCertificate=no;'
    f'Connection Timeout=30;'
)

# Conectar a la base de datos
try:
    conn = pyodbc.connect(connection_string)
    print("Conexión a la base de datos exitosa.")
except pyodbc.Error as e:
    raise ConnectionError(f"Error al conectar con la base de datos: {e}")

# Inicializar el cliente de Data Factory
adf_client = DataFactoryManagementClient(credential, subscription)

# Inicializar el cliente de Google Maps
try:
    gmaps = googlemaps.Client(key=googlemapsapikey2)
    print("Cliente de Google Maps inicializado correctamente.")
except Exception as e:
    raise ValueError(f"Error al inicializar el cliente de Google Maps: {e}")
