"""Repository explorer HTTP routes."""
from __future__ import annotations
from typing import Any
from codecortex.application.service import CortexApplicationService

def mount_repository_routes(app:Any,prefix:str,database:Any,runtimes:Any,principal:Any)->None:
    from fastapi import Depends,HTTPException
    def service(repository_id:str)->CortexApplicationService:
        item=database.repository(repository_id)
        if item is None:raise HTTPException(status_code=404,detail="repository not found")
        return CortexApplicationService(runtimes.get(item.root))
    @app.get(f"{prefix}/repositories/{{repository_id}}/files")
    def files(repository_id:str,limit:int=500,_actor:str=Depends(principal))->dict[str,Any]:return service(repository_id).repository_files(limit=limit)
    @app.get(f"{prefix}/repositories/{{repository_id}}/symbols")
    def symbols(repository_id:str,query:str="",limit:int=200,_actor:str=Depends(principal))->dict[str,Any]:return service(repository_id).repository_symbols(query=query,limit=limit)
    @app.get(f"{prefix}/repositories/{{repository_id}}/graph")
    def graph(repository_id:str,query:str="",depth:int=1,relation:str="",limit:int=400,_actor:str=Depends(principal))->dict[str,Any]:return service(repository_id).repository_graph(query=query,depth=depth,relation=relation,limit=limit)
