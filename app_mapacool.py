from flask import Flask, render_template, request, send_file
from PIL import Image
import base64
from funcion import recognize_invoices
from io import BytesIO
import subprocess
import csv
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from geneticalgorithm import geneticalgorithm as ga
import numpy as np
import folium

app = Flask(__name__)

geolocator = Nominatim(user_agent="invoice_route_planner")

def geocode_address(address):
    try:
        location = geolocator.geocode(address, timeout=10)  # Aumentar el tiempo de espera si es necesario
        return (location.latitude, location.longitude) if location else None
    except GeocoderTimedOut:
        return None

def calculate_distance_matrix(addresses):
    n = len(addresses)
    distance_matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dist = geodesic(addresses[i], addresses[j]).kilometers
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

        with open("archivo.csv", mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerows(invoice_data)

        subprocess.run(['python', 'csv_to_database.py'])

        return render_template('tabla.html', data=invoice_data)

    except base64.binascii.Error:
        return "Error: Datos en base64 inválidos"
    except OSError:
        return "Error: No se pudo abrir la imagen"

@app.route('/ver_mapa')
def ver_mapa():
    direcciones = {}
    try:
        with open("archivo.csv", mode='r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file, delimiter=';')
            for row in reader:
                if len(row) >= 5:
                    direccion = row[3].strip()
                    distrito = row[4].strip()
                    if distrito not in direcciones:
                        direcciones[distrito] = []
                    direcciones[distrito].append(direccion)
                else:
                    print(f"La fila '{row}' no tiene suficientes elementos.")

        # Agregar dirección de origen y destino
        origen_y_destino = "calle los sauces 568, chiclayo"
        all_addresses = [origen_y_destino] + [f"{direccion}, {distrito}" for distrito, direcciones_list in direcciones.items() for direccion in direcciones_list] + [origen_y_destino]

        # Geocodificar todas las direcciones
        geocoded_addresses = [geocode_address(address) for address in all_addresses]
        geocoded_addresses = [addr for addr in geocoded_addresses if addr is not None]

        if len(geocoded_addresses) < 2:
            return "No se pudo geocodificar suficientes direcciones."

        # Calcular matriz de distancias
        distance_matrix = calculate_distance_matrix(geocoded_addresses)

        # Aplicar algoritmo genético para encontrar la ruta óptima
        optimal_route_indices = genetic_algorithm_tsp(distance_matrix)
        optimal_route = [geocoded_addresses[int(i)] for i in optimal_route_indices]

        # Crear el mapa
        folium_map = folium.Map(location=geocoded_addresses[0], zoom_start=14)

        # Añadir marcadores al mapa
        for idx, point in enumerate(optimal_route):
            folium.Marker(location=point, popup=f'Punto {idx + 1}').add_to(folium_map)
        
        # Añadir líneas entre los puntos
        folium.PolyLine(locations=optimal_route, color='blue').add_to(folium_map)

        # Guardar el mapa en un archivo HTML
        folium_map.save('templates/map.html')

        return render_template('map.html')

    except Exception as e:
        return f"Error al leer el archivo CSV: {e}"

if __name__ == '__main__':
    app.run(debug=True)
