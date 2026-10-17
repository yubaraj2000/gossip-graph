"""Write docs/QUERIES.md: every Cypher query in the memory service, straight from the source, with its comment.

    uv run python -m scripts.export_queries

Named queries are module-level string constants (or dicts of them); inline queries are string literals passed
directly to a call. Re-run after changing a query so the document never drifts from the code.
"""
import ast
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "QUERIES.md"
CYPHER = re.compile(r"\b(MATCH|MERGE|CREATE|CALL|UNWIND)\b")
ORDER = ["db", "ingest", "recall", "explain", "narrate", "cases", "templates", "view"]


def comment_above(lines: list[str], lineno: int) -> str:
    """The run of `#` comment lines directly above a statement (1-based lineno)."""
    out, i = [], lineno - 2
    while i >= 0 and lines[i].strip().startswith("#"):
        out.insert(0, lines[i].strip().lstrip("#").strip())
        i -= 1
    return " ".join(out)


def cypher_text(node: ast.AST, source: str) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and CYPHER.search(node.value):
        return textwrap.dedent(node.value).strip()
    if isinstance(node, ast.JoinedStr):
        # Render the f-string with its placeholders as written, e.g. "(n:{label})".
        text = "".join(v.value if isinstance(v, ast.Constant) else "{" + ast.get_source_segment(source, v.value) + "}"
                       for v in node.values)
        if CYPHER.search(text):
            return text.strip()
    return None


def module_queries(path: Path) -> tuple[str, list[tuple[str, str, str]]]:
    source = path.read_text()
    lines = source.splitlines()
    tree = ast.parse(source)
    doc = (ast.get_docstring(tree) or "").splitlines()[0] if ast.get_docstring(tree) else ""
    found, named_values = [], set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
            if (text := cypher_text(value, source)) is not None:
                found.append((name, comment_above(lines, node.lineno), text))
                named_values.add(id(value))
            elif isinstance(value, ast.Dict):
                for k, v in zip(value.keys, value.values):
                    if isinstance(k, ast.Constant) and (text := cypher_text(v, source)) is not None:
                        found.append((f"{name}[{k.value!r}]", comment_above(lines, node.lineno), text))
                        named_values.add(id(v))
    # Inline literals, labelled with the function they're in.
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(fn):
            if isinstance(call, ast.Call):
                for arg in call.args:
                    if id(arg) not in named_values and (text := cypher_text(arg, source)) is not None:
                        found.append((f"inline in `{fn.name}()`", comment_above(lines, call.lineno), text))
    return doc, found


def main() -> None:
    modules = sorted((ROOT / "memory").glob("*.py"), key=lambda p: (ORDER.index(p.stem) if p.stem in ORDER else 99, p.stem))
    parts, total, used = [], 0, 0
    for path in modules:
        doc, queries = module_queries(path)
        if not queries:
            continue
        total += len(queries)
        used += 1
        parts.append(f"## `memory/{path.name}`\n\n{doc}\n")
        for name, comment, text in queries:
            parts.append(f"### {name if name.startswith('inline') else f'`{name}`'}\n")
            if comment:
                parts.append(f"{comment}\n")
            parts.append(f"```cypher\n{text}\n```\n")
    header = (
        "# Every Cypher query\n\n"
        f"All **{total}** queries the memory service runs against FalkorDB, copied from the source by "
        "`scripts/export_queries.py` (re-run it after changing a query; don't edit this file by hand). "
        "`$name` is a query parameter; `{rel}` in the betweenness query is `FRIEND`, or `KNOWS` before any "
        "friendships exist. Besides these, the service uses `GRAPH.COPY` to start a world from a village template "
        "(`memory/templates.py`).\n\n"
        "For what each query is for, start with the README's \"How the graph does the work\" and "
        "[DATA_MODEL.md](DATA_MODEL.md).\n\n"
    )
    OUT.write_text(header + "\n".join(parts))
    print(f"wrote {OUT.relative_to(ROOT)}: {total} queries from {used} modules")


if __name__ == "__main__":
    main()
