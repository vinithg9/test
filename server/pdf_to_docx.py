import sys
from pdf2docx import Converter
import fitz
source,target=sys.argv[1:]
with fitz.open(source) as pdf:
    if pdf.needs_pass:
        sys.exit(5)
    if len(pdf)>200:
        sys.exit(6)
    if not any(page.get_text().strip() for page in pdf):
        sys.exit(4)
converter=Converter(source)
try:
    converter.convert(target,multi_processing=False)
finally:
    converter.close()
