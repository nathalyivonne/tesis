from flask import Flask, render_template, request, session, redirect, url_for, send_from_directory, jsonify
from PIL import Image
import base64
from funcion import recognize_invoices
from io import BytesIO
import subprocess
import csv
import pyodbc 
from datetime import datetime,timedelta
from azure.identity import DefaultAzureCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
import googlemaps
import json
import random
import secrets
import os
import database as db
import pandas as pd
##import matplotlib.pyplot as plt

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
def home():
    return render_template('login.html')

@app.route('/admin')
def admin():
    return render_template('index2.html')

@app.route('/acceso-login', methods=["POST"])
def login():
    if request.method == 'POST' and 'txtEmail' in request.form and 'txtContrasena' in request.form:
        _email = request.form['txtEmail']
        _contrasena = request.form['txtContrasena']

        try:
            # Conectar a la base de datos SQL Server
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            cursor.execute('SELECT usuarioid, rolid FROM usuario WHERE email = ? AND contrasena = ?', (_email, _contrasena))
            account = cursor.fetchone()
            conn.close()

            if account:
                # Autenticación exitosa
                usuarioid, rolid = account[0], account[1]
                
                if rolid in (3,1):
                    return render_template("index2.html")
                elif rolid == 2:
                    return render_template("admin2.html")
                else:
                    return render_template('login.html', mensaje="Rol no válido")
            else:
                return render_template('login.html', mensaje="Usuario o contraseña incorrecta")
        except pyodbc.Error as e:
            return f"Error de base de datos: {e}"
        except Exception as e:
            return f"Error inesperado: {e}"
    else:
        return render_template('login.html')

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

        subprocess.run(['python', 'csv_to_database.py'], check=True)

        response = adf_client.pipelines.create_run(resource_group_name, data_factory_name, pipeline_name)
        print(f'Pipeline run ID: {response.run_id}')

        # Esperar la finalización del pipeline
        pipeline_run = adf_client.pipeline_runs.get(resource_group_name, data_factory_name, response.run_id)
        while pipeline_run.status in ['InProgress', 'Queued']:
            pipeline_run = adf_client.pipeline_runs.get(resource_group_name, data_factory_name, response.run_id)

        # Ejecutar el script para actualizar la fecha y hora en la tabla manifiesto2
        subprocess.run(['python', 'update_fecha_subida.py'], check=True)
        
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        sql_update_estado = """
            UPDATE bdmanifiestos.dbo.Manifiesto2
            set estado = case
                WHEN fecha_hora_entrega IS NOT NULL AND fecha_hora_subida IS NOT NULL
                THEN 1
                ELSE 0 
            END;
        """
        cursor.execute(sql_update_estado)  
        conn.commit()          
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

def fitness(solution):
    # Sumar las longitudes de las direcciones como medida de distancia total
    total_distance = sum(len(direccion) for direccion in solution)
    return total_distance

# Función para inicializar la población
def initialize_population(pop_size, direcciones):
    """
    Inicializa una población de soluciones para el algoritmo genético.
    
    Args:
        pop_size (int): Tamaño de la población.
        direcciones (list): Lista de direcciones a optimizar.
        
    Returns:
        list: Población inicial de soluciones.
    """
    initial_population = []
    num_genes = len(direcciones)
    
    for _ in range(pop_size):
        # Generar una solución aleatoria de direcciones
        solution = random.sample(direcciones, num_genes)
        initial_population.append(solution)
    
    return initial_population

# Función de selección de padres (torneo binario)
def select_parents(population, fitness_values, num_parents):
    selected_parents = []
    for _ in range(num_parents):
        idx1 = random.randint(0, len(population) - 1)
        idx2 = random.randint(0, len(population) - 1)
        parent = population[idx1] if fitness_values[idx1] < fitness_values[idx2] else population[idx2]
        selected_parents.append(parent)
    return selected_parents

# Función de crossover (un punto), creacion de los hijos
def crossover(parent1, parent2):
    point = random.randint(0, len(parent1) - 1)
    child1 = parent1[:point] + parent2[point:]
    child2 = parent2[:point] + parent1[point:]
    
    return child1, child2

# Función de mutación (bit flip) mejorada para direcciones
def mutate(solution, mutation_rate):
    mutated_solution = solution[:]
    for i in range(len(mutated_solution)):
        if random.random() < mutation_rate:
            # Obtener la dirección original
            original_address = solution[i]
            
            # Dividir la dirección en partes (por ejemplo, calle, número, etc.)
            address_parts = original_address.split(',')
            
            # Modificar una parte aleatoria de la dirección
            if len(address_parts) > 1:
                # Escoger aleatoriamente una parte para modificar
                index_to_mutate = random.randint(0, len(address_parts) - 1)
                
                # Modificar esa parte de la dirección original
                mutated_part = address_parts[index_to_mutate].strip()
                address_parts[index_to_mutate] = mutated_part
            
            # Reconstruir la dirección mutada
            mutated_address = ','.join(address_parts)
            
            # Actualizar la solución mutada
            mutated_solution[i] = mutated_address
    
    return mutated_solution

