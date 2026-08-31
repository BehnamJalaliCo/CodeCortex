from pathlib import Path

from codecortex.symbols import SymbolProviderRegistry


def test_typescript_symbols_are_extracted():
    registry = SymbolProviderRegistry()
    path = Path("service.ts")
    source = """
import api from './api'
export interface User { id: string }
export class UserService {}
export const loadUser = async () => api.get('/user')
"""
    symbols = registry.extract(path, source)
    kinds = {(symbol.kind, symbol.name) for symbol in symbols}
    assert ("interface", "User") in kinds
    assert ("class", "UserService") in kinds
    assert ("function", "loadUser") in kinds


def test_go_and_rust_are_supported():
    registry = SymbolProviderRegistry()
    go_symbols = registry.extract(Path("main.go"), "func Run() {}\ntype Store struct {}\n")
    rust_symbols = registry.extract(Path("lib.rs"), "pub struct Store {}\npub fn run() {}\n")
    assert {item.name for item in go_symbols} >= {"Run", "Store"}
    assert {item.name for item in rust_symbols} >= {"Store", "run"}
