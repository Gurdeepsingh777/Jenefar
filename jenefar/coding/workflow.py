from __future__ import annotations
from dataclasses import dataclass
from typing import Any
@dataclass
class CodingWorkflowResult:
    status:str; path:str; diff:str=""; validation:dict[str,Any]|None=None; tests:dict[str,Any]|None=None; backup:str=""
class CodingWorkflow:
    """Safe inspect -> backup -> edit -> validate -> test workflow."""
    def __init__(self,workspace): self.workspace=workspace
    def apply(self,path,content,*,run_tests=True,test_path=None):
        if not str(path).lower().endswith(".py"): raise ValueError("CodingWorkflow currently writes Python files only.")
        result=self.workspace.edit_file(path,content); validation=self.workspace.validate_python(path)
        if not validation.get("valid"): return CodingWorkflowResult("validation_failed",path,result.get("diff",""),validation,backup=result.get("backup",""))
        tests=None
        if run_tests:
            tests=self.workspace.run_pytest(test_path or str(self.workspace.policy.roots[0]))
            if not tests.get("passed"): return CodingWorkflowResult("tests_failed",path,result.get("diff",""),validation,tests,result.get("backup",""))
        return CodingWorkflowResult("completed",path,result.get("diff",""),validation,tests,result.get("backup",""))
