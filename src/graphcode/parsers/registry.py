from __future__ import annotations

from functools import lru_cache

from graphcode.parsers.c_cpp_parser import CParser
from graphcode.parsers.go_parser import GoParser
from graphcode.parsers.java_parser import JavaParser
from graphcode.parsers.python_parser import PythonParser
from graphcode.parsers.rust_parser import RustParser
from graphcode.parsers.ts_js_parser import TsJsParser


@lru_cache(maxsize=None)
def parser_for(language: str):
    if language == "python":
        return PythonParser()
    if language == "javascript":
        return TsJsParser("javascript")
    if language in ("typescript", "tsx"):
        return TsJsParser("typescript" if language == "typescript" else "tsx")
    if language == "go":
        return GoParser()
    if language == "java":
        return JavaParser()
    if language == "rust":
        return RustParser()
    if language == "c":
        return CParser("c")
    if language == "cpp":
        return CParser("cpp")
    raise ValueError(f"Unsupported language: {language}")
