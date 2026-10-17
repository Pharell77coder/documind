import hashlib
import io
from pathlib import PurePosixPath
from pypdf import PdfReader

MAX_BYTES=10*1024*1024
MAX_CHUNKS=400

def extract(name,data):
    name=PurePosixPath(name.replace("\\","/")).name[:160]
    suffix=PurePosixPath(name).suffix.lower()
    if suffix not in {'.pdf','.txt','.md'}: raise ValueError("Formats acceptés : PDF, TXT, MD")
    if not data or len(data)>MAX_BYTES: raise ValueError("Fichier vide ou supérieur à 10 Mo")
    pages=[]
    if suffix=='.pdf':
        try:
            reader=PdfReader(io.BytesIO(data))
            if reader.is_encrypted: raise ValueError("PDF chiffré non pris en charge")
            if len(reader.pages)>100: raise ValueError("PDF limité à 100 pages")
            pages=[(i+1,page.extract_text() or '') for i,page in enumerate(reader.pages)]
        except ValueError: raise
        except Exception as exc: raise ValueError("PDF illisible ou non pris en charge") from exc
    else:
        try: pages=[(1,data.decode('utf-8-sig'))]
        except UnicodeDecodeError as exc: raise ValueError("Le texte doit être encodé en UTF-8") from exc
    chunks=[]
    for page,text in pages:
        words=text.replace('\x00',' ').split()
        for start in range(0,len(words),150):
            chunk=' '.join(words[start:start+180])
            if len(chunk)>2400: raise ValueError("Passage trop long : reformatez le document")
            if chunk:
                chunks.append(dict(page=page,text=chunk,chunk=len(chunks)+1))
            if len(chunks)>MAX_CHUNKS: raise ValueError("Document limité à 400 passages")
            if start+180>=len(words): break
    if not chunks: raise ValueError("Aucun texte extractible : les PDF scannés nécessitent un OCR préalable")
    return name,hashlib.sha256(data).hexdigest(),chunks
