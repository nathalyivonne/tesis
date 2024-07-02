from flask import Flask, render_template, request
from PIL import Image
import base64
from funcion import recognize_invoices
from io import BytesIO
import subprocess
import csv
import pyodbc
from azure.identity import DefaultAzureCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
import googlemaps
import json

app = Flask(__name__)

# Parámetros de Azure
subscription_id = 'cbe95d56-10d1-4e9a-a0b7-b99aaabe8a67'
resource_group_name = 'datafactory-rg749'
data_factory_name = 'nathalypupuche-df'
pipeline_name = 'pipeline2'  # Reemplaza con el nombre de tu pipeline

# Crear credenciales y cliente de Azure Data Factory
credentials = DefaultAzureCredential()
adf_client = DataFactoryManagementClient(credentials, subscription_id)

# Configuración de la base de datos SQL Server
server = 'servidormanifiesto.database.windows.net'
database = 'bdmanifiestos'
username = 'serveradmin'
password = '!admin123'
driver = '{ODBC Driver 17 for SQL Server}'

conn_str = f'DRIVER={driver};SERVER={server};PORT=1433;DATABASE={database};UID={username};PWD={password}'

# Configuración del cliente de Google Maps
google_maps_api_key = 'AIzaSyAg-pHzpWI9Ik34rYvyPZYGU9s2aWWtFx4'  # Reemplazar con tu propia clave API
gmaps = googlemaps.Client(key=google_maps_api_key)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def upload():
    base64_data = request.form['base64Data']
    try:
        base64_data_cleaned = base64_data.split(',')[1]
        image_data = base64.b64decode(base64_data_cleaned)
        image = Image.open(BytesIO(image_data))
        invoice_data = recognize_invoices(image)

        # Guardar datos en archivo.csv
        with open("archivo.csv", mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerows(invoice_data)

        # Ejecutar script csv_to_database.py
        subprocess.run(['python', 'csv_to_database.py'], check=True)

        # Ejecutar el pipeline de Azure Data Factory
        response = adf_client.pipelines.create_run(resource_group_name, data_factory_name, pipeline_name)
        print(f'Pipeline run ID: {response.run_id}')

        # Esperar la finalización del pipeline (opcional)
        pipeline_run = adf_client.pipeline_runs.get(resource_group_name, data_factory_name, response.run_id)
        while pipeline_run.status in ['InProgress', 'Queued']:
            pipeline_run = adf_client.pipeline_runs.get(resource_group_name, data_factory_name, response.run_id)

        # Conectar a la base de datos SQL Server y obtener los datos de la tabla manifiesto2
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM manifiesto2")
        rows = cursor.fetchall()
        conn.close()
        
         # Preparar los datos para pasar a la plantilla
        data = [list(row) for row in rows]

        return render_template('tabla.html', data=data)
        
    except base64.binascii.Error:
        return "Error: Datos en base64 inválidos"
    except OSError:
        return "Error: No se pudo abrir la imagen"
    except subprocess.CalledProcessError:
        return "Error: Fallo en la ejecución del script csv_to_database.py"
    except pyodbc.Error as e:
        return f"Error de base de datos: {e}"
    except Exception as e:
        return f"Error: {e}"

@app.route('/ver_mapa')
def ver_mapa():
    try:
        # Conectar a la base de datos SQL Server y obtener los datos de la tabla manifiesto2
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT direccion, distrito FROM manifiesto2")
        rows = cursor.fetchall()
        conn.close()

        # Preparar las direcciones para geocodificar
        direcciones = [f"{row.direccion.strip()}, {row.distrito.strip()}" for row in rows]

        # Geocodificar todas las direcciones usando Google Maps API
        geocoded_addresses = []
        for direccion in direcciones:
            geocode_result = gmaps.geocode(direccion)
            if geocode_result:
                location = geocode_result[0]['geometry']['location']
                geocoded_addresses.append({
                    'address': direccion,
                    'latitude': location['lat'],
                    'longitude': location['lng']
                })
            else:
                print(f"No se pudo geocodificar la dirección: {direccion}")

        # Convertir a formato JSON
        json_data = json.dumps(geocoded_addresses, indent=4)
        
        # Renderizar la plantilla mapa.html con los datos geocodificados
        return render_template('mapa.html', direcciones_geocodificadas=json_data)
    except pyodbc.Error as e:
        return f"Error de base de datos: {e}"
    except Exception as e:
        return f"Error: {e}"

if __name__ == '__main__':
    app.run(debug=True)