# Función principal del algoritmo genético
def genetic_algorithm(pop_size, direcciones, max_generations):
    population = initialize_population(pop_size, direcciones)
    for generation in range(max_generations):
        fitness_values = [fitness(solution) for solution in population]
        parents = select_parents(population, fitness_values, num_parents=2)
        offspring = []
        for i in range(0, pop_size, 2):
            child1, child2 = crossover(parents[0], parents[1])  
            offspring.append(mutate(child1, mutation_rate=0.1))
            offspring.append(mutate(child2, mutation_rate=0.1))
        population = offspring
    best_solution = min(population, key=fitness)
    return best_solution

@app.route('/ver_mapa')
def ver_mapa():
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT direccion, distrito, servicio FROM manifiesto2")
        rows = cursor.fetchall()
        conn.close()
        
        direcciones = [f"{row.direccion.strip()}, {row.distrito.strip()}" for row in rows]
        servicios = [row.servicio.strip() for row in rows]
        servicios_unicos = sorted(set(servicios))  # Obtener servicios únicos y ordenarlos
        
        # Ejecutar el algoritmo genético para optimizar las direcciones
        pop_size = 10  # Tamaño de la población inicial
        max_generations = 50  # Número máximo de generaciones
        best_solution = genetic_algorithm(pop_size, direcciones, max_generations)  # Pasar direcciones como lista
        
        # Geocodificar todas las direcciones usando Google Maps API
        geocoded_addresses = []
        for i, direccion in enumerate(best_solution):
            try:
                geocode_result = gmaps.geocode(direccion)
                if geocode_result:
                    location = geocode_result[0]['geometry']['location']
                    latitud = location['lat']
                    longitud = location['lng']
                    
                    etiqueta = f'DIRECCION {i + 1}'

                    geocoded_addresses.append({
                        'label': etiqueta,
                        'address': direccion,
                        'latitude': latitud,
                        'longitude': longitud,
                        'servicio': servicios[i]  # Usar el servicio correspondiente al índice
                    })
                else:
                    print(f"No se encontraron resultados para la dirección: {direccion}")
            except googlemaps.exceptions.ApiError as ex:
                print(f"Error de API al geocodificar {direccion}: {ex}")
        
        # Filtrar duplicados por coordenadas después de geocodificar
        unique_geocoded_addresses = []
        seen_addresses = set()
        for address in geocoded_addresses:
            coordinates = (address['latitude'], address['longitude'])
            if coordinates not in seen_addresses:
                unique_geocoded_addresses.append(address)
                seen_addresses.add(coordinates)
            else:
                print(f"Dirección duplicada encontrada: {address['address']} (Lat: {address['latitude']}, Lng: {address['longitude']})")
        
        # Geocodificar y agregar la dirección de inicio
        start_address = "CALLE LOS SAUCES 568 URBANIZACION SANTA VICTORIA, CHICLAYO"
        geocode_result = gmaps.geocode(start_address)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            unique_geocoded_addresses.append({
                'label': 'DIRECCION 1', 
                'address': start_address,
                'latitude': location['lat'],
                'longitude': location['lng'],
                'servicio': 'Punto de inicio'
            })
        else:
            print(f"No se encontraron resultados para la dirección de inicio: {start_address}")
        
        json_data = json.dumps(unique_geocoded_addresses, indent=4)
        return render_template('mapa.html', direcciones_geocodificadas=json_data, servicios_unicos= servicios_unicos)   
    except pyodbc.Error as e:
        return f"Error de base de datos: {e}"
    except Exception as e:
        return f"Error inesperado: {e}"


