"""质量保障路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_current_principal
from ..qa_system import TestCase, TestSuite, SecurityScanResult, PerformanceTest, get_qa_system

router = APIRouter(prefix="/qa", tags=["qa"])


class TestCaseCreate(BaseModel):
    name: str
    test_type: str
    module: str = ""
    description: str = ""
    priority: str = "medium"


class SuiteCreate(BaseModel):
    name: str
    test_cases: list[str] = []


class SecurityScanAdd(BaseModel):
    scan_type: str
    severity: str
    title: str
    description: str = ""
    file_path: str = ""


class PerfTestCreate(BaseModel):
    name: str
    target_url: str = ""
    concurrent_users: int = 10
    duration_seconds: int = 60


@router.post("/cases")
def create_test_case(
    req: TestCaseCreate,
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    case = TestCase(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        test_type=req.test_type,
        module=req.module,
        description=req.description,
        priority=req.priority,
    )
    qa.create_test_case(case)
    return {"id": case.id, "name": case.name}


@router.get("/cases")
def list_test_cases(
    test_type: str | None = None,
    module: str | None = None,
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    cases = qa.list_test_cases(test_type, module)
    return [{"id": c.id, "name": c.name, "test_type": c.test_type, "priority": c.priority} for c in cases]


@router.delete("/cases/{case_id}")
def delete_test_case(
    case_id: str,
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    if qa.delete_test_case(case_id):
        return {"status": "ok"}
    return {"error": "Not found"}


@router.post("/suites")
def create_suite(
    req: SuiteCreate,
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    suite = TestSuite(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        test_cases=req.test_cases,
    )
    qa.create_suite(suite)
    return {"id": suite.id, "name": suite.name}


@router.get("/suites")
def list_suites(
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    return [{"id": s.id, "name": s.name, "status": s.status} for s in qa.list_suites()]


@router.post("/suites/{suite_id}/run")
def run_suite(
    suite_id: str,
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    suite = qa.run_suite(suite_id)
    if not suite:
        return {"error": "Not found"}
    return {"id": suite.id, "status": suite.status, "results": len(suite.results)}


@router.get("/suites/{suite_id}/summary")
def get_suite_summary(
    suite_id: str,
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    return qa.get_suite_summary(suite_id)


@router.post("/security")
def add_security_result(
    req: SecurityScanAdd,
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    result = SecurityScanResult(
        id=str(__import__("uuid").uuid4())[:8],
        scan_type=req.scan_type,
        severity=req.severity,
        title=req.title,
        description=req.description,
        file_path=req.file_path,
    )
    qa.add_security_result(result)
    return {"id": result.id}


@router.get("/security")
def list_security_results(
    severity: str | None = None,
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    results = qa.get_security_results(severity)
    return [{"id": r.id, "title": r.title, "severity": r.severity, "scan_type": r.scan_type} for r in results]


@router.get("/security/summary")
def get_security_summary(
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    return qa.get_security_summary()


@router.post("/performance")
def create_performance_test(
    req: PerfTestCreate,
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    test = PerformanceTest(
        id=str(__import__("uuid").uuid4())[:8],
        name=req.name,
        target_url=req.target_url,
        concurrent_users=req.concurrent_users,
        duration_seconds=req.duration_seconds,
    )
    qa.create_performance_test(test)
    return {"id": test.id, "name": test.name}


@router.get("/performance")
def list_performance_tests(
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    return [{"id": t.id, "name": t.name, "status": t.status} for t in qa.list_performance_tests()]


@router.get("/stats")
def get_stats(
    principal=Depends(get_current_principal),
):
    qa = get_qa_system()
    return qa.get_overall_stats()
