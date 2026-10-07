import subprocess, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon
out = pathlib.Path(__file__).parent
V="#EDE9FE"; G="#E3F0E9"; Y="#FEF3C7"; R="#FEE2E2"; W="#FFFFFF"; N="#F1F1F5"
FS = 7.6

class Canvas:
    def __init__(s, w, h):
        s.fig, s.ax = plt.subplots(figsize=(w, h), dpi=300)
        s.ax.set_xlim(0, w); s.ax.set_ylim(0, h); s.ax.axis("off")
        s.n = {}
    def box(s, key, cx, cy, w, h, text, color=N, dashed=False, diamond=False):
        if diamond:
            p = Polygon([(cx-w/2,cy),(cx,cy+h/2),(cx+w/2,cy),(cx,cy-h/2)], closed=True, fc=color, ec="#555", lw=0.8)
            s.ax.add_patch(p)
        else:
            p = FancyBboxPatch((cx-w/2,cy-h/2), w, h, boxstyle="round,pad=0.0,rounding_size=0.06",
                               fc=color, ec="#555", lw=0.8, ls="--" if dashed else "-")
            s.ax.add_patch(p)
        s.ax.text(cx, cy, text, ha="center", va="center", fontsize=FS, family="DejaVu Sans")
        s.n[key] = (cx, cy, w, h)
    def a(s, key, side):
        cx, cy, w, h = s.n[key]
        return {"l":(cx-w/2,cy),"r":(cx+w/2,cy),"t":(cx,cy+h/2),"b":(cx,cy-h/2)}[side]
    def line(s, pts, label=None, lpos=None, dashed=False, arrow=True):
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        s.ax.plot(xs[:-1] if arrow else xs, ys[:-1] if arrow else ys, color="#555", lw=0.8, ls="--" if dashed else "-", solid_capstyle="butt")
        if arrow:
            s.ax.annotate("", xy=pts[-1], xytext=pts[-2], arrowprops=dict(arrowstyle="-|>", color="#555", lw=0.8, shrinkA=0, shrinkB=0, mutation_scale=7))
        if label:
            x,y = lpos if lpos else ((xs[0]+xs[-1])/2, (ys[0]+ys[-1])/2)
            s.ax.text(x, y, label, fontsize=FS-1, ha="center", va="center", color="#333",
                      bbox=dict(fc="white", ec="none", pad=0.6))
    def save(s, name):
        s.fig.savefig(out/name, bbox_inches="tight", pad_inches=0.04); plt.close(s.fig)

# ---------------- Fig 1: architecture ----------------
c = Canvas(6.9, 4.0)
def cluster(x0,y0,x1,y1,title,color):
    c.ax.add_patch(FancyBboxPatch((x0,y0),x1-x0,y1-y0,boxstyle="round,pad=0,rounding_size=0.08",fc="none",ec=color,lw=1.0,ls="--"))
    c.ax.text(x0+0.08,y1-0.07,title,fontsize=FS,ha="left",va="top",color=color,weight="bold")