def format_date_time(date_time_str):
    """
    This function ensures the date is formatted as 'YYYY-MM-DD HH:MM:SS' before being passed to SQL Server.
    If the format is incorrect, it uses the current time as a fallback.
    """
    try:
        # Check if the date string is already in the correct format
        return datetime.strptime(date_time_str, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        # Handle cases where the format is different, for example if you get 'Tue, 08 Oct 2024 16:20:05 GMT'
        try:
            return datetime.strptime(date_time_str, '%a, %d %b %Y %H:%M:%S %Z').strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            # If the string cannot be parsed, use the current date and time as fallback
            print(f"Invalid date format received: {date_time_str}. Using current time.")
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

@app.route('/actualizar_hora_entrega', methods=['POST'])
def actualizar_hora_entrega():
    data = request.json
    print("Datos recibidos:", data)  # Para verificar que llegan los datos correctos
    try:
        # Habilitar autocommit
        conn = pyodbc.connect(conn_str, autocommit=False)
        cursor = conn.cursor()

        # Actualización de cada ítem
        for item in data['items']:
            print(f"Actualizando item: {item['item']}")
            
            # Verificación de datos antes de actualizar
            if not all(k in item for k in ['fecha_hora_entrega', 'servicio', 'direccion', 'item']):
                raise ValueError(f"Faltan datos en el ítem: {item}")
            
            formatted_date = format_date_time(item['fecha_hora_entrega'])
            print(f"Formatted date: {formatted_date}")
            
            sql_update = """
                UPDATE manifiesto2
                SET fecha_hora_entrega = ?, servicio = ?, direccion = ?
                WHERE item = ?
            """
            cursor.execute(sql_update, (formatted_date, item['servicio'], item['direccion'], item['item']))
            
            # Update the 'estado' field for the specific item
            sql_update_estado = """
            UPDATE bdmanifiestos.dbo.Manifiesto2
            SET estado = CASE
                WHEN fecha_hora_entrega IS NOT NULL AND fecha_hora_subida IS NOT NULL
                THEN 1
                ELSE 0 
            END
            WHERE item = ?
            """
            cursor.execute(sql_update_estado, (item['item'],))  # Provide item ID as the argument

            #sql_update_estado = """
            #UPDATE bdmanifiestos.dbo.Manifiesto2
            #set estado = case
            #    WHEN fecha_hora_entrega IS NOT NULL AND fecha_hora_subida IS NOT NULL
            #    THEN 1
            #    ELSE 0 
            #    END;
            #"""
            #cursor.execute(sql_update_estado)
            
        print("Comenzando commit...")
        conn.commit()
        print("Commit realizado con éxito.")

        # Query para calcular el cumplimiento
        item_ids = [item['item'] for item in data['items']]
        if not item_ids:
            return jsonify({"status": "error", "message": "No hay ítems para actualizar."}), 400

        placeholders = ', '.join(['?'] * len(item_ids))
        print(placeholders)
        # Query para calcular el cumplimiento
        sql_select = f"""
            SELECT 
                item,  -- Asegúrate de obtener el ID del ítem para la actualización
                fecha_hora_subida,
                fecha_hora_entrega,
                CASE 
                    WHEN fecha_hora_entrega IS NULL THEN 'NULL'
                    ELSE CAST(DATEDIFF(MINUTE, fecha_hora_subida, fecha_hora_entrega) AS VARCHAR)
                END AS cumplimiento
            FROM 
                manifiesto2
            WHERE item IN ({placeholders})
        """
        cursor.execute(sql_select, item_ids)
        cumplimiento_data = cursor.fetchall()

        cumplimiento_result = []
        for row in cumplimiento_data:
            item_id = row[0]
            cumplimiento = row[3]

            cumplimiento_result.append({
                "item": item_id,
                "fecha_hora_subida": row[1],
                "fecha_hora_entrega": row[2],
                "cumplimiento": cumplimiento
            })

            # Actualizar el cumplimiento en la base de datos
            sql_update_cumplimiento = """
                UPDATE manifiesto2
                SET cumplimiento = ?
                WHERE item = ?
            """
            cursor.execute(sql_update_cumplimiento, (cumplimiento, item_id))

        print("Datos de cumplimiento obtenidos y actualizados:", cumplimiento_result)
        conn.commit()  # Asegúrate de hacer commit de la actualización de cumplimiento

        return jsonify({"status": "success", "cumplimiento": cumplimiento_result}), 200

    except Exception as e:
        print("Error durante la actualización:", e)
        conn.rollback()  # Rollback en caso de error
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
        
@app.route('/eliminar_entrega', methods=['POST'])
def eliminar_entrega():
    data = request.json
    print("Datos recibidos:", data)  # Verificar los datos que llegan desde el frontend
    
    try:
        # Conectar a la base de datos
        conn = pyodbc.connect(conn_str, autocommit=False)
        cursor = conn.cursor()

        # Verificación de que lleguen ítems para eliminar
        if 'items' not in data or not data['items']:
            raise ValueError("No se han proporcionado ítems para eliminar")

        # Iterar sobre cada ítem
        for item in data['items']:
            item_id = int(item['item'])  # Asegúrate de convertir a entero
            print(f"Procesando item: {item_id}")
            
            if item.get('eliminar'):  # Solo si se especifica que se debe eliminar
                # Preparar la consulta de eliminación
                sql_delete = """
                    UPDATE manifiesto2
                    SET fecha_hora_entrega = NULL, cumplimiento = NULL, estado = 0
                    WHERE item = ?
                """
                print(f"Ejecutando SQL: {sql_delete} para item {item_id}")
                
                # Ejecutar la consulta SQL para eliminar la fecha y el cumplimiento
                result = cursor.execute(sql_delete, (item['item'],))
                if result.rowcount == 0:
                    print(f"No se encontró el ítem {item_id} para actualizar.")
                else:
                    print(f"Fecha y cumplimiento eliminados para el ítem {item_id}. Filas afectadas: {result.rowcount}")
        
        # Hacer commit de los cambios
        print("Realizando commit de los cambios...")
        conn.commit()
        print("Cambios guardados exitosamente en la base de datos.")

        return jsonify({"status": "success", "message": "Datos eliminados correctamente"}), 200

    except Exception as e:
        # En caso de error, realizar rollback para revertir los cambios
        print(f"Error durante la eliminación: {e}")
        conn.rollback()  # Rollback en caso de error
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        # Cerrar la conexión a la base de datos
        cursor.close()
        conn.close()

################################ MANTENIMIENTOS ###############################
#################################### CARGO ####################################
@app.route('/cargo')
def cargo():
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM cargo")
    myresult = cursor.fetchall()
    # Convertir los datos a diccionario
    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()
    return render_template('cargo.html', data=insertObject)

@app.route('/agregar_cargo', methods=['POST'])
def agregar_cargo():
    titulo = request.form['titulo']
    descripcion = request.form['descripcion']
    estado = 1 if 'estado' in request.form else 0 
    if titulo and descripcion:
        cursor = db.conn.cursor()
        sql = "INSERT INTO cargo (titulo, descripcion, estado) VALUES (?, ?, ?)"
        data = (titulo, descripcion, estado)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('cargo'))

