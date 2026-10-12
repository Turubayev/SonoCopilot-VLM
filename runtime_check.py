"""Synthetic-only check run inside the frozen EXE; never reads clinical files."""
import base64
import io
from pathlib import Path


def check_runtime(output):
    import numpy as np
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, JPEG2000Lossless, generate_uid
    from PIL import Image
    from server import convert_image
    from report_export import make_pdf

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    buffer = io.BytesIO()
    Image.new('RGB', (64, 48), '#476465').save(buffer, format='PNG')
    converted = convert_image(base64.b64encode(buffer.getvalue()).decode())
    result['png_decode'] = converted['metadata']['width'] == 64
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = generate_uid()
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset(None, {}, file_meta=meta, preamble=b'\0'*128)
    ds.Modality = 'US'
    ds.Rows = ds.Columns = 64
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = np.arange(4096, dtype=np.uint8).tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    converted = convert_image(base64.b64encode(buffer.getvalue()).decode())
    result['dicom_decode'] = converted['metadata']['modality'] == 'US'
    ds.compress(JPEG2000Lossless, encoding_plugin='pylibjpeg')
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    converted = convert_image(base64.b64encode(buffer.getvalue()).decode())
    result['jpeg2000_decode'] = converted['metadata']['width'] == 64
    data = {'organ': 'Тестовое исследование', 'age': '30', 'description':
            'Искусственные данные для проверки приложения. Это не медицинское заключение.',
            'conclusion': 'Тест экспорта PDF. Анализ пациента не выполнялся.',
            'limitations': 'Тестовая запись', 'observations': 'Проверка русских букв: УЗИ, ё.',
            'doctor': 'Тест', 'status': 'Черновик', 'created_at': '2026-10-12',
            'provenance': {'provider': 'manual'}}
    pdf = make_pdf(data)
    (output / 'synthetic-report.pdf').write_bytes(pdf)
    result['pdf_export'] = pdf.startswith(b'%PDF-') and len(pdf) > 10000
    return result
