from codecortex.memory.knowledge import ProjectKnowledgeExtractor


def test_project_knowledge_detects_stack(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts='-q'\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    service = tmp_path / "services"
    service.mkdir()
    (service / "users.py").write_text("class UserService: pass\n", encoding="utf-8")

    knowledge = ProjectKnowledgeExtractor(tmp_path).extract()
    assert knowledge.languages[0] == ("Python", 2)
    assert "Python/pip" in knowledge.package_systems
    assert "app.py" in knowledge.entry_points
    assert "service layer" in knowledge.architecture
    assert "pytest" in knowledge.test_frameworks