@app.route('/eliminar_cargo/<string:cargoid>', methods=['GET'])
def eliminar_cargo(cargoid):
    cursor = db.conn.cursor()
    sql = "DELETE FROM cargo WHERE cargoid=?"
    data = (cargoid,)
    cursor.execute(sql, data)
    db.conn.commit()
    return redirect(url_for('cargo')) 

@app.route('/editar_cargo/<string:cargoid>', methods=['POST'])
def editar_cargo(cargoid):
    titulo = request.form['titulo']
    descripcion = request.form['descripcion']
    estado = 'estado' in request.form
    if titulo and descripcion:
        cursor = db.conn.cursor()
        sql = "UPDATE cargo SET titulo = ?, descripcion = ?, estado = ? WHERE cargoid = ?"
        data = (titulo, descripcion, estado, cargoid)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('cargo'))
#################################### ROLES ####################################
@app.route('/roles')
def roles():
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM roles")
    myresult = cursor.fetchall()
    # Convertir los datos a diccionario
    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()
    return render_template('roles.html', data=insertObject)

@app.route('/agregar_roles', methods=['POST'])
def agregar_roles():
    descripcion = request.form['descripcion']
    estado = 1 if 'estado' in request.form else 0  # Esto asignará 1 si el checkbox está marcado, y 0 si no está marcado
    if descripcion:
        cursor = db.conn.cursor()
        sql = "INSERT INTO roles (descripcion, estado) VALUES (?, ?)"
        data = (descripcion, estado)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('roles'))

@app.route('/eliminar_roles/<string:rolid>', methods=['GET'])
def eliminar_roles(rolid):
    cursor = db.conn.cursor()
    sql = "DELETE FROM roles WHERE rolid=?"
    data = (rolid,)
    cursor.execute(sql, data)
    db.conn.commit()
    return redirect(url_for('roles')) 

@app.route('/editar_roles/<string:rolid>', methods=['POST'])
def editar_roles(rolid):
    descripcion = request.form['descripcion']
    estado = 'estado' in request.form
    if descripcion:
        cursor = db.conn.cursor()
        sql = "UPDATE roles SET descripcion = ?, estado = ? WHERE rolid = ?"
        data = (descripcion, estado, rolid)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('roles'))
################################ TIPO DOCUMENTO ###############################
@app.route('/tipoDocumento')
def tipoDocumento():
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM TipoDocumento")
    myresult = cursor.fetchall()
    # Convertir los datos a diccionario
    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()
    return render_template('tipoDocumento.html', data=insertObject)

@app.route('/agregar_tipodocumento', methods=['POST'])
def agregar_tipodocumento():
    Acronimo = request.form['Acronimo']
    Descripcion = request.form['Descripcion']
    estado = 1 if 'estado' in request.form else 0  # Esto asignará 1 si el checkbox está marcado, y 0 si no está marcado
    if Acronimo and Descripcion:
        cursor = db.conn.cursor()
        sql = "INSERT INTO TipoDocumento (Acronimo, Descripcion, estado) VALUES (?, ?, ?)"
        data = (Acronimo, Descripcion, estado)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('tipoDocumento'))

@app.route('/eliminar_tipodocumento/<string:TipodocumentoID>', methods=['GET'])
def eliminar_tipodocumento(TipodocumentoID):
    cursor = db.conn.cursor()
    sql = "DELETE FROM TipoDocumento WHERE TipodocumentoID=?"
    data = (TipodocumentoID,)
    cursor.execute(sql, data)
    db.conn.commit()
    return redirect(url_for('tipoDocumento')) 

