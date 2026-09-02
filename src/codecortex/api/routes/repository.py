"""Repository explorer HTTP routes."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel,Field
from codecortex.application.context_lab import ContextLabService
from codecortex.application.impact import ImpactService
from codecortex.application.search import RepositorySearchService
from codecortex.application.service import CortexApplicationService
from codecortex.application.traces import TraceExplorerService
class QueryRequest(BaseModel):query:str=Field(min_length=1,max_length=12000)
class SearchRequest(QueryRequest):limit:int=Field(default=20,ge=1,le=100)
class ContextRequest(QueryRequest):budget:int=Field(default=32000,ge=128)
def mount_repository_routes(app:Any,prefix:str,database:Any,runtimes:Any,principal:Any)->None:
    from fastapi import Depends,HTTPException
    def record(repository_id:str):
        item=database.repository(repository_id)
        if item is None:raise HTTPException(status_code=404,detail="repository not found")
        return item
    def runtime(repository_id:str):return runtimes.get(record(repository_id).root)
    def service(repository_id:str)->CortexApplicationService:return CortexApplicationService(runtime(repository_id))
    @app.get(f"{prefix}/repositories/{{repository_id}}/files")
    def files(repository_id:str,limit:int=500,_actor:str=Depends(principal))->dict[str,Any]:return service(repository_id).repository_files(limit=limit)
    @app.get(f"{prefix}/repositories/{{repository_id}}/symbols")
    def symbols(repository_id:str,query:str="",limit:int=200,_actor:str=Depends(principal))->dict[str,Any]:return service(repository_id).repository_symbols(query=query,limit=limit)
    @app.get(f"{prefix}/repositories/{{repository_id}}/graph")
    def graph(repository_id:str,query:str="",depth:int=1,relation:str="",limit:int=400,_actor:str=Depends(principal))->dict[str,Any]:return service(repository_id).repository_graph(query=query,depth=depth,relation=relation,limit=limit)
    @app.post(f"{prefix}/repositories/{{repository_id}}/search")
    def search(repository_id:str,payload:SearchRequest,_actor:str=Depends(principal))->dict[str,Any]:
        try:return RepositorySearchService(runtime(repository_id).config.project_root).search(payload.query,payload.limit)
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    @app.post(f"{prefix}/repositories/{{repository_id}}/context")
    async def context(repository_id:str,payload:ContextRequest,_actor:str=Depends(principal))->dict[str,Any]:
        try:return await ContextLabService(runtime(repository_id)).build(payload.query,payload.budget)
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    @app.post(f"{prefix}/repositories/{{repository_id}}/impact")
    def impact(repository_id:str,payload:QueryRequest,_actor:str=Depends(principal))->dict[str,Any]:
        try:return ImpactService(runtime(repository_id).config.project_root).analyze(payload.query)
        except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc)) from exc
    @app.post(f"{prefix}/repositories/{{repository_id}}/route")
    def route(repository_id:str,payload:QueryRequest,_actor:str=Depends(principal))->dict[str,Any]:
        plan=service(repository_id).route(payload.query);rows=plan.get("scores",[])
        return {"kind":plan.get("request_kind","unknown"),"selected":plan.get("selected",[]),"context_budget":plan.get("context_budget",0),"scores":{str(r.get("capability")):float(r.get("score",0)) for r in rows if isinstance(r,dict)},"reasons":{str(r.get("capability")):str(r.get("reason","")) for r in rows if isinstance(r,dict)}}
    @app.get(f"{prefix}/repositories/{{repository_id}}/traces")
    def traces(repository_id:str,limit:int=50,_actor:str=Depends(principal))->dict[str,Any]:return TraceExplorerService(runtime(repository_id)).recent(limit)
    @app.get(f"{prefix}/repositories/{{repository_id}}/traces/{{trace_id}}")
    def trace_detail(repository_id:str,trace_id:str,_actor:str=Depends(principal))->dict[str,Any]:
        try:return TraceExplorerService(runtime(repository_id)).detail(trace_id)
        except KeyError as exc:raise HTTPException(status_code=404,detail="trace not found") from exc
