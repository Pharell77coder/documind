import io
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from main import create_app
from ingestion import extract
from providers import DemoEmbedder,OpenAIProvider,ProviderError

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(storage=tmp_path/'db',mode='demo')) as c: yield c

def upload(client,name='cours.txt',data='Les sauvegardes PostgreSQL sont conservées pendant trente jours. Les restaurations sont testées chaque mois.'.encode()):
    return client.post('/api/documents',files={'file':(name,data)})

def test_full_flow_and_duplicate(client):
    assert client.get('/').status_code==200
    assert client.get('/assets/app.js').status_code==200
    result=upload(client).json(); assert result['status']=='indexed'
    assert upload(client,name='autre.txt').json()['status']=='duplicate'
    docs=client.get('/api/status').json()['documents']; assert len(docs)==1
    answer=client.post('/api/ask',json={'question':'Quelle est la conservation des sauvegardes PostgreSQL ?'}).json()
    assert not answer['generated'] and 'trente jours' in answer['sources'][0]['text']
    assert answer['sources'][0]['page']==1 and answer['sources'][0]['citation']=='S1'
    assert client.delete('/api/documents/'+result['id']).status_code==200
    assert client.get('/api/status').json()['documents']==[]
    assert client.delete('/api/documents/'+result['id']).status_code==404

def test_empty_and_unrelated(client):
    assert client.post('/api/ask',json={'question':'Bonjour ?'}).json()['sources']==[]
    upload(client)
    assert client.post('/api/ask',json={'question':'astronomie galaxies telescopes'}).json()['sources']==[]
    assert client.post('/api/ask',json={'question':'  '}).status_code==422
    assert client.post('/api/ask',json={'question':'test','k':99}).status_code==422

@pytest.mark.parametrize('name,data',[('x.exe',b'test'),('x.txt',b''),('x.txt',b'\xff\xff'),('x.pdf',b'not a pdf')])
def test_invalid_upload(client,name,data):
    assert upload(client,name,data).status_code==422

def test_chunk_overlap_and_filename():
    name,_,chunks=extract('../../cours.md',(' '.join('mot'+str(i) for i in range(400))).encode())
    assert name=='cours.md' and len(chunks)==3
    assert chunks[0]['text'].split()[-30:]==chunks[1]['text'].split()[:30]

def test_pdf_without_text(client):
    writer=PdfWriter();writer.add_blank_page(width=200,height=200);buf=io.BytesIO();writer.write(buf)
    r=upload(client,'scan.pdf',buf.getvalue())
    assert r.status_code==422 and 'OCR' in r.json()['detail']

def test_persistence_and_index_separation(tmp_path):
    path=tmp_path/'db'
    with TestClient(create_app(storage=path,mode='demo')) as c: upload(c)
    with TestClient(create_app(storage=path,mode='demo')) as c:
        assert len(c.get('/api/status').json()['documents'])==1
    class Other(DemoEmbedder): signature='different-model'
    with TestClient(create_app(storage=path,mode='demo',provider=Other())) as c:
        assert c.get('/api/status').json()['documents']==[]

def test_openai_contract_without_network(monkeypatch):
    p=OpenAIProvider('fake-key','text-embedding-3-small','gpt-4.1-mini')
    calls=[]
    def post(url,**kwargs):
        calls.append(kwargs['json'])
        if url.endswith('/embeddings'):
            return httpx.Response(200,json={'data':[{'index':0,'embedding':[0.01]*1536}]},request=httpx.Request('POST',url))
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'Trente jours [S1].'}]}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx,'post',post)
    assert len(p.embed(['texte'])[0])==1536
    assert p.answer('Question',[dict(citation='S1',filename='cours',page=1,text='trente jours')])=='Trente jours [S1].'
    assert calls[-1]['store'] is False and calls[0]['dimensions']==1536
    assert 'fake-key' not in str(calls)

def test_bad_citations_and_provider_failure(monkeypatch):
    p=OpenAIProvider('fake-key','text-embedding-3-small','gpt-4.1-mini')
    monkeypatch.setattr(p,'post',lambda *args:dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text='Inventé [S99]')])]))
    with pytest.raises(ProviderError,match='références'): p.answer('Q',[dict(citation='S1',filename='cours',page=1,text='Source')])

def test_generation_path_with_fake_provider(tmp_path):
    class Fake(DemoEmbedder):
        def answer(self,question,sources):return 'Trente jours [S1].'
    with TestClient(create_app(storage=tmp_path/'db',mode='openai',provider=Fake())) as c:
        upload(c)
        r=c.post('/api/ask',json={'question':'conservation sauvegardes PostgreSQL'}).json()
        assert r['generated'] and r['answer']=='Trente jours [S1].'

def test_text_pdf_and_page_numbers(client):
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    writer=PdfWriter()
    for content in ['Premiere page : cours.', 'Deuxieme page : sauvegardes PostgreSQL pendant trente jours.']:
        page=writer.add_blank_page(width=595,height=842)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 40 700 Td ('+content+') Tj ET').encode())
        page[NameObject('/Contents')]=writer._add_object(stream)
    buf=io.BytesIO();writer.write(buf)
    r=upload(client,'cours.pdf',buf.getvalue())
    assert r.status_code==200 and r.json()['chunks']==2
    answer=client.post('/api/ask',json={'question':'sauvegardes PostgreSQL trente jours'}).json()
    assert answer['sources'][0]['page']==2
