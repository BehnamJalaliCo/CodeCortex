from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_language_pack")

from codecortex.languages import LanguageRegistry


@pytest.mark.parametrize(
    ("name", "source", "symbol"),
    [
        (
            "sample.ts",
            "export class AuthService { refresh(): string { return 'x' } }",
            "AuthService",
        ),
        ("sample.go", 'package main\nfunc RefreshToken() string { return "x" }', "RefreshToken"),
        ("sample.rs", "pub fn refresh_token() -> String { String::new() }", "refresh_token"),
        (
            "Sample.java",
            'public class AuthService { public String refresh() { return "x"; } }',
            "AuthService",
        ),
        ("sample.cpp", "class AuthService {};\nint refresh_token() { return 1; }", "AuthService"),
        (
            "Sample.cs",
            'public class AuthService { public string Refresh() { return "x"; } }',
            "AuthService",
        ),
    ],
)
def test_tree_sitter_provider_extracts_symbols(name, source, symbol):
    units = LanguageRegistry(native=True).parse(Path(name), source)
    assert any(item.name == symbol for item in units)
    assert all(item.end_line is not None for item in units)
