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
import os
import database as db
import pandas as pd
import secrets
from secrets import SystemRandom
from flask_wtf import FlaskForm 
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired
from flask_wtf.csrf import CSRFProtect, CSRFError

class LoginForm(FlaskForm):
    txtEmail = StringField('Email', validators=[DataRequired()])
    txtContrasena = PasswordField('Contraseña', validators=[DataRequired()])

app = Flask(__name__)
app.config['SECRET_KEY'] = db.secretkey
csrf = CSRFProtect(app) 

adf_client = db.adf_client
gmaps = db.gmaps
conn_str = db.connection_string
resourcegroupname = db.resourcegroupname
datafactoryname = db.datafactoryname
pipelinename = db.pipelinename


@app.route('/', methods=["GET", "POST"])
def home():
    form = LoginForm()
    return render_template('login.html', form=form)

@app.route('/admin')
def admin():
    return render_template('index2.html')

@app.route('/acceso-login', methods=["POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit(): 
        print("Formulario validado correctamente")
        _email = form.txtEmail.data
        _contrasena = form.txtContrasena.data

        try:
            cursor = db.conn.cursor()
            cursor.execute('SELECT usuarioid, rolid FROM usuario WHERE email = ? AND contrasena = ?', (_email, _contrasena))
            account = cursor.fetchone()
            cursor.close()

            if account:
                usuarioid, rolid = account[0], account[1]
                
                if rolid in (3,1):
                    return render_template("index2.html")
                elif rolid == 2:
                    return render_template("admin2.html")
                else:
                    return render_template('login.html', form=form, mensaje="Rol no válido")
                    #return render_template('login.html', mensaje="Rol no válido")
            else:
                return render_template('login.html', form=form, mensaje="Usuario o contraseña incorrecta")
                #return render_template('login.html', mensaje="Usuario o contraseña incorrecta")
        except pyodbc.Error as e:
            return f"Error de base de datos: {e}"
        except Exception as e:
            return f"Error inesperado: {e}"
    else:
        print("Errores en el formulario:", form.errors)
    #return render_template('login.html')
    return render_template('login.html', form=form)

@csrf.exempt
@app.route('/analizar', methods=['POST'])
def upload():
    base64_data = request.form['base64Data']
    try:
        if not base64_data.startswith(("data:image/jpeg", "data:image/jpg", "data:image/png")):
            return "Error: Solo se admiten imágenes en formato JPEG, JPG o PNG"

        base64_data_cleaned = base64_data.split(',')[1]
        image_data = base64.b64decode(base64_data_cleaned)
        image = Image.open(BytesIO(image_data))
        invoice_data = recognize_invoices(image)

        with open("archivo.csv", mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerows(invoice_data)

        subprocess.run(['python', 'csv_to_database.py'], check=True)

        response = adf_client.pipelines.create_run(resourcegroupname, datafactoryname, pipelinename)
        print(f'Pipeline run ID: {response.run_id}')

        pipeline_run = adf_client.pipeline_runs.get(resourcegroupname, datafactoryname, response.run_id)
        while pipeline_run.status in ['InProgress', 'Queued']:
            pipeline_run = adf_client.pipeline_runs.get(resourcegroupname, datafactoryname, response.run_id)

        subprocess.run(['python', 'update_fecha_subida.py'], check=True)
        
        cursor = db.conn.cursor()
        sql_update_estado = """
            UPDATE bdmanifiestos.dbo.Manifiesto2
            set estado = case
                WHEN fecha_hora_entrega IS NOT NULL AND fecha_hora_subida IS NOT NULL
                THEN 1
                ELSE 0 
            END;
        """
        cursor.execute(sql_update_estado)  
        db.conn.commit()           
        cursor.execute("SELECT * FROM manifiesto2")
        rows = cursor.fetchall()
        cursor.close()
        
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

@csrf.exempt
@app.route('/ver_tabla', methods=['GET', 'POST'])
def ver_tabla():
    try:
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM manifiesto2")
        rows = cursor.fetchall()
        cursor.close()
        
        data = [list(row) for row in rows]

        return render_template('tabla.html', data=data)  
    except pyodbc.Error as e:
        return f"Error de base de datos: {e}"
    except Exception as e:
        return f"Error: {e}"

# distance_matrix.py
from typing import List, Dict
import time

def chunk_addresses(addresses: List[str], chunk_size: int = 10) -> List[List[str]]:
    """Divide la lista de direcciones en chunks más pequeños."""
    return [addresses[i:i + chunk_size] for i in range(0, len(addresses), chunk_size)]

def get_distance_matrix(addresses: List[str], gmaps) -> List[List[float]]:
    """
    Obtiene la matriz de distancias usando Google Maps Distance Matrix API,
    manejando las limitaciones de la API dividiendo en chunks.
    """
    CHUNK_SIZE = 10  # Google Maps API tiene un límite de 10x10 elementos por solicitud
    chunks = chunk_addresses(addresses, CHUNK_SIZE)
    matrix_size = len(addresses)
    distance_matrix = [[float('inf')] * matrix_size for _ in range(matrix_size)]
    
    try:
        for i, origins_chunk in enumerate(chunks):
            origin_start = i * CHUNK_SIZE
            
            for j, destinations_chunk in enumerate(chunks):
                dest_start = j * CHUNK_SIZE
                
                # Añadir delay para evitar límites de rate
                time.sleep(0.5)
                
                result = gmaps.distance_matrix(
                    origins_chunk,
                    destinations_chunk,
                    mode="driving",
                    language="es",
                    units="metric"
                )
                
                # Procesar resultados
                for row_idx, row in enumerate(result['rows']):
                    for elem_idx, element in enumerate(row['elements']):
                        if element['status'] == 'OK':
                            matrix_i = origin_start + row_idx
                            matrix_j = dest_start + elem_idx
                            if matrix_i < matrix_size and matrix_j < matrix_size:
                                distance_matrix[matrix_i][matrix_j] = element['distance']['value']
        
        return distance_matrix
    except Exception as e:
        print(f"Error al obtener matriz de distancias: {e}")
        return None

# route_optimizer.py
def calculate_total_distance(route: List[int], distance_matrix: List[List[float]]) -> float:
    """Calcula la distancia total de una ruta."""
    if not route or not distance_matrix:
        return float('inf')
    
    total = 0
    for i in range(len(route) - 1):
        total += distance_matrix[route[i]][route[i + 1]]
    # Añadir retorno al inicio
    total += distance_matrix[route[-1]][route[0]]
    return total

def initialize_population(pop_size: int, num_locations: int) -> List[List[int]]:
    """Inicializa la población con permutaciones aleatorias."""
    population = []
    for _ in range(pop_size):
        # Mantener el punto de inicio (índice 0) fijo
        route = list(range(1, num_locations))
        random.shuffle(route)
        route = [0] + route  # Añadir el punto de inicio al principio
        population.append(route)
    return population

def crossover_pmx(parent1: List[int], parent2: List[int]) -> tuple:
    """Implementa Partially Mapped Crossover (PMX)."""
    size = len(parent1)
    point1, point2 = sorted(random.sample(range(1, size), 2))
    
    def pmx_helper(p1, p2):
        child = [-1] * size
        child[0] = 0  # Mantener el punto de inicio fijo
        
        # Copiar segmento del primer padre
        child[point1:point2] = p1[point1:point2]
        
        # Mapear elementos del segundo padre
        mapping = dict(zip(p1[point1:point2], p2[point1:point2]))
        
        # Rellenar resto de posiciones
        for i in range(1, size):
            if i < point1 or i >= point2:
                current = p2[i]
                while current in child:
                    current = mapping.get(current, current)
                child[i] = current
                
        return child
    
    child1 = pmx_helper(parent1, parent2)
    child2 = pmx_helper(parent2, parent1)
    
    return child1, child2

def mutate(solution: List[int], mutation_rate: float) -> List[int]:
    """Aplica mutación swap preservando el punto de inicio."""
    if random.random() < mutation_rate:
        idx1, idx2 = random.sample(range(1, len(solution)), 2)
        solution[idx1], solution[idx2] = solution[idx2], solution[idx1]
    return solution

def genetic_algorithm(addresses: List[str], gmaps, pop_size: int = 50, 
                     generations: int = 100, mutation_rate: float = 0.1) -> List[int]:
    """
    Implementa el algoritmo genético para optimización de rutas.
    """
    # Obtener matriz de distancias
    distance_matrix = get_distance_matrix(addresses, gmaps)
    if not distance_matrix:
        raise ValueError("No se pudo obtener la matriz de distancias")
    
    num_locations = len(addresses)
    population = initialize_population(pop_size, num_locations)
    best_route = None
    best_distance = float('inf')
    
    for generation in range(generations):
        # Evaluar población
        fitness_scores = [calculate_total_distance(route, distance_matrix) 
                         for route in population]
        
        # Actualizar mejor ruta
        min_idx = fitness_scores.index(min(fitness_scores))
        if fitness_scores[min_idx] < best_distance:
            best_distance = fitness_scores[min_idx]
            best_route = population[min_idx]
        
        # Selección y reproducción
        new_population = [best_route]  # Elitismo
        
        while len(new_population) < pop_size:
            # Selección por torneo
            tournament = random.sample(list(enumerate(fitness_scores)), 5)
            parents = sorted(tournament, key=lambda x: x[1])[:2]
            parent1, parent2 = population[parents[0][0]], population[parents[1][0]]
            
            # Crossover y mutación
            child1, child2 = crossover_pmx(parent1, parent2)
            child1, child2 = mutate(child1, mutation_rate), mutate(child2, mutation_rate)
            
            new_population.extend([child1, child2])
        
        population = new_population[:pop_size]
    
    return best_route

def validar_direccion(direccion):
    try:
        result = db.gmaps.geocode(direccion)
        if result:
            return True
        return False
    except Exception:
        return False

# routes.py
@app.route('/ver_mapa', methods=['GET'])
def ver_mapa():
    try:
        fecha_filtro = request.args.get('fecha', None)
        
        conn = pyodbc.connect(db.connection_string)
        cursor = conn.cursor()
        
        if fecha_filtro:
            cursor.execute("""
                SELECT TOP 25 direccion, distrito, servicio, fecha_hora_subida 
                FROM manifiesto2 
                WHERE CAST(fecha_hora_subida AS DATE) = ?
            """, (fecha_filtro,))
        else:
            cursor.execute("""
                SELECT TOP 25 direccion, distrito, servicio, fecha_hora_subida 
                FROM manifiesto2
            """)
        
        rows = cursor.fetchall()
        print(f"Filtrado por fecha {fecha_filtro}: {rows}")
        cursor.close()  # Cerrar el cursor
        conn.close()    # Cerrar la conexión
        
        if not rows:
            return render_template('mapa.html', mensaje="No se encontraron direcciones para mostrar")
        
        # Punto de inicio/fin
        START_ADDRESS = "CALLE LOS SAUCES 568 URBANIZACION SANTA VICTORIA, CHICLAYO"
        
        # Preparar direcciones incluyendo punto de inicio
        direcciones = [START_ADDRESS]
        for row in rows:
            direccion_completa = f"{row.direccion.strip()}, {row.distrito.strip()}, Chiclayo, Peru"
            if validar_direccion(direccion_completa):
                direcciones.append(direccion_completa)
            else:
                print(f"Dirección inválida: {direccion_completa}")
        
        # Obtener matriz de distancias
        distance_matrix = []
        for origen in direcciones:
            row_distances = []
            for destino in direcciones:
                if origen == destino:
                    row_distances.append(0)
                    continue
                
                try:
                    result = db.gmaps.distance_matrix(
                        origen,
                        destino,
                        mode="driving",
                        language="es"
                    )
                    
                    if result['rows'][0]['elements'][0]['status'] == 'OK':
                        distance = result['rows'][0]['elements'][0]['distance']['value']
                        row_distances.append(distance)
                    else:
                        row_distances.append(float('inf'))
                except Exception as e:
                    print(f"Error obteniendo distancia entre {origen} y {destino}: {e}")
                    row_distances.append(float('inf'))
            
            distance_matrix.append(row_distances)
        
        # Implementar algoritmo del vecino más cercano
        def nearest_neighbor(distances, start_idx=0):
            n = len(distances)
            unvisited = set(range(n))
            route = [start_idx]
            unvisited.remove(start_idx)
            
            while unvisited:
                current = route[-1]
                next_city = min(unvisited, key=lambda x: distances[current][x])
                route.append(next_city)
                unvisited.remove(next_city)
            
            # Volver al inicio
            route.append(start_idx)
            return route
        
        # Obtener ruta optimizada
        optimal_route = nearest_neighbor(distance_matrix)
        
        # Geocodificar direcciones en orden optimizado
        geocoded_addresses = []
        for i, idx in enumerate(optimal_route[:-1]):  # Excluir última repetición del inicio
            direccion = direcciones[idx]
            try:
                geocode_result = db.gmaps.geocode(direccion)
                if geocode_result:
                    location = geocode_result[0]['geometry']['location']
                    # Si idx es 0, es el punto de inicio/fin
                    if idx == 0:
                        geocoded_addresses.append({
                            'label': 'INICIO/FIN',
                            'address': direccion,
                            'latitude': location['lat'],
                            'longitude': location['lng'],
                            'servicio': 'INICIO/FIN',
                            'orden': i,
                            'fecha_hora_subida': None
                        })
                    else:
                        # Restamos 1 a idx porque el array rows no incluye la dirección de inicio
                        geocoded_addresses.append({
                            'label': f'Parada {i}',
                            'address': direccion,
                            'latitude': location['lat'],
                            'longitude': location['lng'],
                            'servicio': rows[idx-1].servicio,
                            'orden': i,
                            'fecha_hora_subida': rows[idx-1].fecha_hora_subida.strftime('%Y-%m-%d %H:%M:%S') if rows[idx-1].fecha_hora_subida else None
                        })
            except Exception as e:
                print(f"Error geocodificando {direccion}: {e}")

        # Convertir a JSON para el template
        json_data = json.dumps(geocoded_addresses)
        servicios_unicos = sorted(set(row.servicio.strip() for row in rows))
        
        return render_template('mapa.html', 
                             direcciones_geocodificadas=json_data,
                             servicios_unicos=servicios_unicos)
        
    except Exception as e:
        return f"Error inesperado: {e}"


def format_date_time(date_time_str):
    """
    This function ensures the date is formatted as 'YYYY-MM-DD HH:MM:SS' before being passed to SQL Server.
    If the format is incorrect, it uses the current time as a fallback.
    """
    try:
        return datetime.strptime(date_time_str, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            return datetime.strptime(date_time_str, '%a, %d %b %Y %H:%M:%S %Z').strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            print(f"Invalid date format received: {date_time_str}. Using current time.")
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

@csrf.exempt
@app.route('/actualizar_hora_entrega', methods=['POST'])
def actualizar_hora_entrega():
    data = request.json
    print("Datos recibidos:", data) 
    try:
        cursor = db.conn.cursor()

        for item in data['items']:
            print(f"Actualizando item: {item['item']}")
            
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
            
            sql_update_estado = """
            UPDATE bdmanifiestos.dbo.Manifiesto2
            SET estado = CASE
                WHEN fecha_hora_entrega IS NOT NULL AND fecha_hora_subida IS NOT NULL
                THEN 1
                ELSE 0 
            END
            WHERE item = ?
            """
            cursor.execute(sql_update_estado, (item['item'],)) 
            
        print("Comenzando commit...")
        db.conn.commit()
        print("Commit realizado con éxito para las actualizaciones de items.")

        item_ids = [item['item'] for item in data['items']]
        if not item_ids:
            return jsonify({"status": "error", "message": "No hay ítems para actualizar."}), 400

        placeholders = ', '.join(['?'] * len(item_ids))
        print(placeholders)
        sql_select = f"""
            SELECT 
                item,  
                fecha_hora_subida,
                fecha_hora_entrega,
                CASE 
                    WHEN fecha_hora_entrega IS NULL THEN 'NULL'
                    ELSE DATEDIFF(MINUTE, fecha_hora_subida, fecha_hora_entrega)
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
            
            if cumplimiento != 'NULL' and cumplimiento is not None:
                if cumplimiento < 60:
                    cumplimiento_formateado = f"{cumplimiento} MINUTOS"
                else:
                    horas = cumplimiento // 60
                    minutos = cumplimiento % 60
                    cumplimiento_formateado = f"{horas} HORAS {minutos} MINUTOS"
            else:
                cumplimiento_formateado = None

            cumplimiento_result.append({
                "item": item_id,
                "fecha_hora_subida": row[1],
                "fecha_hora_entrega": row[2],
                "cumplimiento": cumplimiento,
                "cumplimiento_formateado": cumplimiento_formateado
            })

            sql_update_cumplimiento = """
                UPDATE manifiesto2
                SET cumplimiento = ?,
                    cumplimiento_formateado = ?
                WHERE item = ?
            """
            cursor.execute(sql_update_cumplimiento, (cumplimiento, cumplimiento_formateado, item_id))
      
        db.conn.commit()
        print("Commit realizado para actualizaciones de cumplimiento.")
        return jsonify({"status": "success", "cumplimiento": cumplimiento_result}), 200

    except Exception as e:
        print("Error durante la actualización:", e)
        conn.rollback() 
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cursor.close()
        
@csrf.exempt
@app.route('/eliminar_entrega', methods=['POST'])
def eliminar_entrega():
    data = request.json
    print("Datos recibidos:", data) 
    
    try:
        cursor = db.conn.cursor()

        if 'items' not in data or not data['items']:
            raise ValueError("No se han proporcionado ítems para eliminar")

        for item in data['items']:
            item_id = int(item['item'])  
            print(f"Procesando item: {item_id}")
            
            if item.get('eliminar'): 
                sql_delete = """
                    UPDATE manifiesto2
                    SET fecha_hora_entrega = NULL, cumplimiento = NULL, estado = 0, cumplimiento_formateado = NULL
                    WHERE item = ?
                """
                print(f"Ejecutando SQL: {sql_delete} para item {item_id}")
                
                result = cursor.execute(sql_delete, (item['item'],))
                if result.rowcount == 0:
                    print(f"No se encontró el ítem {item_id} para actualizar.")
                else:
                    print(f"Fecha y cumplimiento eliminados para el ítem {item_id}. Filas afectadas: {result.rowcount}")
        
        print("Realizando commit de los cambios...")
        db.conn.commit()
        print("Cambios guardados exitosamente en la base de datos.")

        return jsonify({"status": "success", "message": "Datos eliminados correctamente"}), 200

    except Exception as e:
        print(f"Error durante la eliminación: {e}")
        conn.rollback() 
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        cursor.close()

################################ MANTENIMIENTOS ###############################
#################################### CARGO ####################################
@app.route('/cargo')
def cargo():
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM cargo")
    myresult = cursor.fetchall()
    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()
    return render_template('cargo.html', data=insertObject)

#@csrf.exempt
@app.route('/agregar_cargo', methods=['POST'])
def agregar_cargo():
    titulo = request.form.get('titulo')
    descripcion = request.form.get('descripcion')
    estado = 1 if request.form.get('estado') else 0 
    try:
        if titulo and descripcion:
            titulo = titulo.strip()
            descripcion = descripcion.strip()
            if titulo and descripcion:
                cursor = db.conn.cursor()
                sql = "INSERT INTO cargo (titulo, descripcion, estado) VALUES (?, ?, ?)"
                data = (titulo, descripcion, estado)
                cursor.execute(sql, data)
                db.conn.commit()
                cursor.close()
                return redirect(url_for('cargo'))
        else:
            return "Faltan campos requeridos", 400
    except Exception as e:
        print(f"Error al insertar cargo: {e}")
        return "Error al insertar cargo", 500

@app.route('/eliminar_cargo/<string:cargoid>', methods=['GET'])
def eliminar_cargo(cargoid):
    cursor = db.conn.cursor()
    sql = "DELETE FROM cargo WHERE cargoid=?"
    data = (cargoid,)
    cursor.execute(sql, data)
    db.conn.commit()
    return redirect(url_for('cargo')) 

#@csrf.exempt
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
    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()
    return render_template('roles.html', data=insertObject)

#@csrf.exempt
@app.route('/agregar_roles', methods=['POST'])
def agregar_roles():
    descripcion = request.form['descripcion']
    estado = 1 if 'estado' in request.form else 0  
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

#@csrf.exempt
@app.route('/editar_roles/<string:rolid>', methods=['POST'])
def editar_roles(rolid):
    try:
        descripcion = request.form['descripcion']
        estado = 'estado' in request.form
        if descripcion:
            cursor = db.conn.cursor()
            sql = "UPDATE roles SET descripcion = ?, estado = ? WHERE rolid = ?"
            data = (descripcion, estado, rolid)
            cursor.execute(sql, data)
            db.conn.commit()
        else:
            return redirect(url_for('roles'))
    except Exception as e:
        print(f"Error al editar el rol: {e}")
        return f"Error: {e}", 500
    return redirect(url_for('roles'))
################################ TIPO DOCUMENTO ###############################
@app.route('/tipoDocumento')
def tipoDocumento():
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM TipoDocumento")
    myresult = cursor.fetchall()
    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()
    return render_template('tipoDocumento.html', data=insertObject)

#@csrf.exempt
@app.route('/agregar_tipodocumento', methods=['POST'])
def agregar_tipodocumento():
    try:
        Acronimo = request.form['Acronimo']
        Descripcion = request.form['Descripcion']
        estado = 1 if 'estado' in request.form else 0  
        
        if Acronimo and Descripcion:
            cursor = db.conn.cursor()
            sql = "INSERT INTO TipoDocumento (Acronimo, Descripcion, estado) VALUES (?, ?, ?)"
            data = (Acronimo, Descripcion, estado)
            cursor.execute(sql, data)
            db.conn.commit()
        return redirect(url_for('tipoDocumento'))
    except KeyError as e:
        return f"Falta clave de formulario: {e}", 400
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/eliminar_tipodocumento/<string:TipodocumentoID>', methods=['GET'])
def eliminar_tipodocumento(TipodocumentoID):
    cursor = db.conn.cursor()
    sql = "DELETE FROM TipoDocumento WHERE TipodocumentoID=?"
    data = (TipodocumentoID,)
    cursor.execute(sql, data)
    db.conn.commit()
    return redirect(url_for('tipoDocumento')) 

#@csrf.exempt
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
    query = """
        SELECT u.*, d.Acronimo, c.titulo, r.descripcion
        FROM Usuario u
        JOIN TipoDocumento d ON d.TipodocumentoID = u.tipodocumento AND d.estado = 1
        JOIN Cargo c ON c.cargoid = u.cargoid AND c.estado = 1
        JOIN Roles r ON r.rolid = u.rolid AND r.estado = 1;
    """
    cursor.execute(query)
    myresult = cursor.fetchall()

    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()

    cursor = db.conn.cursor()
    cursor.execute("SELECT TipodocumentoID, Acronimo FROM TipoDocumento WHERE estado = 1")
    tipodocumentos_activos = cursor.fetchall()
    tipodocumentos = [{'TipodocumentoID': row[0], 'Acronimo': row[1]} for row in tipodocumentos_activos]
    cursor.close()

    cursor = db.conn.cursor()
    cursor.execute("SELECT cargoid, titulo FROM Cargo WHERE estado = 1")
    cargos_activos = cursor.fetchall()
    cargos = [{'cargoid': row[0], 'titulo': row[1]} for row in cargos_activos]
    cursor.close()

    cursor = db.conn.cursor()
    cursor.execute("SELECT rolid, descripcion FROM Roles WHERE estado = 1")
    roles_activos = cursor.fetchall()
    roles = [{'rolid': row[0], 'descripcion': row[1]} for row in roles_activos]
    cursor.close()

    return render_template('usuario.html', data=insertObject, tipodocumentos=tipodocumentos, cargos=cargos, roles=roles)

#@csrf.exempt
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
    estado = 1 if 'estado' in request.form else 0  
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

#@csrf.exempt
@app.route('/editar_usuario/<string:usuarioid>', methods=['POST'])
def editar_usuario(usuarioid):
    try:
        email = request.form.get('email')
        contrasena = request.form.get('contrasena')
        nombreusuario = request.form.get('nombreusuario')
        tipodocumento = request.form.get('tipodocumento')
        documento = request.form.get('documento')
        nombres = request.form.get('nombres')
        apellidos = request.form.get('apellidos')
        telefono = request.form.get('telefono')
        direccion = request.form.get('direccion')
        estado = 'estado' in request.form
        cargoid = request.form.get('cargoid')
        rolid = request.form.get('rolid')

        if not tipodocumento:
            print("Error: tipodocumento no puede ser nulo.")
            return "Error: tipodocumento es obligatorio y no puede ser nulo", 400

        if email and nombreusuario and contrasena and documento and nombres and apellidos and telefono and direccion and cargoid and rolid:
            cursor = db.conn.cursor()
            sql = """
                UPDATE usuario
                SET email = ?, nombreusuario = ?, contrasena = ?, tipodocumento = ?, documento = ?, nombres = ?, apellidos = ?, telefono = ?, direccion = ?, estado = ?, cargoid = ?, rolid = ?
                WHERE usuarioid = ?
            """
            data = (email, nombreusuario, contrasena, tipodocumento, documento, nombres, apellidos, telefono, direccion, estado, cargoid, rolid, usuarioid)
            cursor.execute(sql, data)
            db.conn.commit()
            cursor.close()
        else:
            print("Campos obligatorios faltantes")
            return "Error: Campos obligatorios faltantes", 400

        return redirect(url_for('usuario'))
    except Exception as e:
        print(f"Error al editar el usuario: {e}")
        print("Datos recibidos:", request.form)
        return "Error al procesar la solicitud", 400
################################ VEHICULO ##############################
@app.route('/vehiculo')
def vehiculo():
    cursor = db.conn.cursor()
    query = """
        SELECT v.*, u.nombres, u.apellidos 
        FROM vehiculo v
        JOIN Usuario u ON v.usuarioid = u.usuarioid
    """
    cursor.execute(query)
    myresult = cursor.fetchall()

    insertObject = []
    columnNames = [column[0] for column in cursor.description]
    for record in myresult:
        insertObject.append(dict(zip(columnNames, record)))
    cursor.close()
    
    cursor = db.conn.cursor()
    cursor.execute("SELECT usuarioid, nombres, apellidos FROM Usuario WHERE estado = 1")
    usuarios_activos = cursor.fetchall()
    print(usuarios_activos)

    usuarios = [{'usuarioid': row[0], 'nombres': row[1], 'apellidos': row[2]} for row in usuarios_activos]
    cursor.close()
    return render_template('vehiculo.html', data=insertObject, usuarios=usuarios)

#@csrf.exempt
@app.route('/agregar_vehiculo', methods=['POST'])
def agregar_vehiculo():
    marca = request.form['marca']
    modelo = request.form['modelo']
    placa = request.form['placa']
    usuarioid = request.form['usuarioid']
    estado = 1 if 'estado' in request.form else 0  
    if marca and modelo and placa and usuarioid:
        cursor = db.conn.cursor()
        sql = "INSERT INTO vehiculo (marca, modelo, placa, usuarioid, estado) VALUES (?, ?, ?, ?, ?)"
        data = (marca, modelo, placa, usuarioid, estado)
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

#@csrf.exempt
@app.route('/editar_vehiculo/<string:vehiculoid>', methods=['POST'])
def editar_vehiculo(vehiculoid):
    marca = request.form['marca']
    modelo = request.form['modelo']
    placa = request.form['placa']
    usuarioid = request.form['usuarioid']
    estado = 'estado' in request.form
    if marca and modelo and placa and usuarioid:
        cursor = db.conn.cursor()
        sql = "UPDATE vehiculo SET marca = ?, modelo = ?, placa = ?, usuarioid = ?, estado = ? WHERE vehiculoid = ?"
        data = (marca, modelo, placa, usuarioid, estado, vehiculoid)
        cursor.execute(sql, data)
        db.conn.commit()
    return redirect(url_for('vehiculo'))

################################### REPORTES ##################################
def get_db_connection():
    return pyodbc.connect(db.connection_string)
################################## 1.DISTRITOS ##################################
@app.route('/reporte_distritos', methods=['GET'])
def reporte_distritos():
    conn = db.conn 
    try:
        fecha_inicio = request.args.get('fecha_inicio', None)
        fecha_fin = request.args.get('fecha_fin', None)

        cursor = db.conn.cursor()

        if fecha_inicio and fecha_fin:
            query = """
            SELECT distrito, COUNT(*) as cantidad
            FROM manifiesto2
            WHERE CAST(fecha_hora_subida AS DATE) BETWEEN ? AND ?
            GROUP BY distrito
            """
            cursor.execute(query, (fecha_inicio, fecha_fin))
        else:
            query = """
            SELECT distrito, COUNT(*) as cantidad
            FROM manifiesto2
            GROUP BY distrito
            """
            cursor.execute(query)

        results = cursor.fetchall()
        distritos = [row[0] for row in results]
        cantidades = [row[1] for row in results]

        return jsonify({"distritos": distritos, "cantidades": cantidades})
    except pyodbc.Error as e:
        print(f"Error de base de datos: {e}")
        return f"Error de base de datos: {e}", 500
    except Exception as e:
        print(f"Error inesperado: {e}")
        return f"Error inesperado: {e}", 500
################################### 2.CLIENTE ###################################
@app.route('/reporte_clientes', methods=['GET'])
def reporte_clientes():
    conn = get_db_connection() 
    try:
        fecha_inicio = request.args.get('fecha_inicio', None)
        fecha_fin = request.args.get('fecha_fin', None)

        print(f"Fecha inicio: {fecha_inicio}, Fecha fin: {fecha_fin}")

        conn = get_db_connection()
        cursor = conn.cursor()

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

            query = """
            SELECT cliente, COUNT(*) as cantidad
            FROM manifiesto2
            GROUP BY cliente
            """
            print("Ejecutando consulta sin filtro de fecha.")
            cursor.execute(query)

        results = cursor.fetchall()
        print(f"Resultados de la consulta: {results}") 

        clientes = [row[0] for row in results]
        cantidades = [row[1] for row in results]
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
    conn = get_db_connection()
    try:
        fecha_inicio = request.args.get('fecha_inicio', None)
        fecha_fin = request.args.get('fecha_fin', None)

        print(f"Fecha inicio: {fecha_inicio}, Fecha fin: {fecha_fin}")

        conn = get_db_connection()
        cursor = conn.cursor()

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
            query = """
            SELECT cliente, distrito, COUNT(*) as cantidad
            FROM manifiesto2
            GROUP BY cliente, distrito
            """
            print("Ejecutando consulta sin filtro de fecha.")
            cursor.execute(query)

        results = cursor.fetchall()
        
        clientes_distritos = [{"cliente": row[0], "distrito": row[1], "cantidad": row[2]} for row in results]
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
    conn = get_db_connection()
    try:
        fecha_inicio = request.args.get('fecha_inicio', None)
        fecha_fin = request.args.get('fecha_fin', None)

        conn = get_db_connection()
        cursor = conn.cursor()

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
            cursor.execute(query, (fecha_inicio, fecha_fin))
        else:
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
            cursor.execute(query)

        results = cursor.fetchall()
        
        estados = [row[0] for row in results] 
        cantidades = [row[1] for row in results]  

        return jsonify({"estados": estados, "cantidades": cantidades})
    except pyodbc.Error as e:
        print(f"Error de base de datos: {e}")
        return f"Error de base de datos: {e}", 500
    except Exception as e:
        print(f"Error inesperado: {e}")
        return f"Error inesperado: {e}", 500
    finally:
        cursor.close()  
                
#if __name__ == '__main__':
#    app.run(debug=True)

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1']
    app.run(debug=debug_mode)
    