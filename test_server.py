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
        with patch('server.ollama',side_effect=[{'models':[{'name':'test','digest':'abc'}]},{'capabilities':['vision']},{'message':{'content':json.dumps(result)}}]) as backend:
            report=server.analyze({'images':[png()],'privacy_confirmed':True,'model':'test'})
            self.assertEqual({k:report[k] for k in result},result)
            self.assertFalse(report['provenance']['clinically_validated'])
            self.assertEqual(report['provenance']['model_digest'],'abc')
            messages=backend.call_args.args[1]['messages']
            self.assertEqual(messages[0]['role'],'system')
            self.assertEqual(len(messages[1]['images']),1)

    def test_incomplete_model_output(self):
        with patch('server.ollama',side_effect=[{'models':[{'name':'test'}]},{'capabilities':['vision']},{'message':{'content':'{}'}}]):
            with self.assertRaises(ValueError):server.analyze({'images':[png()],'privacy_confirmed':True,'model':'test'})

    def test_nonvision_rejected_before_inference(self):
        with patch('server.ollama',side_effect=[{'models':[{'name':'text'}]},{'capabilities':['completion']}]) as backend:
            with self.assertRaises(ValueError):server.analyze({'images':[png()],'privacy_confirmed':True,'model':'text'})
            self.assertEqual(backend.call_count,2)

    def test_invalid_frame(self):
        for frame in [-1,True,1]:
            with self.assertRaises(ValueError):server.convert_image(png(),frame)

    def test_dicom_selected_frame_and_bounds(self):
        meta=FileMetaDataset();meta.TransferSyntaxUID=ExplicitVRLittleEndian
        meta.MediaStorageSOPClassUID=generate_uid();meta.MediaStorageSOPInstanceUID=generate_uid()
        ds=FileDataset(None,{},file_meta=meta,preamble=b'\0'*128)
        ds.Modality='US';ds.Rows=8;ds.Columns=8;ds.SamplesPerPixel=1;ds.NumberOfFrames=2
        ds.PhotometricInterpretation='MONOCHROME2';ds.BitsAllocated=8;ds.BitsStored=8;ds.HighBit=7;ds.PixelRepresentation=0
        ds.PixelData=np.stack([np.zeros((8,8),np.uint8),np.arange(64,dtype=np.uint8).reshape(8,8)]).tobytes()
        def encoded():
            buf=io.BytesIO();ds.save_as(buf,enforce_file_format=True)
            return base64.b64encode(buf.getvalue()).decode()
        first=server.convert_image(encoded(),0);second=server.convert_image(encoded(),1)
        self.assertEqual(second['metadata']['selected_frame'],1)
        self.assertNotEqual(first['metadata']['sha256_png'],second['metadata']['sha256_png'])
        with self.assertRaises(ValueError):server.convert_image(encoded(),2)
        ds.Rows=65535;ds.Columns=65535
        with patch('pydicom.pixels.pixel_array') as decode:
            with self.assertRaises(ValueError):server.convert_image(encoded())
            decode.assert_not_called()

if __name__=='__main__':unittest.main()
