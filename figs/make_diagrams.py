import subprocess, pathlib

out = pathlib.Path(__file__).parent
V2 = "#EDE9FE"
G2 = "#E3F0E9"
R2 = "#FEE2E2"

# ---------------- Graph schema (Fig 3) via Graphviz ----------------
src = f'''digraph G {{
  graph [fontname="Helvetica", dpi=300, pad=0.05, nodesep=0.2, ranksep=0.45, rankdir=LR];
  node [fontname="Helvetica", fontsize=12, shape=box, style="rounded,filled", fillcolor="#F1F1F5", color="#555555", margin="0.08,0.05"];
  edge [fontname="Helvetica", fontsize=10, color="#555555", arrowsize=0.7];
  C [label="Contact\\n{{id, name, phone}}", fillcolor="{V2}"];
  E [label="Episode\\n{{call_id, date,\\nsummary, outcome}}", fillcolor="{G2}"];
  N [label="Entity\\n{{name, type}}"]; T [label="Topic\\n{{name}}"];
  F [label="FrustrationEvent\\n{{intensity, phrase}}", fillcolor="{R2}"];
  E2 [label="Episode\\n(next call)", fillcolor="{G2}"];
  C -> E [label="HAD_EPISODE"];
  E -> N [label="MENTIONED_ENTITY"];
  E -> T [label="DISCUSSED_TOPIC"];
  E -> F [label="EXPERIENCED_\\nFRUSTRATION"];
  E -> E2 [label="TRANSITIONED_TO"];
}}'''

dot_path = out / "fig3_graph_schema.dot"
png_path = out / "fig3_graph_schema.png"
dot_path.write_text(src, encoding="utf-8")

try:
    subprocess.run(["dot", "-Tpng", str(dot_path), "-o", str(png_path)], check=True)
    print("fig3_graph_schema generated via Graphviz dot")
except Exception as e:
    print(f"Graphviz dot execution notice: {e}")