@app.route('/editar_tipodocumento/<string:TipodocumentoID>', methods=['POST'])
def editar_tipodocumento(TipodocumentoID):
    Acronimo = request.form['Acronimo']
    Descripcion = request.form['Descripcion']
    estado = 'estado' in request.form
    if Acronimo and Descripcion:
        cursor = db.conn.cursor()
        sql = "UPDATE TipoDocumento SET Acronimo = ?, Descripcion = ?, estado = ? WHERE TipodocumentoID = ?"
        data = (Acronimo, Descripcion, estado, TipodocumentoID)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('tipoDocumento'))
################################ USUARIO ###############################
@app.route('/usuario')
def usuario():
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM usuario")
    myresult = cursor.fetchall()
    # Convertir los datos a diccionario
    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()
    return render_template('usuario.html', data=insertObject)

@app.route('/agregar_usuario', methods=['POST'])
def agregar_usuario():
    email = request.form ['email']
    contrasena = request.form['contrasena']
    nombreusuario = request.form['nombreusuario']    
    tipodocumento = request.form['tipodocumento']
    documento = request.form['documento']
    nombres = request.form['nombres']
    apellidos = request.form['apellidos']
    telefono = request.form['telefono']
    direccion = request.form['direccion']
    estado = 1 if 'estado' in request.form else 0  # Esto asignará 1 si el checkbox está marcado, y 0 si no está marcado
    cargoid = request.form['cargoid']
    rolid = request.form['rolid']
    if email and nombreusuario and contrasena and tipodocumento and documento and nombres and apellidos and telefono and direccion and cargoid and rolid:
        cursor = db.conn.cursor()
        sql = "INSERT INTO usuario (email, nombreusuario, contrasena, tipodocumento, documento, nombres, apellidos, telefono, direccion, estado, cargoid, rolid) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        data = (email, nombreusuario, contrasena, tipodocumento, documento, nombres, apellidos, telefono, direccion, estado, cargoid, rolid)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('usuario'))

@app.route('/eliminar_usuario/<string:usuarioid>', methods=['GET'])
def eliminar_usuario(usuarioid):
    cursor = db.conn.cursor()
    sql = "DELETE FROM usuario WHERE usuarioid=?"
    data = (usuarioid,)
    cursor.execute(sql, data)
    db.conn.commit()
    return redirect(url_for('usuario')) 

@app.route('/editar_usuario/<string:usuarioid>', methods=['POST'])
def editar_usuario(usuarioid):
    email = request.form ['email']
    contrasena = request.form['contrasena']
    nombreusuario = request.form['nombreusuario']    
    tipodocumento = request.form['tipodocumento']
    documento = request.form['documento']
    nombres = request.form['nombres']
    apellidos = request.form['apellidos']
    telefono = request.form['telefono']
    direccion = request.form['direccion']
    estado = 'estado' in request.form
    cargoid = request.form['cargoid']
    rolid = request.form['rolid']
    if email and nombreusuario and contrasena and tipodocumento and documento and nombres and apellidos and telefono and direccion and cargoid and roldid:
        cursor = db.conn.cursor()
        sql = "UPDATE usuario SET email = ?, nombreusuario = ?, contrsena = ?, tipodocumento = ?, documento = ?, nombres = ?, apellidos = ?, telefono = ?, direccion = ?, estado = ?, cargoid = ?, rolid = ? WHERE usuarioid = ?"
        data = (email, nombreusuario, contrasena, tipodocumento, documento, nombres, apellidos, telefono, direccion, estado, cargoid, usuarioid, rolid)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('usuario'))
################################ VEHICULO ##############################
@app.route('/vehiculo')
def vehiculo():
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM vehiculo")
    myresult = cursor.fetchall()
    # Convertir los datos a diccionario
    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()
    return render_template('vehiculo.html', data=insertObject)

@app.route('/agregar_vehiculo', methods=['POST'])
def agregar_vehiculo():
    nombre = request.form['nombre']
    marca = request.form['marca']
    modelo = request.form['modelo']
    placa = request.form['placa']
    usuarioid = request.form['usuarioid']
    estado = 1 if 'estado' in request.form else 0  # Esto asignará 1 si el checkbox está marcado, y 0 si no está marcado
    if nombre and marca and modelo and placa and usuarioid:
        cursor = db.conn.cursor()
        sql = "INSERT INTO vehiculo (nombre, marca, modelo, placa, usuarioid, estado) VALUES (?, ?, ?, ?, ?, ?)"
        data = (nombre, marca, modelo, placa, usuarioid, estado)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('vehiculo'))

