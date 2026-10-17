import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel,Field
from providers import DemoEmbedder,OpenAIProvider,ProviderError
from ingestion import extract,MAX_BYTES
from store import Store

ROOT=Path(__file__).parent

class Question(BaseModel):
    question: str = Field(min_length=3,max_length=1500)
    k: int = Field(default=4,ge=1,le=6)


def create_app(storage=None,mode=None,provider=None):
    mode=mode or os.getenv('RAG_MODE','demo')
    if mode not in {'demo','openai'}: raise ValueError('RAG_MODE invalide')
    embedder=provider or (DemoEmbedder() if mode=='demo' else OpenAIProvider(os.getenv('OPENAI_API_KEY',''),os.getenv('EMBEDDING_MODEL','text-embedding-3-small'),os.getenv('OPENAI_MODEL','gpt-4.1-mini')))
    threshold=float(os.getenv('MIN_SCORE','0.20'))
    if not 0<=threshold<=1: raise ValueError('MIN_SCORE doit être compris entre 0 et 1')
    @asynccontextmanager
    async def lifespan(app):
        app.state.store=Store(storage or os.getenv('RAG_STORAGE',str(ROOT/'storage')),embedder)
        yield
        app.state.store.close()
    app=FastAPI(title='Documind RAG',version='1.0.0',lifespan=lifespan)
    app.mount('/assets',StaticFiles(directory=ROOT/'web'),name='assets')
    @app.get('/',include_in_schema=False)
    def home(): return FileResponse(ROOT/'web/index.html')
    @app.get('/api/status')
    def status():
        return dict(mode=mode,embedding=embedder.signature,generation=mode=='openai',documents=app.state.store.documents())
    @app.post('/api/documents')
    async def upload(file:UploadFile):
        data=bytearray()
        try:
            while part:=await file.read(65536):
                data.extend(part)
                if len(data)>MAX_BYTES: raise HTTPException(413,'Fichier limité à 10 Mo')
            name,doc_id,chunks=await run_in_threadpool(extract,file.filename or 'document.txt',bytes(data))
            return await run_in_threadpool(app.state.store.ingest,name,doc_id,chunks)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        except ProviderError as exc: raise HTTPException(502,str(exc)) from exc
        finally: await file.close()
    @app.delete('/api/documents/{doc_id}')
    def delete(doc_id:str):
        if not app.state.store.delete(doc_id): raise HTTPException(404,'Document introuvable')
        return dict(status='deleted')
    @app.post('/api/ask')
    def ask(body:Question):
        question=body.question.strip()
        if len(question)<3: raise HTTPException(422,'Question trop courte')
        try:
            sources=app.state.store.search(question,body.k,threshold)
            if not sources: return dict(answer='Je ne trouve pas de passage suffisamment proche de cette question. Reformulez-la ou ajoutez un document.',sources=[],mode=mode,generated=False)
            if mode=='demo':
                answer='Mode démonstration : voici les passages retrouvés. Aucune réponse de modèle de langage n’a été générée.'
            else: answer=embedder.answer(question,sources)
            return dict(answer=answer,sources=sources,mode=mode,generated=mode=='openai')
        except ProviderError as exc: raise HTTPException(502,str(exc)) from exc
    return app

app=create_app()
