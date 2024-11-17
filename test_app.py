import pytest
from app import app  
from app import genetic_algorithm, fitness, initialize_population, select_parents, crossover, mutate
import pytest
import base64
from io import BytesIO
from PIL import Image
import warnings
import pyodbc

@pytest.fixture
def client():
    app.config['TESTING'] = True 
    with app.test_client() as client:
        yield client
########################################## TEST POSITIVOS ##########################################

def test_home_page(client):
    """Prueba para la página de inicio."""
    response = client.get('/')  # Realiza una solicitud GET a la ruta de inicio
    assert response.status_code == 200  # Verifica que la respuesta sea exitosa
    assert b'login' in response.data  # Verifica que el contenido esperado está en la página (cambia 'login' según tu caso)

def test_login(client):
    """Prueba para el endpoint de login."""
    response = client.post('/acceso-login', data={
        'txtEmail': 'test@example.com',
        'txtContrasena': 'password123'
    })
    assert response.status_code == 200  # Verifica el estado de la respuesta
    assert 'Usuario o contraseña incorrecta' in response.data.decode('utf-8')  # Compara el contenido esperado

def test_view_table(client):
    """Prueba para visualizar la tabla."""
    response = client.get('/ver_tabla')
    assert response.status_code == 200
    assert b'<table' in response.data 
    
def test_view_mapa(client):
    """Prueba para visualizar el mapa."""
    response = client.get('/ver_mapa')
    assert response.status_code == 200
    assert b'<div id="map"' in response.data  
    print(response.data.decode('utf-8'))

def test_reporte_distritos(client):
    """Prueba para el reporte de distritos."""
    response = client.get('/reporte_distritos')
    assert response.status_code == 200
    data = response.get_json()
    assert 'distritos' in data
    assert 'cantidades' in data
    
def test_genetic_algorithm():
    """Prueba para el algoritmo genético de optimización de direcciones."""
    import random
    random.seed(42) 

    # Datos de prueba
    direcciones = [
        "Calle Principal 123, Ciudad A",
        "Avenida Secundaria 456, Ciudad B",
        "Calle Tercera 789, Ciudad C",
        "Boulevard Cuarta 101, Ciudad D",
        "Pasaje Quinta 202, Ciudad E"
    ]
    pop_size = 4
    max_generations = 10

    best_solution = genetic_algorithm(pop_size, direcciones, max_generations)

    assert isinstance(best_solution, list), "La mejor solución debe ser una lista."
    assert len(best_solution) == len(direcciones), "La solución debe contener el mismo número de direcciones que la entrada."
    normalized_solution = [direccion.replace(" ", "").lower() for direccion in best_solution]
    normalized_direcciones = [direccion.replace(" ", "").lower() for direccion in direcciones]

    assert set(normalized_solution).issubset(set(normalized_direcciones)), "La solución debe ser un subconjunto válido de las direcciones de entrada."


# Ignorar todos los warnings
warnings.filterwarnings("ignore")

def test_analizar_endpoint(client):
    """Prueba para el endpoint '/analizar' con una imagen cargada desde el archivo."""

    # Cargar una imagen desde el sistema de archivos
    with open('DF03.03.23.jpeg', 'rb') as image_file:
        image_data = image_file.read()
    base64_image = base64.b64encode(image_data).decode('utf-8')
    base64_data = f"data:image/png;base64,{base64_image}"

    # Realizar la solicitud de prueba
    response = client.post('/analizar', data={'base64Data': base64_data})

    # Validar la respuesta
    assert response.status_code == 200, "El endpoint debería responder con un código de estado 200"
    assert b'archivo.csv' in response.data or b'Error' not in response.data, (
        "El endpoint debería generar un archivo CSV correctamente o manejar errores"
    )

########################################## TEST NEGATIVOS ##########################################

def test_agregar_vehiculo_incompleto_data(client):
    """Prueba de agregar vehículo con datos incompletos."""
    response = client.post('/agregar_vehiculo', data={'nombre': '', 'marca': '', 
                                                      'modelo': '', 'placa': '', 'usuarioid': ''})
    assert response.status_code == 302  
  
def test_analizar_imagen_not(client):
    """Prueba negativa para verificar que el sistema rechaza imágenes en formato no permitido (por ejemplo, un archivo GIF)."""
    invalid_image_base64 = "data:image/gif;base64,R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs="
    response = client.post('/analizar', data={'base64Data': invalid_image_base64})
    assert response.status_code == 200  
    assert response.data.decode('utf-8') == "Error: Solo se admiten imágenes en formato JPEG, JPG o PNG"

def test_mapa_error_bd(client, mocker):
    """Prueba negativa para verificar el manejo de errores de la base de datos."""
    mocker.patch('pyodbc.connect', side_effect=pyodbc.Error("Fallo de conexión"))
    response = client.get('/ver_mapa')
    assert response.status_code == 200 
    assert "Error de base de datos" in response.data.decode('utf-8')  

def test_mapa_metodo_post(client):
    """Prueba negativa para verificar que el acceso al mapa con un método HTTP no permitido devuelve un error."""
    response = client.post('/ver_mapa')
    assert response.status_code == 405

def test_mapa_geocoding_error(client, mocker):
    """
    Prueba negativa para verificar que el sistema maneja adecuadamente
    el caso en el que el geocodificador de Google Maps no puede encontrar una dirección.
    """
    mocker.patch('googlemaps.Client.geocode', return_value=[]) 

    response = client.get('/ver_mapa')

    print(response.data.decode('utf-8'))  
    assert response.status_code == 200
    assert "No se encontraron direcciones geocodificadas para mostrar" in response.data.decode('utf-8')

def test_mapa_sin_direcciones(client, mocker):
    """
    Prueba negativa para verificar que el sistema maneja correctamente
    el caso en el que no hay direcciones en la base de datos o el proceso de geocodificación falla.
    """

    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.return_value = [] 
    mock_conn = mocker.MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mocker.patch('pyodbc.connect', return_value=mock_conn)

    mocker.patch('googlemaps.Client.geocode', return_value=[])

    response = client.get('/ver_mapa')

    assert response.status_code == 200
    response_text = response.data.decode('utf-8')
    assert "No se encontraron direcciones para mostrar" in response_text

def test_genetic_algorithm_negativo():
    """Prueba negativa para el algoritmo genético con casos límite y entradas no válidas."""
    import random
    random.seed(42)  
    
    direcciones_vacias = []
    pop_size = 4
    max_generations = 10

    try:
        resultado = genetic_algorithm(pop_size, direcciones_vacias, max_generations)
        assert False, "El algoritmo debería haber fallado con una lista vacía de direcciones."
    except ValueError as e:
        assert str(e) == "La lista de direcciones no puede estar vacía.", "El mensaje de error esperado no coincide."

def test_genetic_algorithm_invalid_direciones():
    direcciones = [123, None, "Calle válida"]
    try:
        resultado = genetic_algorithm(pop_size=4, direcciones=direcciones, max_generations=10)
        assert False, "El algoritmo debería haber fallado con direcciones no válidas."
    except TypeError as e:
        assert "Cada dirección debe ser una cadena de texto." in str(e)