from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient, DocumentField
import json
import csv
from io import BytesIO
import database as db

def recognize_invoices(imagen):
    endpoint = db.endpoint
    keyocr = db.keyocr
    modelid = db.modelid
    
    formFile = imagen

    document_analysis_client = DocumentAnalysisClient(
        endpoint=endpoint, credential=AzureKeyCredential(keyocr)
    )
    try:
        image_bytes = BytesIO()
        imagen.save(image_bytes, format='JPEG')
        image_bytes.seek(0)
    except Exception as e:
        print(f"Error al procesar la imagen: {e}")
        return []
    
    try:
        poller = document_analysis_client.begin_analyze_document(modelid, image_bytes.read())
        result = poller.result()
    except Exception as e:
        print(f"Error al analizar el documento: {e}")
        return []
    
    tabla_datos = []

    for table in result.tables:
        for i, cell in enumerate(table.cells):
            row_index = cell.row_index
            column_index = cell.column_index
            content = cell.content

            # Asegurarse de que la lista tenga suficientes elementos para contener la fila
            if len(tabla_datos) <= row_index:
                tabla_datos.extend([[] for _ in range(row_index - len(tabla_datos) + 1)])

            # Asegurarse de que la lista tenga suficientes elementos para contener la columna
            if len(tabla_datos[row_index]) <= column_index:
                tabla_datos[row_index].extend([''] * (column_index - len(tabla_datos[row_index]) + 1))

            tabla_datos[row_index][column_index] = content

    return tabla_datos

def guardararchivocsv(jsonarc):
    try:
        with open(jsonarc, 'r') as file:
            data = json.load(file)
    except Exception as e:
        print(f"Error al leer el archivo JSON: {e}")
        return
    
    try:
        with open("archivo.csv", mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file, delimiter=';')

            # Recorrer los datos y escribir cada fila en el archivo CSV
            for i, row in enumerate(data):
                writer.writerow(row)
    except Exception as e:
        print(f"Error al escribir el archivo CSV: {e}")