cluster(0.1,2.0,6.8,3.0,"Real-time voice pipeline (Pipecat)","#7C3AED")
cluster(0.1,0.95,6.8,1.7,"Four-tier caller memory","#4F7A65")
bw=1.5; bh=0.5
c.box("web",1.2,3.75,1.9,0.46,"Browser caller\n(WebRTC via LiveKit)",W)
c.box("pstn",3.45,3.75,2.2,0.46,"PSTN caller\n(Twilio / Exotel / Plivo)",W)
c.box("api",5.8,3.75,1.9,0.46,"FastAPI service\n(sessions, agents, erasure)",N)
xs=[0.95,2.6,4.25,5.9]
c.box("stt",xs[0],2.35,bw,bh,"STT router\nWhisper | Saarika",V)
c.box("emo",xs[1],2.35,bw,bh,"Emotion + intent\nfusion, slots",V)
c.box("llm",xs[2],2.35,bw,bh,"LLM\nllama-3.3-70b",V)
c.box("tts",xs[3],2.35,bw,bh,"TTS router\nCartesia, Bulbul,\nOctave",V)
c.box("t1",xs[0],1.2,bw,bh,"T1 Redis\nin-call buffer",G)
c.box("t2",xs[1],1.2,bw,bh,"T2 pgvector\nsemantic facts",G)
c.box("t3",xs[2],1.2,bw,bh,"T3 Postgres\nepisodic summaries",G)
c.box("t4",xs[3],1.2,bw,bh,"T4 FalkorDB\ncontact graph",G)
c.box("post",2.0,0.3,3.2,0.46,"Post-call worker (Trigger.dev)\nsummary, extraction, tier writes",N)
c.box("conn",5.3,0.3,2.7,0.46,"Connectors\nCalendar, CRM, Slack, WhatsApp",N)
c.line([(1.2,3.52),(1.2,3.0)])
c.line([(3.45,3.52),(3.45,3.0)])
c.line([(5.8,3.52),(5.8,3.0)], dashed=True, label="session", lpos=(5.8,3.27))
for a,b in [("stt","emo"),("emo","llm"),("llm","tts")]:
    c.line([c.a(a,"r"), c.a(b,"l")])
c.line([(3.4,2.0),(3.4,1.7)], arrow=True)
c.line([(3.5,1.7),(3.5,2.0)], arrow=True, label="retrieve (parallel) / append turn", lpos=(5.0,1.85))
c.line([(1.2,0.53),(1.2,0.53)], arrow=False)
c.line([(2.6,0.53),(2.6,0.95)], arrow=True, dashed=True)
c.ax.text(1.2,0.78,"T1 purged\nafter call",fontsize=FS-1,ha="center",va="center",color="#333")
c.line([(4.25,0.53),(4.25,0.95)], arrow=True, dashed=True) if False else None
c.line([(3.3,0.53),(3.3,0.62),(4.25,0.62),(4.25,0.95)], arrow=True, dashed=True)
c.line([(3.6,0.62),(5.9,0.62),(5.9,0.95)], arrow=True, dashed=True, label="write-back after hang-up", lpos=(4.9,0.62))
c.line([c.a("post","r"), c.a("conn","l")], dashed=True)
c.save("fig1_architecture.png")

# ---------------- Fig 2: per-turn flow ----------------
c = Canvas(6.9, 3.45)
cx=[0.95,2.65,4.35,6.05]; ry=[3.12,2.37,1.62,0.8]; bw=1.56; bh=0.56
c.box("a",cx[0],ry[0],bw,bh,"Caller audio\n(16 kHz mono)",W)
c.box("b",cx[1],ry[0],bw,bh,"Language route\n(agent config)",Y)
c.box("c",cx[2],ry[0],bw,bh,"STT\nWhisper | Saarika",V)
c.box("d",cx[3],ry[0],bw,bh,"Transcript turn",W)
c.box("p1",cx[0],ry[1],bw,bh,"Text emotion\n(LLM, JSON mode)",V)
c.box("p2",cx[1],ry[1],bw,bh,"Audio emotion\n(Hume, circumplex)",V)
c.box("p3",cx[2],ry[1],bw,bh,"Intent + slots",V)
c.box("p4",cx[3],ry[1],bw,bh,"Memory fan-out\nT1-T4 (parallel)",G)
c.box("f",cx[0],ry[2],bw,bh,"Fusion\nv = w·v_a + (1-w)·v_t",V)
c.box("g",cx[1],ry[2],bw+0.1,bh+0.1,"v < tone\nthreshold?",Y,diamond=True)
c.box("h",cx[2],ry[2],bw,bh,"Tone instruction;\nalert if v < -θ_alert",R)
c.box("i",cx[3],ry[2],bw,bh,"Assemble prompt\n(memory, tone, slots)",N)
c.box("j",cx[3],ry[3],bw,bh,"LLM stream",V)
c.box("k",cx[2],ry[3],bw,bh,"TTS route\nEN | HI | emotion",V)
c.box("l",cx[1],ry[3],bw,bh,"Audio out;\nturn appended to T1",W)
c.box("m",cx[0],ry[3],bw,bh,"After hang-up:\npost-call worker",N,dashed=True)
for u,v in [("a","b"),("b","c"),("c","d")]:
    c.line([c.a(u,"r"), c.a(v,"l")])
