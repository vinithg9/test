import base64
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import threading
import unittest
import zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('conversion_app',ROOT/'server/app.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class ServiceFixture:

 @classmethod
 def setUpClass(cls):
  cls.server=app.Server(('127.0.0.1',0),app.Handler)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close()
 def request(self,path,body=b'',headers=None,method='POST'):
  conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=120)
  conn.request(method,path,body,{'Content-Type':'application/octet-stream',**(headers or {})})
  r=conn.getresponse();result=(r.status,dict(r.getheaders()),r.read());conn.close();return result

class ServiceTests(ServiceFixture, unittest.TestCase):
 def test_health(self):
  code,headers,body=self.request('/api/health',method='GET');self.assertEqual(code,200);self.assertEqual(headers['Cache-Control'],'no-store')
 def test_cross_origin_rejected(self):
  self.assertEqual(self.request('/api/convert/docx-to-pdf',b'x',{'Origin':'https://attacker.example'})[0],403)
 def test_wrong_content_type(self):
  self.assertEqual(self.request('/api/convert/docx-to-pdf',b'x',{'Content-Type':'text/plain'})[0],415)
 def test_empty_and_oversize(self):
  self.assertEqual(self.request('/api/convert/docx-to-pdf')[0],413)
  self.assertEqual(self.request('/api/convert/docx-to-pdf',b'',{'Content-Length':str(26*1024*1024)})[0],413)
 def test_invalid_file(self):
  self.assertEqual(self.request('/api/convert/docx-to-pdf',b'not a zip')[0],422)
  self.assertEqual(self.request('/api/convert/pdf-to-docx',b'not a pdf')[0],422)
 def test_no_source_or_directory_exposure(self):
  for path in ['/server/app.py','/server/requirements.txt','/../README.md','/.git/config']:
   self.assertEqual(self.request(path,method='GET')[0],404)
 def test_busy_rejection(self):
  app.SLOTS.acquire();app.SLOTS.acquire()
  try:self.assertEqual(self.request('/api/convert/docx-to-pdf',b'x')[0],429)
  finally:app.SLOTS.release();app.SLOTS.release()
 def test_secure_mode_fails_closed(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(app.shutil,'which',return_value=None):
   with self.assertRaises(app.ConversionError):app.command_for(Path(tmp),'docx-to-pdf',True)
 def test_sandbox_filesystem_and_network_are_isolated(self):
  if os.environ.get('DOCFLOW_DEV_UNSANDBOXED')=='1':
   self.skipTest('Development renderer test; isolation is verified in CI')
  with tempfile.NamedTemporaryFile(prefix='docflow-private-') as secret, tempfile.TemporaryDirectory() as tmp:
   command=app.command_for(Path(tmp),'docx-to-pdf',True)
   renderer=next(i for i,value in enumerate(command) if value.endswith('/soffice'))
   code="import json,os,socket; s=socket.socket();s.settimeout(2);print(json.dumps({'host_file_visible':os.path.exists("+repr(secret.name)+"),'network_connected':s.connect_ex(('1.1.1.1',443))==0}))"
   result=subprocess.run(command[:renderer]+[sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(json.loads(result.stdout),{'host_file_visible':False,'network_connected':False})
 def test_archive_traversal_and_external_resources(self):
  for bad in ['../escape','word/vbaProject.bin','word/external.rels']:
   with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'input.docx'
    with zipfile.ZipFile(p,'w') as z:
     z.writestr('[Content_Types].xml','x');z.writestr('word/document.xml','x')
     z.writestr(bad,'<Relationships><Relationship TargetMode="External" Type="image" Target="file:///etc/passwd"/></Relationships>')
    with self.assertRaises(app.ConversionError):app.validate_input(p,'.docx')

class RenderingTests(ServiceFixture, unittest.TestCase):
 def test_word_layout_tables_images_and_pagination(self):
  from docx import Document
  from docx.shared import Inches
  from PIL import Image
  import fitz
  with tempfile.TemporaryDirectory() as tmp:
   d=Document();d.add_heading('LAYOUT_WORD_SENTINEL',0);d.add_paragraph('Unicode: café — résumé')
   table=d.add_table(rows=2,cols=2);table.style='Table Grid';table.cell(0,0).text='Table left';table.cell(0,1).text='Table right';table.cell(1,0).text='123';table.cell(1,1).text='456'
   image=Path(tmp)/'image.png';Image.new('RGB',(160,90),(30,120,210)).save(image);d.add_picture(str(image),width=Inches(2));d.add_page_break();d.add_paragraph('SECOND_PAGE_SENTINEL')
   p=Path(tmp)/'input.docx';d.save(p)
   code,headers,body=self.request('/api/convert/docx-to-pdf',p.read_bytes());self.assertEqual(code,200,body)
   pdf=fitz.open(stream=body,filetype='pdf');self.assertEqual(len(pdf),2)
   self.assertIn('LAYOUT_WORD_SENTINEL',pdf[0].get_text());self.assertIn('Table left',pdf[0].get_text());self.assertIn('Table right',pdf[0].get_text());self.assertTrue(pdf[0].get_images());self.assertIn('SECOND_PAGE_SENTINEL',pdf[1].get_text())
 def test_excel_sheets_chart_image_and_unicode(self):
  from openpyxl import Workbook
  from openpyxl.drawing.image import Image as XLImage
  from openpyxl.chart import BarChart,Reference
  from PIL import Image
  import fitz
  with tempfile.TemporaryDirectory() as tmp:
   wb=Workbook();ws=wb.active;ws.title='Report';ws.append(['LAYOUT_EXCEL_SENTINEL','Value']);ws.append(['Sales',42]);ws.append(['Costs',12]);ws.column_dimensions['A'].width=35
   chart=BarChart();chart.add_data(Reference(ws,min_col=2,min_row=1,max_row=3),titles_from_data=True);ws.add_chart(chart,'A6')
   image=Path(tmp)/'image.png';Image.new('RGB',(100,50),(40,150,50)).save(image);ws.add_image(XLImage(io.BytesIO(image.read_bytes())),'E1');ws.print_options.horizontalCentered=True
   ws.page_setup.orientation='landscape';ws.sheet_properties.pageSetUpPr.fitToPage=True;ws.page_setup.fitToWidth=1
   other=wb.create_sheet('Other');other['A1']='SECOND_SHEET_SENTINEL';other.column_dimensions['A'].width=40
   p=Path(tmp)/'input.xlsx';wb.save(p)
   code,headers,body=self.request('/api/convert/xlsx-to-pdf',p.read_bytes());self.assertEqual(code,200,body)
   pdf=fitz.open(stream=body,filetype='pdf');text=''.join(p.get_text() for p in pdf)
   self.assertIn('LAYOUT_EXCEL_SENTINEL',text);self.assertIn('SECOND_SHEET_SENTINEL',text);self.assertTrue(any(p.get_images() for p in pdf));self.assertGreaterEqual(len(pdf),2)
 def test_pdf_to_word_reconstructs_table_and_image(self):
  from docx import Document
  from docx.shared import Inches
  from PIL import Image
  with tempfile.TemporaryDirectory() as tmp:
   d=Document();d.add_heading('PDF_LAYOUT_SENTINEL',0);table=d.add_table(rows=2,cols=2);table.style='Table Grid';table.cell(0,0).text='Alpha';table.cell(0,1).text='Beta';table.cell(1,0).text='123';table.cell(1,1).text='456'
   image=Path(tmp)/'im.png';Image.new('RGB',(160,90),(120,40,90)).save(image);d.add_picture(str(image),width=Inches(2));p=Path(tmp)/'input.docx';d.save(p)
   code,_,pdf=self.request('/api/convert/docx-to-pdf',p.read_bytes());self.assertEqual(code,200,pdf)
   code,_,body=self.request('/api/convert/pdf-to-docx',pdf);self.assertEqual(code,200,body)
   result=Document(io.BytesIO(body));self.assertTrue(result.tables);self.assertGreater(len(result.inline_shapes),0);self.assertIn('PDF_LAYOUT_SENTINEL',' '.join(p.text for p in result.paragraphs))

if __name__=='__main__':unittest.main()
