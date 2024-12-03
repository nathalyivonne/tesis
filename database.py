from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import pyodbc
import googlemaps
from azure.mgmt.datafactory import DataFactoryManagementClient
from cachetools import LRUCache, cached 

key_vault_url = "https://clavetesis-keyvault.vault.azure.net/"

credential = DefaultAzureCredential()
client = SecretClient(vault_url=key_vault_url, credential=credential)

cache = LRUCache(maxsize=100) 

@cached(cache)
def get_secret_cached(secret_name):
    """Función para recuperar secretos con almacenamiento temporal en caché."""
    return client.get_secret(secret_name).value

try:
    server = get_secret_cached("server")
    database = get_secret_cached("database")
    username = get_secret_cached("username")
    password = get_secret_cached("password")
    subscription = get_secret_cached("subscription")
    resourcegroupname = get_secret_cached("resourcegroupname")
    datafactoryname = get_secret_cached("datafactoryname")
    pipelinename = get_secret_cached("pipelinename")
    googlemapsapikey3 = get_secret_cached("googlemapsapikey3")
    endpoint = get_secret_cached("endpoint")
    modelid = get_secret_cached("modelid")
    keyocr = get_secret_cached("keyocr")
    secretkey = get_secret_cached("secretkey")
except Exception as e:
    raise ValueError(f"Error al recuperar los secretos del Key Vault: {e}")

required_secrets = [server, database, username, password, subscription, resourcegroupname, 
                    datafactoryname, pipelinename, googlemapsapikey3, endpoint, modelid,
                    keyocr, secretkey]
if not all(required_secrets):
    raise ValueError("No se pudieron recuperar todas las credenciales requeridas.")

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

try:
    conn = pyodbc.connect(connection_string)
    print("Conexión a la base de datos exitosa.")
except pyodbc.Error as e:
    raise ConnectionError(f"Error al conectar con la base de datos: {e}")

adf_client = DataFactoryManagementClient(credential, subscription)

try:
    gmaps = googlemaps.Client(key=googlemapsapikey3)
    print("Cliente de Google Maps inicializado correctamente.")
except Exception as e:
    raise ValueError(f"Error al inicializar el cliente de Google Maps: {e}")