bus=(ry[0]+ry[1])/2+0.02
c.line([c.a("d","b"), (cx[3],bus)], arrow=False)
c.line([(cx[0],bus),(cx[3],bus)], arrow=False)
for k in ["p1","p2","p3","p4"]:
    c.line([(c.n[k][0],bus), c.a(k,"t")])
c.line([c.a("p1","b"), c.a("f","t")])
mid=(ry[1]+ry[2])/2
c.line([c.a("p2","b"), (cx[1],mid), (cx[0]+0.45,mid), (cx[0]+0.45, c.a("f","t")[1])])
c.line([c.a("f","r"), (cx[1]-(bw+0.1)/2, ry[2])])
c.line([(cx[1]+(bw+0.1)/2, ry[2]), c.a("h","l")], label="yes", lpos=(cx[1]+0.9, ry[2]+0.12))
c.line([c.a("h","r"), c.a("i","l")])
c.line([(cx[1], ry[2]-(bh+0.1)/2), (cx[1], 1.18), (cx[3]-0.45, 1.18), (cx[3]-0.45, c.a("i","b")[1])], label="no", lpos=(cx[1]+0.12, 1.24))
c.line([c.a("p3","b"), (cx[2], mid), (cx[3]-0.45, mid), (cx[3]-0.45, c.a("i","t")[1])])
c.line([c.a("p4","b"), c.a("i","t")])
c.line([(cx[3]+0.45, c.a("i","b")[1]), (cx[3]+0.45, c.a("j","t")[1])]) if False else None
c.line([(cx[3], c.a("i","b")[1]), c.a("j","t")]) if False else None
c.line([(cx[3]+0.3, c.a("i","b")[1]), (cx[3]+0.3, c.a("j","t")[1])])
c.line([c.a("j","l"), c.a("k","r")])
c.line([c.a("k","l"), c.a("l","r")])
c.line([c.a("l","l"), c.a("m","r")], dashed=True)
c.save("fig2_turn_flow.png")
print("diagrams done")

# ---------------- Graph schema (Fig 3) via Graphviz ----------------
V2="#EDE9FE"; G2="#E3F0E9"; R2="#FEE2E2"
src = f'''digraph G {{
  graph [fontname="Helvetica", dpi=300, pad=0.05, nodesep=0.2, ranksep=0.45, rankdir=LR];
  node [fontname="Helvetica", fontsize=12, shape=box, style="rounded,filled", fillcolor="#F1F1F5", color="#555555", margin="0.08,0.05"];
  edge [fontname="Helvetica", fontsize=10, color="#555555", arrowsize=0.7];
  C [label="Contact\\n{{id, name, phone}}", fillcolor="{V2}"];
  E [label="Episode\\n{{call_id, date,\\nsummary, outcome}}", fillcolor="{G2}"];
  N [label="Entity\\n{{name, type}}"]; T [label="Topic\\n{{name}}"];
  F [label="FrustrationEvent\\n{{intensity, phrase}}", fillcolor="{R2}"];
  E2 [label="Episode\\n(next call)", fillcolor="{G2}"];
  C -> E [label="HAD_EPISODE"]; E -> N [label="MENTIONED_ENTITY"];
  E -> T [label="DISCUSSED_TOPIC"]; E -> F [label="EXPERIENCED_\\nFRUSTRATION"];
  E -> E2 [label="TRANSITIONED_TO"];
}}'''
(out/"fig3_graph_schema.dot").write_text(src)
subprocess.run(["dot","-Tpng",str(out/"fig3_graph_schema.dot"),"-o",str(out/"fig3_graph_schema.png")],check=True)
