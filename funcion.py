from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient, DocumentField
import json
import csv
from io import BytesIO

def recognize_invoices(imagen):
    endpoint = "https://tesisocr.cognitiveservices.azure.com/"
    key = "71cfd9d5b6374193aa1dad8f7a5efb53"
    model_id = "modelotesis"
    formFile = imagen

    document_analysis_client = DocumentAnalysisClient(
        endpoint=endpoint, credential=AzureKeyCredential(key)
    )

    # Convertir la imagen de PIL a bytes utilizando BytesIO
    image_bytes = BytesIO()
    imagen.save(image_bytes, format='JPEG')
    image_bytes.seek(0)

    poller = document_analysis_client.begin_analyze_document(model_id, image_bytes.read())
    result = poller.result()

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
    with open(jsonarc, 'r') as file:
        data = json.load(file)

    with open("archivo.csv", mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file, delimiter=';')

        # Recorrer los datos y escribir cada fila en el archivo CSV
        for i, row in enumerate(data):
            writer.writerow(row)