@app.route('/eliminar_vehiculo/<string:vehiculoid>', methods=['GET'])
def eliminar_vehiculo(vehiculoid):
    cursor = db.conn.cursor()
    sql = "DELETE FROM vehiculo WHERE vehiculoid=?"
    data = (vehiculoid,)
    cursor.execute(sql, data)
    db.conn.commit()
    return redirect(url_for('vehiculo')) 

@app.route('/editar_vehiculo/<string:vehiculoid>', methods=['POST'])
def editar_vehiculo(vehiculoid):
    nombre = request.form['nombre']
    marca = request.form['marca']
    modelo = request.form['modelo']
    placa = request.form['placa']
    usuarioid = request.form['usuarioid']
    estado = 'estado' in request.form
    if nombre and marca and modelo and placa and usuarioid:
        cursor = db.conn.cursor()
        sql = "UPDATE vehiculo SET nombre = ?, marca = ?, modelo = ?, placa = ?, usuarioid = ?, estado = ? WHERE vehiculoid = ?"
        data = (nombre, marca, modelo, placa, usuarioid, estado, vehiculoid)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('vehiculo'))

################################### REPORTES ##################################
################################## 1.DISTRITOS ##################################
@app.route('/reporte_distritos', methods=['GET'])
def reporte_distritos():
    try:
        # Obtener las fechas de inicio y fin desde los parámetros de la URL
        fecha_inicio = request.args.get('fecha_inicio', None)
        fecha_fin = request.args.get('fecha_fin', None)

        # Imprimir las fechas para verificar que se recibieron correctamente
        print(f"Fecha inicio: {fecha_inicio}, Fecha fin: {fecha_fin}")

        # Conectar a la base de datos SQL Server
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Si se proporcionan fechas de inicio y fin, filtrar por ese rango
        if fecha_inicio and fecha_fin:
            query = """
            SELECT distrito, COUNT(*) as cantidad
            FROM manifiesto2
            WHERE CAST(fecha_hora_subida AS DATE) BETWEEN ? AND ?
            GROUP BY distrito
            """
            print(f"Ejecutando la consulta: {query} con parámetros: {fecha_inicio}, {fecha_fin}")
            cursor.execute(query, (fecha_inicio, fecha_fin))
        else:
            # Si no hay fechas seleccionadas, devolver todos los datos
            query = """
            SELECT distrito, COUNT(*) as cantidad
            FROM manifiesto2
            GROUP BY distrito
            """
            print("Ejecutando consulta sin filtro de fecha.")
            cursor.execute(query)

        # Obtener resultados de la consulta
        results = cursor.fetchall()
        print(f"Resultados de la consulta: {results}")  # Depuración para ver los resultados en el servidor

        # Preparar los datos para el gráfico
        distritos = [row[0] for row in results]
        cantidades = [row[1] for row in results]

        cursor.close()
        conn.close()

        # Ver los datos que se van a enviar al frontend
        print(f"Datos enviados al frontend: Distritos: {distritos}, Cantidades: {cantidades}")

        return jsonify({"distritos": distritos, "cantidades": cantidades})
    except pyodbc.Error as e:
        print(f"Error de base de datos: {e}")
        return f"Error de base de datos: {e}"
    except Exception as e:
        print(f"Error inesperado: {e}")
        return f"Error inesperado: {e}"
################################### 2.CLIENTE ###################################
@app.route('/reporte_clientes', methods=['GET'])
def reporte_clientes():
    try:
        # Obtener las fechas de inicio y fin desde los parámetros de la URL
        fecha_inicio = request.args.get('fecha_inicio', None)
        fecha_fin = request.args.get('fecha_fin', None)

        # Imprimir las fechas para verificar que se recibieron correctamente
        print(f"Fecha inicio: {fecha_inicio}, Fecha fin: {fecha_fin}")

        # Conectar a la base de datos SQL Server
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Si se proporcionan fechas de inicio y fin, filtrar por ese rango
        if fecha_inicio and fecha_fin:
            query = """
            SELECT cliente, COUNT(*) as cantidad
            FROM manifiesto2
            WHERE CAST(fecha_hora_subida AS DATE) BETWEEN ? AND ?
            GROUP BY cliente
            """
            print(f"Ejecutando la consulta: {query} con parámetros: {fecha_inicio}, {fecha_fin}")
            cursor.execute(query, (fecha_inicio, fecha_fin))
        else:
            # Si no hay fechas seleccionadas, devolver todos los datos
            query = """
            SELECT cliente, COUNT(*) as cantidad
            FROM manifiesto2
            GROUP BY cliente
            """
            print("Ejecutando consulta sin filtro de fecha.")
            cursor.execute(query)

        # Obtener resultados de la consulta
        results = cursor.fetchall()
        print(f"Resultados de la consulta: {results}")  # Depuración para ver los resultados en el servidor

        # Preparar los datos para el gráfico
        clientes = [row[0] for row in results]
        cantidades = [row[1] for row in results]

        cursor.close()
        conn.close()

        # Ver los datos que se van a enviar al frontend
        print(f"Datos enviados al frontend: Clientes: {clientes}, Cantidades: {cantidades}")

        return jsonify({"clientes": clientes, "cantidades": cantidades})
    except pyodbc.Error as e:
        print(f"Error de base de datos: {e}")
        return f"Error de base de datos: {e}"
    except Exception as e:
        print(f"Error inesperado: {e}")
        return f"Error inesperado: {e}"
