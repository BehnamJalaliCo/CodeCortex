"""Transport-neutral product service used by CLI, MCP and HTTP adapters."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, ConfigDict
from codecortex.git_intelligence import GitIntelligence
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
from codecortex.memory.knowledge import ProjectKnowledgeExtractor
if TYPE_CHECKING:
    from codecortex.runtime import CortexRuntime

class ProjectOverview(BaseModel):
    model_config=ConfigDict(frozen=True)
    project_root:str; health:dict[str,bool]; active_backends:tuple[str,...]

class CortexApplicationService:
    def __init__(self,runtime:"CortexRuntime")->None:self.runtime=runtime
    @property
    def project_root(self)->str:return str(self.runtime.config.project_root)
    def _graph(self):return IncrementalGraphIndex(self.runtime.config.project_root).refresh()[0]
    async def overview(self)->ProjectOverview:return ProjectOverview(project_root=self.project_root,health=await self.runtime.gateway.health(),active_backends=self.runtime.active_backends)
    async def repository_dashboard(self)->dict[str,Any]:
        root=self.runtime.config.project_root; graph,stats=IncrementalGraphIndex(root).refresh(); git=GitIntelligence(root).analyze(300); knowledge=ProjectKnowledgeExtractor(root).extract(); counts=graph.counts(); symbols=sum(v for k,v in counts.items() if k not in {"file","module","reference"})
        return {"repository":{"root":str(root),"languages":list(knowledge.languages)},"index":{"tracked":stats.index.tracked,"added":len(stats.index.added),"changed":len(stats.index.changed),"removed":len(stats.index.removed),"files_reparsed":stats.files_reparsed,"full_rebuild":stats.full_rebuild,"duration_ms":stats.index.duration_ms},"graph":{"nodes":len(graph.nodes),"edges":len(graph.edges),"symbols":symbols,"counts":counts},"git":{"commits":git.commits,"hot_files":[x.path for x in git.hot_files[:8]]},"runtime":{"health":await self.runtime.gateway.health(),"active_backends":list(self.runtime.active_backends)}}
    def repository_files(self,*,limit:int=500)->dict[str,Any]:
        graph=self._graph(); rows=[n for n in graph.nodes if n.kind=="file"][:min(5000,max(1,limit))]
        return {"files":[{"id":n.id,"name":n.name,"path":n.path,"language":n.metadata.get("language")} for n in rows],"total":sum(n.kind=="file" for n in graph.nodes)}
    def repository_symbols(self,*,query:str="",limit:int=200)->dict[str,Any]:
        graph=self._graph(); candidates=graph.search(query,limit) if query.strip() else graph.nodes; rows=[n for n in candidates if n.kind not in {"file","module","reference"}][:min(1000,max(1,limit))]
        return {"symbols":[{"id":n.id,"name":n.name,"kind":n.kind,"path":n.path,"line":n.line,"language":n.metadata.get("language"),"container":n.metadata.get("container")} for n in rows],"total":sum(n.kind not in {"file","module","reference"} for n in graph.nodes)}
    def repository_graph(self,*,query:str="",depth:int=1,relation:str="",limit:int=400)->dict[str,Any]:
        graph=self._graph(); bounded_depth=min(4,max(0,depth)); bounded_limit=min(1000,max(1,limit)); seed=graph.search(query,8) if query.strip() else graph.nodes[:min(60,bounded_limit)]; selected={n.id for n in seed}; eligible=[e for e in graph.edges if not relation or e.kind==relation]
        for _ in range(bounded_depth):
            frontier=set(selected)
            for edge in eligible:
                if edge.source in frontier or edge.target in frontier:selected.add(edge.source);selected.add(edge.target)
                if len(selected)>=bounded_limit:break
            if len(selected)>=bounded_limit:break
        nodes=[n for n in graph.nodes if n.id in selected][:bounded_limit]; ids={n.id for n in nodes}; edges=[e for e in eligible if e.source in ids and e.target in ids][:bounded_limit*4]
        return {"nodes":[{"id":n.id,"name":n.name,"kind":n.kind,"path":n.path,"line":n.line,"metadata":n.metadata} for n in nodes],"edges":[{"source":e.source,"target":e.target,"kind":e.kind,"confidence":e.metadata.get("confidence"),"metadata":e.metadata} for e in edges]}
    def route(self,query:str)->dict[str,Any]:return self.runtime.gateway.route(query,self.project_root).model_dump(mode="json")
    async def query(self,query:str)->dict[str,Any]:return (await self.runtime.gateway.query(query,self.project_root)).model_dump(mode="json")
    async def health(self)->dict[str,bool]:return await self.runtime.gateway.health()
    async def remember(self,key:str,value:str,namespace:str="project")->None:await self.runtime.gateway.remember(key,value,namespace)
