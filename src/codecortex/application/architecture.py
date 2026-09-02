"""Architecture inference, baseline and drift application service."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from typing import Any
from codecortex.architecture import ArchitectureDriftDetector,ArchitectureFingerprint,ArchitectureInferenceEngine
from codecortex.indexing.incremental_graph import IncrementalGraphIndex
class ArchitectureService:
    def __init__(self,root:Path)->None:self.root=root.expanduser().resolve();self.baseline_path=self.root/".codecortex"/"architecture"/"baseline.json"
    def _graph(self):return IncrementalGraphIndex(self.root).refresh()[0]
    def analyze(self)->dict[str,Any]:return asdict(ArchitectureInferenceEngine().analyze(self._graph()))
    def baseline(self)->dict[str,Any]:
        detector=ArchitectureDriftDetector();current=detector.fingerprint(self._graph());current.save(self.baseline_path);return asdict(current)
    def drift(self)->dict[str,Any]:
        detector=ArchitectureDriftDetector();current=detector.fingerprint(self._graph());baseline=ArchitectureFingerprint.load(self.baseline_path)
        if baseline is None:return {"baseline":None,"current":asdict(current),"drift":None}
        return {"baseline":asdict(baseline),"current":asdict(current),"drift":asdict(detector.compare(baseline,current))}