############################## 3.CLIENTE_DISTRITOS ##############################
@app.route('/reporte_clientes_distritos', methods=['GET'])
def reporte_clientes_distritos():
    try:
        # Obtener las fechas de inicio y fin desde los parámetros de la URL
        fecha_inicio = request.args.get('fecha_inicio', None)
        fecha_fin = request.args.get('fecha_fin', None)

        # Imprimir las fechas para verificar que se recibieron correctamente
        print(f"Fecha inicio: {fecha_inicio}, Fecha fin: {fecha_fin}")

        # Conectar a la base de datos SQL Server
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Si se proporcionan fechas de inicio y fin, filtrar por ese rango
        if (fecha_inicio and fecha_fin):
            query = """
            SELECT cliente, distrito, COUNT(*) as cantidad
            FROM manifiesto2
            WHERE CAST(fecha_hora_subida AS DATE) BETWEEN ? AND ?
            GROUP BY cliente, distrito
            """
            print(f"Ejecutando la consulta: {query} con parámetros: {fecha_inicio}, {fecha_fin}")
            cursor.execute(query, (fecha_inicio, fecha_fin))
        else:
            # Si no hay fechas seleccionadas, devolver todos los datos
            query = """
            SELECT cliente, distrito, COUNT(*) as cantidad
            FROM manifiesto2
            GROUP BY cliente, distrito
            """
            print("Ejecutando consulta sin filtro de fecha.")
            cursor.execute(query)

        # Obtener resultados de la consulta
        results = cursor.fetchall()

        # Preparar los datos para el gráfico
        clientes_distritos = [{"cliente": row[0], "distrito": row[1], "cantidad": row[2]} for row in results]

        cursor.close()
        conn.close()

        # Ver los datos que se van a enviar al frontend
        print(f"Datos enviados al frontend: {clientes_distritos}")

        return jsonify({"clientes_distritos": clientes_distritos})
    except pyodbc.Error as e:
        print(f"Error de base de datos: {e}")
        return f"Error de base de datos: {e}"
    except Exception as e:
        print(f"Error inesperado: {e}")
        return f"Error inesperado: {e}"
################################ 4.ENVIOS_RANGO #################################
@app.route('/reporte_porcentaje_faltantes', methods=['GET'])
def reporte_porcentaje_faltantes():
    try:
        # Obtener las fechas de inicio y fin desde los parámetros de la URL
        fecha_inicio = request.args.get('fecha_inicio', None)
        fecha_fin = request.args.get('fecha_fin', None)

        # Conexión a la base de datos
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Consulta SQL con filtrado por fechas si se proporcionan
        if fecha_inicio and fecha_fin:
            query = """
            SELECT 
                CASE 
                    WHEN fecha_hora_entrega IS NULL THEN 'Faltantes' 
                    ELSE 'Entregados' 
                END AS estado,
                COUNT(*) AS cantidad
            FROM 
                manifiesto2
            WHERE 
                CAST(fecha_hora_subida AS DATE) BETWEEN ? AND ?
            GROUP BY 
                CASE 
                    WHEN fecha_hora_entrega IS NULL THEN 'Faltantes' 
                    ELSE 'Entregados' 
                END;
            """
            print(f"Ejecutando la consulta con parámetros: {fecha_inicio}, {fecha_fin}")
            cursor.execute(query, (fecha_inicio, fecha_fin))
        else:
            # Si no se proporcionan fechas, ejecutar la consulta general
            query = """
            SELECT 
                CASE 
                    WHEN fecha_hora_entrega IS NULL THEN 'Faltantes' 
                    ELSE 'Entregados' 
                END AS estado,
                COUNT(*) AS cantidad
            FROM 
                manifiesto2
            GROUP BY 
                CASE 
                    WHEN fecha_hora_entrega IS NULL THEN 'Faltantes' 
                    ELSE 'Entregados' 
                END;
            """
            print("Ejecutando consulta sin filtro de fecha.")
            cursor.execute(query)

        # Ejecutar la consulta y obtener los resultados
        results = cursor.fetchall()

        # Procesar los resultados para convertirlos en JSON
        estados = [row[0] for row in results]  # 'Faltantes' o 'Entregados'
        cantidades = [row[1] for row in results]  # Cantidad de items en cada estado
        
        # Cerrar conexión a la base de datos
        cursor.close()
        conn.close()

        # Ver los datos que se enviarán al frontend
        print(f"Datos enviados al frontend: Estados: {estados}, Cantidades: {cantidades}")

        # Devolver los datos en formato JSON
        return jsonify({"estados": estados, "cantidades": cantidades})

    except pyodbc.Error as e:
        return f"Error de base de datos: {e}", 500
    except Exception as e:
        return f"Error inesperado: {e}", 500
