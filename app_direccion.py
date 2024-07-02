from flask import Flask, render_template, request, send_file
from PIL import Image
import base64
from funcion import recognize_invoices
from io import BytesIO
import subprocess
import csv
import pyodbc
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut  # Importar la excepción
from geneticalgorithm import geneticalgorithm as ga
from azure.identity import DefaultAzureCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
from azure.mgmt.datafactory.models import CreateRunResponse
import numpy as np
import folium

app = Flask(__name__)

# Parámetros de Azure
subscription_id = 'cbe95d56-10d1-4e9a-a0b7-b99aaabe8a67'
resource_group_name = 'datafactory-rg749'
data_factory_name = 'nathalypupuche-df'
pipeline_name = 'pipeline2'  # Reemplaza con el nombre de tu pipeline

# Crear credenciales y cliente
credentials = DefaultAzureCredential()
adf_client = DataFactoryManagementClient(credentials, subscription_id)

# Configuración de la base de datos
server = 'servidormanifiesto.database.windows.net'
database = 'bdmanifiestos'
username = 'serveradmin'
password = '!admin123'
driver = '{ODBC Driver 17 for SQL Server}'

conn_str = f'DRIVER={driver};SERVER={server};PORT=1433;DATABASE={database};UID={username};PWD={password}'

geolocator = Nominatim(user_agent="geoapiExercises")

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

        # Ejecutar el pipeline
        response = adf_client.pipelines.create_run(resource_group_name, data_factory_name, pipeline_name)
        print(f'Pipeline run ID: {response.run_id}')

        # Esperar la finalización del pipeline (opcional)
        pipeline_run = adf_client.pipeline_runs.get(resource_group_name, data_factory_name, response.run_id)
        while pipeline_run.status in ['InProgress', 'Queued']:
            pipeline_run = adf_client.pipeline_runs.get(resource_group_name, data_factory_name, response.run_id)

        # Conectar a la base de datos y obtener los datos de la tabla manifiesto2
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

def geocode_address(direccion):
    try:
        location = geolocator.geocode(direccion, timeout=10)  # Aumentar el tiempo de espera si es necesario
        return (location.latitude, location.longitude) if location else None
    except GeocoderTimedOut:
        return None

def calculate_distance_matrix(direcciones):
    n = len(direcciones)
    distance_matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dist = geodesic(direcciones[i], direcciones[j]).kilometers
            distance_matrix[i][j] = dist
            distance_matrix[j][i] = dist
    return distance_matrix

def genetic_algorithm_tsp(distance_matrix):
    def fitness_function(route):
        distance = 0
        for i in range(len(route) - 1):
            distance += distance_matrix[int(route[i])][int(route[i+1])]
        distance += distance_matrix[int(route[-1])][int(route[0])]  # Return to the start
        return distance

    varbound = np.array([[0, len(distance_matrix)-1]]*(len(distance_matrix)))
    algorithm_param = {'max_num_iteration': 1000,
                       'population_size': 100,
                       'mutation_probability': 0.1,
                       'elit_ratio': 0.01,
                       'crossover_probability': 0.5,
                       'parents_portion': 0.3,
                       'crossover_type': 'uniform',
                       'max_iteration_without_improv': None}

    model = ga(function=fitness_function, dimension=len(distance_matrix), variable_type='int', variable_boundaries=varbound, algorithm_parameters=algorithm_param)
    model.run()
    return model.output_dict['variable']

@app.route('/ver_mapa')
def ver_mapa():
    direcciones = {}
    try:
        # Conectar a la base de datos y obtener los datos de la tabla manifiesto2
        conn = pyodbc.connect(conn_str)

        cursor = conn.cursor()
        cursor.execute("SELECT direccion, distrito FROM manifiesto2")
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            direccion = row[0].strip()
            distrito = row[1].strip()
            if distrito not in direcciones:
                direcciones[distrito] = []
            direcciones[distrito].append(direccion)

        # Agregar dirección de origen y destino
        origen_y_destino = "calle los sauces 568, chiclayo"
        all_addresses = [origen_y_destino] + [f"{direccion}, {distrito}" for distrito, direcciones_list in direcciones.items() for direccion in direcciones_list] + [origen_y_destino]

        # Geocodificar todas las direcciones
        geocoded_addresses = [geocode_address(direccion) for direccion in all_addresses]
        geocoded_addresses = [addr for addr in geocoded_addresses if addr is not None]

        if len(geocoded_addresses) < 2:
            return "No se pudo geocodificar suficientes direcciones."

        # Crear el mapa
        folium_map = folium.Map(location=geocoded_addresses[0], zoom_start=14)

        # Añadir marcadores al mapa para todas las direcciones
        for idx, point in enumerate(geocoded_addresses):
            folium.Marker(location=point, popup=f'Punto {idx + 1}').add_to(folium_map)

        # Añadir líneas entre todos los puntos
        folium.PolyLine(locations=geocoded_addresses, color='red').add_to(folium_map)

        # Guardar el mapa en un archivo HTML
        folium_map.save('templates/mapa.html')

        return render_template('mapa.html')

    except pyodbc.Error as e:
        return f"Error de base de datos: {e}"
    except Exception as e:
        return f"Error: {e}"


if __name__ == '__main__':
    app.run(debug=True)