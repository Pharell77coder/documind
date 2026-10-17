import hashlib
import threading
import uuid
from pathlib import Path
from qdrant_client import QdrantClient, models

class Store:
    def __init__(self,path,embedder):
        Path(path).mkdir(parents=True,exist_ok=True)
        self.client=QdrantClient(path=str(path)); self.embedder=embedder
        self.lock=threading.RLock()
        self.collection='docs_'+hashlib.sha256((embedder.signature+':chunk180overlap30-v1').encode()).hexdigest()[:20]
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(self.collection,vectors_config=models.VectorParams(size=embedder.dimensions,distance=models.Distance.COSINE))
    def close(self): self.client.close()
    def documents(self):
        with self.lock:
            offset=None; docs={}
            while True:
                rows,offset=self.client.scroll(self.collection,limit=256,offset=offset,with_vectors=False,with_payload=['doc_id','filename','page'])
                for row in rows:
                    p=row.payload
                    d=docs.setdefault(p['doc_id'],dict(id=p['doc_id'],filename=p['filename'],chunks=0))
                    d['chunks']+=1
                if offset is None: break
            return list(docs.values())
    def ingest(self,name,doc_id,chunks):
        with self.lock:
            docs=self.documents()
            if any(d['id']==doc_id for d in docs): return dict(status='duplicate',id=doc_id,chunks=0)
            if len(docs)>=100 or sum(d['chunks'] for d in docs)+len(chunks)>10000:
                raise ValueError("Capacité de démonstration atteinte : 100 documents ou 10 000 passages")
            vectors=self.embedder.embed([c['text'] for c in chunks])
            points=[models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL,f'{doc_id}:{c["chunk"]}')),
                vector=v,payload=dict(**c,doc_id=doc_id,filename=name)) for c,v in zip(chunks,vectors)]
            if len(points)!=len(chunks): raise ValueError("Nombre d'embeddings incorrect")
            self.client.upsert(self.collection,points=points,wait=True)
            return dict(status='indexed',id=doc_id,chunks=len(chunks))
    def delete(self,doc_id):
        with self.lock:
            if not any(d['id']==doc_id for d in self.documents()): return False
            self.client.delete(self.collection,models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(key='doc_id',match=models.MatchValue(value=doc_id))])),wait=True)
            return True
    def search(self,question,k,threshold):
        with self.lock:
            if self.client.count(self.collection).count==0: return []
            hits=self.client.query_points(self.collection,query=self.embedder.embed([question])[0],limit=k,score_threshold=threshold,with_payload=True).points
            return [dict(**h.payload,score=round(h.score,6),citation=f'S{i+1}') for i,h in enumerate(hits)]