################################ 5.ENVIOS_FECHA #################################
# @app.route('/reporte_envios_fecha', methods=['GET'])
# def reporte_envios_fecha():
#     try:
#         fecha = request.args.get('fecha', None)  # Obtener la fecha desde los parámetros de la URL
#         print(f"Fecha seleccionada: {fecha}")

#         conn = pyodbc.connect(conn_str)
#         cursor = conn.cursor()

#         # Si hay una fecha seleccionada, no necesitas agrupar
#         if fecha:
#             query = """
#             SELECT COUNT(*) as cantidad
#             FROM manifiesto2
#             WHERE CAST(fecha_hora_entrega AS DATE) = ?
#             """
#             cursor.execute(query, fecha)
#             result = cursor.fetchone()
#             fechas = [fecha]  # Como solo es una fecha, devolvemos la misma
#             cantidades = [result[0]]  # La cantidad obtenida
#         else:
#             # Si no hay fecha seleccionada, se agrupan todas las fechas
#             query = """
#             SELECT CAST(fecha_hora_entrega AS DATE) AS fecha_hora_entrega, COUNT(*) as cantidad
#             FROM manifiesto2
#             GROUP BY CAST(fecha_hora_entrega AS DATE)
#             ORDER BY fecha_hora_entrega
#             """
#             cursor.execute(query)
#             results = cursor.fetchall()
#             fechas = [row[0].strftime('%Y-%m-%d') for row in results]
#             cantidades = [row[1] for row in results]

#         cursor.close()
#         conn.close()

#         return jsonify({"fechas": fechas, "cantidades": cantidades})
#     except pyodbc.Error as e:
#         print(f"Error de base de datos: {e}")
#         return f"Error de base de datos: {e}"
#     except Exception as e:
#         print(f"Error inesperado: {e}")
#         return f"Error inesperado: {e}"
############################### ENVIOS_SERVICIO ###############################
# @app.route('/reporte_envios_servicio')
# def reporte_envios_servicio():
#     try:
#         conn = pyodbc.connect(conn_str)
#         cursor = conn.cursor()
        
#         query = """
#         SELECT servicio, COUNT(*) as cantidad
#         FROM manifiesto2
#         GROUP BY servicio
#         """
#         cursor.execute(query)
#         results = cursor.fetchall()
        
#         servicios = [row[0] for row in results]
#         cantidades = [row[1] for row in results]
        
#         cursor.close()
#         conn.close()
        
#         return jsonify({"servicios": servicios, "cantidades": cantidades})
#     except pyodbc.Error as e:
#         return f"Error de base de datos: {e}"
#     except Exception as e:
#         return f"Error inesperado: {e}"
################################ MONTO_CLIENTE ################################
# @app.route('/reporte_monto_cliente')
# def reporte_monto_cliente():
#     try:
#         conn = pyodbc.connect(conn_str)
#         cursor = conn.cursor()
        
#         query = """
#         SELECT cliente, SUM(monto) as monto_total
#         FROM manifiesto2
#         GROUP BY cliente
#         """
#         cursor.execute(query)
#         results = cursor.fetchall()
        
#         clientes = [row[0] for row in results]
#         montos = [row[1] for row in results]
        
#         cursor.close()
#         conn.close()
        
#         return jsonify({"clientes": clientes, "montos": montos})
#     except pyodbc.Error as e:
#         return f"Error de base de datos: {e}"
#     except Exception as e:
#         return f"Error inesperado: {e}"
################################ ESTADO_ENVIOS ################################
# @app.route('/reporte_estado_envios')
# def reporte_estado_envios():
#     try:
#         conn = pyodbc.connect(conn_str)
#         cursor = conn.cursor()
        
#         query = """
#         SELECT estado, COUNT(*) as cantidad
#         FROM manifiesto2
#         GROUP BY estado
#         """
#         cursor.execute(query)
#         results = cursor.fetchall()
        
#         estados = [row[0] for row in results]
#         cantidades = [row[1] for row in results]
        
#         cursor.close()
#         conn.close()
        
#         return jsonify({"estados": estados, "cantidades": cantidades})
#     except pyodbc.Error as e:
#         return f"Error de base de datos: {e}"
#     except Exception as e:
#         return f"Error inesperado: {e}"

if __name__ == '__main__':
    app.run(debug=True)