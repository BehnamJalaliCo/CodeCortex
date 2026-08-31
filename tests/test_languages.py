from pathlib import Path

from codecortex.languages import LanguageRegistry


def test_python_parser_extracts_types_and_signatures() -> None:
    source = """
class Service(BaseService):
    def execute(self, value: Request) -> Response:
        return Response(value)
"""
    registry = LanguageRegistry()
    units = registry.parse(Path("service.py"), source)
    service = next(unit for unit in units if unit.name == "Service")
    execute = next(unit for unit in units if unit.name == "execute")
    assert service.bases == ("BaseService",)
    assert execute.return_type == "Response"
    assert execute.annotations["value"] == "Request"


def test_typescript_structural_parser() -> None:
    source = """
export class AuthService extends BaseService { }
export async function refresh(token: Token): Promise<Result> { return token; }
"""
    units = LanguageRegistry().parse(Path("auth.ts"), source)
    assert any(unit.name == "AuthService" and unit.kind == "class" for unit in units)
    assert any(unit.name == "refresh" and unit.kind == "function" for unit in units)
