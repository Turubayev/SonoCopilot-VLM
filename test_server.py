import base64
import io
import json
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
import server

def png():
    buf=io.BytesIO(); Image.new('RGB',(64,48)).save(buf,format='PNG')
    return base64.b64encode(buf.getvalue()).decode()

class Tests(unittest.TestCase):
    def test_png(self):
        result=server.convert_image(png())
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(result['image']))).size,(64,48))

    def test_corrupt_image(self):
        with self.assertRaises(Exception): server.convert_image(base64.b64encode(b'broken').decode())

    def test_dicom_strips_patient_tags(self):
        meta=FileMetaDataset();meta.TransferSyntaxUID=ExplicitVRLittleEndian
        meta.MediaStorageSOPClassUID=generate_uid();meta.MediaStorageSOPInstanceUID=generate_uid()
        ds=FileDataset(None,{},file_meta=meta,preamble=b'\0'*128)
        ds.Modality='US';ds.PatientName='PRIVATE';ds.PatientID='SECRET'
        ds.Rows=8;ds.Columns=8;ds.SamplesPerPixel=1;ds.PhotometricInterpretation='MONOCHROME2'
        ds.BitsAllocated=8;ds.BitsStored=8;ds.HighBit=7;ds.PixelRepresentation=0
        ds.PixelData=np.arange(64,dtype=np.uint8).tobytes()
        buf=io.BytesIO();ds.save_as(buf,enforce_file_format=True)
        result=server.convert_image(base64.b64encode(buf.getvalue()).decode())
        self.assertEqual(result['metadata']['modality'],'US')
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('SECRET',json.dumps(result))

    def test_analysis_requires_privacy(self):
        with self.assertRaises(ValueError):server.analyze({'images':[png()]})

    def test_analysis_model_response(self):
        result={'description':'Описание','conclusion':'Черновик','limitations':'Ограничения'}
        with patch('server.ollama',side_effect=[{'models':[{'name':'test'}]},{'message':{'content':json.dumps(result)}}]) as backend:
            self.assertEqual(server.analyze({'images':[png()],'privacy_confirmed':True,'model':'test'}),result)
            self.assertEqual(len(backend.call_args.args[1]['messages'][0]['images']),1)

    def test_incomplete_model_output(self):
        with patch('server.ollama',side_effect=[{'models':[{'name':'test'}]},{'message':{'content':'{}'}}]):
            with self.assertRaises(ValueError):server.analyze({'images':[png()],'privacy_confirmed':True,'model':'test'})

if __name__=='__main__':unittest.main()
