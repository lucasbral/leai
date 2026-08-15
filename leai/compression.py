from __future__ import annotations
import re
from leai.models import SchemaMetadata


def minify_plsql_source(source: str) -> str:
    """Removes license/history header comments and collapses excessive blank spaces."""
    if not source:
        return ""

    text = source

    # 1. Remove header comment blocks like /* ... */ containing license/history keywords
    def _strip_license_block(match: re.Match) -> str:
        raw = match.group(0)
        # Preserve Oracle optimizer hints (e.g. /*+ INDEX(...) */)
        if raw.startswith("/*+"):
            return raw
        content = raw.lower()
        if any(k in content for k in ("license", "copyright", "author:", "autor:", "history:", "historico:", "version:", "versão:")):
            return ""
        return raw

    text = re.sub(r"/\*.*?\*/", _strip_license_block, text, flags=re.DOTALL)

    # 2. Remove comment lines containing only separators (e.g. -- ================== or -- ------------)
    text = re.sub(r"^\s*--\s*[-=_*]{4,}\s*$", "", text, flags=re.MULTILINE)

    # 3. Collapse multiple consecutive newlines into at most two
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # 4. Strip trailing whitespace from line ends
    text = "\n".join(line.rstrip() for line in text.splitlines())

    return text.strip()


def extract_subprogram_block(package_source: str, subprogram_name: str) -> str | None:
    """Surgically extracts the exact block of a PROCEDURE or FUNCTION from within a Package."""
    if not package_source or not subprogram_name:
        return None

    target = subprogram_name.strip()
    # Pattern to match PROCEDURE/FUNCTION <NAME> ... END [<NAME>];
    pattern = rf"(?is)\b(PROCEDURE|FUNCTION)\s+{re.escape(target)}\b.*?\bEND(?:\s+{re.escape(target)})?\s*;"

    match = re.search(pattern, package_source)
    if match:
        return minify_plsql_source(match.group(0))

    return None


def extract_package_skeleton(package_source: str) -> str:
    """Generates a compact Package skeleton containing only subprogram signatures."""
    if not package_source:
        return ""

    lines = []
    # Capture signatures: PROCEDURE/FUNCTION <NAME>(...) [RETURN ...] [IS|AS|;]
    sig_pattern = re.compile(
        r"(?is)\b(PROCEDURE|FUNCTION)\s+([A-Za-z0-9_$#]+)\s*(\([^)]*\))?\s*(?:RETURN\s+[A-Za-z0-9_$#%]+)?\s*(?:IS|AS|;)",
    )

    for match in sig_pattern.finditer(package_source):
        routine_type = match.group(1).upper()
        routine_name = match.group(2).upper()
        params = match.group(3) or ""
        params_clean = " ".join(params.split())

        # If RETURN is present in the block
        full_match = match.group(0)
        ret_match = re.search(r"(?i)RETURN\s+([A-Za-z0-9_$#%]+)", full_match)
        ret_str = f" RETURN {ret_match.group(1).upper()}" if ret_match else ""

        lines.append(f"  {routine_type} {routine_name}{params_clean}{ret_str};")

    if not lines:
        # If not matched by detailed regex, return first 1500 minified characters
        return minify_plsql_source(package_source)[:1500]

    return "PACKAGE SKELETON (Assinaturas dos Subprogramas):\n" + "\n".join(lines)


def compact_schema_notation(schema: SchemaMetadata, max_tables: int = 40) -> str:
    """Ultra-dense representation of tables and FKs to conserve tokens across large schemas."""
    table_lines = []

    for t in schema.tables[:max_tables]:
        pk_set = set(t.primary_keys)
        fk_map = {fk.column: f"->{fk.referenced_table}" for fk in t.foreign_keys}

        cols_repr = []
        for col in t.columns[:10]:
            c_name = col.name
            suffix = "*" if c_name in pk_set else ""
            fk_ref = fk_map.get(c_name, "")
            cols_repr.append(f"{c_name}{suffix}{fk_ref}")

        if len(t.columns) > 10:
            cols_repr.append(f"+{len(t.columns) - 10}cols")

        table_lines.append(f"{t.name}({', '.join(cols_repr)})")

    view_names = [v.name for v in schema.views[:30]]
    pkg_names = [co.name for co in schema.code_objects[:30]]

    result_parts = [f"Schema '{schema.schema_name}':", "Tabelas: " + "; ".join(table_lines)]
    if view_names:
        result_parts.append("Views: " + ", ".join(view_names))
    if pkg_names:
        result_parts.append("Packages/Procs: " + ", ".join(pkg_names))

    return "\n".join(result_parts)
