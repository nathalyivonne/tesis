from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import pyodbc
import googlemaps
from azure.mgmt.datafactory import DataFactoryManagementClient

key_vault_name = "claveTesis-KeyVault"
key_vault_url = "https://clavetesis-keyvault.vault.azure.net/"

credential = DefaultAzureCredential()
client = SecretClient(vault_url=key_vault_url, credential=credential)

server = client.get_secret("server").value
database = client.get_secret("database").value
username = client.get_secret("username").value
password = client.get_secret("password").value

subscription = client.get_secret("subscription").value
resourcegroupname = client.get_secret("resourcegroupname").value
datafactoryname = client.get_secret("datafactoryname").value
pipelinename = client.get_secret("pipelinename").value
googlemapsapikey = client.get_secret("googlemapsapikey").value


endpoint = client.get_secret("endpoint").value
modelid = client.get_secret("modelid").value
keyocr = client.get_secret("keyocr").value

secretkey = client.get_secret("secretkey").value

if not all([server, database, username, password, subscription, resourcegroupname, datafactoryname, pipelinename, googlemapsapikey, endpoint, modelid, keyocr, secretkey]):
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

conn = pyodbc.connect(connection_string)

credentials = DefaultAzureCredential()
adf_client = DataFactoryManagementClient(credentials, subscription)

gmaps = googlemaps.Client(key=googlemapsapikey)