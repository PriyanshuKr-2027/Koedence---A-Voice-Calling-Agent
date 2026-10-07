"""PLACEHOLDER charts. Every number below is illustrative, NOT a measured result.
Replace the arrays with your own measurements and re-run: python3 make_charts.py"""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, pathlib
out = pathlib.Path(__file__).parent
plt.rcParams.update({"font.size":8,"font.family":"DejaVu Sans","axes.spines.top":False,"axes.spines.right":False})
P="#7C3AED"; Gc="#4F7A65"; Gy="#9CA3AF"; Am="#D97706"

def wm(ax):
    ax.text(0.5,0.5,"PLACEHOLDER DATA",transform=ax.transAxes,ha="center",va="center",
            fontsize=15,color="red",alpha=0.18,rotation=20,weight="bold")

# ---- Fig 4: memory ablation (a) + emotion modality (b) ----
fig,(a1,a2)=plt.subplots(1,2,figsize=(6.9,2.5),dpi=300)
cfg=["No\nmemory","T2\nvector","T2+T3\n(+episodic)","T1-T4\n(full)"]
acc=[20,48,58,66]            # PLACEHOLDER
rec=[10,45,52,69]            # PLACEHOLDER
x=np.arange(4); w=0.38
a1.bar(x-w/2,acc,w,color=P,label="QA accuracy (%)"); a1.bar(x+w/2,rec,w,color=Gc,label="Pattern recall@3 (%)")
a1.set_xticks(x); a1.set_xticklabels(cfg); a1.set_ylim(0,100); a1.set_ylabel("Score (%)")
a1.set_title("(a) Memory-tier ablation",fontsize=8.5); a1.legend(frameon=False,fontsize=7,loc="upper left"); wm(a1)
mods=["Text only","Audio only","Fused\n(w = 0.6)"]; f1=[55,61,66]   # PLACEHOLDER
a2.bar(mods,f1,color=[Gy,Gy,P],width=0.55); a2.set_ylim(0,100); a2.set_ylabel("Macro-F1 (%)")
a2.set_title("(b) Emotion signal comparison",fontsize=8.5); wm(a2)
fig.tight_layout(); fig.savefig(out/"fig4_memory_emotion.png",bbox_inches="tight"); plt.close(fig)

# ---- Fig 5: latency stack (a) + fusion weight sweep (b) ----
fig,(b1,b2)=plt.subplots(1,2,figsize=(6.9,2.5),dpi=300)
stages=["STT","Emotion /\nmemory","LLM\nTTFT","TTS\nTTFAB","Network"]
en=[150,50,300,80,40]; hi=[200,50,300,150,40]      # PLACEHOLDER (ms)
cols=["#C4B5FD","#86EFAC","#7C3AED","#FCD34D","#D1D5DB"]
for i,(lab,vals) in enumerate([("English",en),("Hinglish",hi)]):
    left=0
    for s,v,cl in zip(stages,vals,cols):
        b1.barh(i,v,left=left,color=cl,edgecolor="white",label=s.replace("\n"," ") if i==0 else None); left+=v
b1.axvline(800,color="red",ls="--",lw=0.8); b1.text(800,1.45,"800 ms target",color="red",fontsize=6.5,ha="right")
b1.set_yticks([0,1]); b1.set_yticklabels(["English","Hinglish"]); b1.set_xlabel("p95 latency (ms)")
b1.set_title("(a) Per-stage latency",fontsize=8.5); b1.legend(frameon=False,fontsize=6,ncol=3,loc="lower center",bbox_to_anchor=(0.5,-0.55)); wm(b1)
ws=np.linspace(0,1,11); f=62+8*np.exp(-((ws-0.55)**2)/0.08)-2     # PLACEHOLDER shape
b2.plot(ws,f,marker="o",ms=3,color=P); b2.set_xlabel("Audio weight w"); b2.set_ylabel("Macro-F1 (%)"); b2.set_ylim(40,90)
b2.set_title("(b) Fusion-weight sweep",fontsize=8.5); wm(b2)
fig.tight_layout(); fig.savefig(out/"fig5_latency_fusion.png",bbox_inches="tight"); plt.close(fig)
print("charts done")
