"""Change-impact application service."""
from __future__ import annotations
from typing import Any
from pathlib import Path
from codecortex.indexing.impact import ImpactAnalyzer,ImpactItem
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
class ImpactService:
    def __init__(self,root:Path)->None:self.root=root.expanduser().resolve()
    @staticmethod
    def _item(item:ImpactItem)->dict[str,Any]:return {"node":item.node.model_dump(mode="json"),"depth":item.depth,"via":item.via,"risk":item.risk}
    def analyze(self,query:str)->dict[str,Any]:
        if not query.strip():raise ValueError("impact target is required")
        graph,_=IncrementalGraphIndex(self.root).refresh();report=ImpactAnalyzer(graph).analyze(query)
        return {"target":report.target.model_dump(mode="json"),"risk_score":report.risk_score,"direct":[self._item(x) for x in report.direct],"indirect":[self._item(x) for x in report.indirect],"affected_tests":[self._item(x) for x in report.affected_tests]}
