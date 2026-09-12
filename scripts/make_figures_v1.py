"""Publication figures from results you already have. No GPU, no re-running.

Figures:
  fig1_pretokenization.pdf  cl100k shatters Telugu; o200k does not
  fig2_fertility.pdf        chars/token per language + parity ratio
  fig3_corpus.pdf           corpus token counts per tokenizer
  fig4_loss.pdf             training loss curves (needs logs/*.log)
  fig5_bpb.pdf              BPB with error bars (needs results/bpb.json)

Run:  python make_figures.py
Telugu glyphs need a Telugu-capable font. Windows has "Nirmala UI".
"""
import os, re, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

import unicodedata
DOTTED = "\u25cc"

def show(s):
    """Prefix U+25CC when a chunk starts with a combining mark."""
    return DOTTED + s if s and unicodedata.category(s[0]) == "Mn" else s

PROJ = "D:/Tasks/Project_SLM"
OUT = f"{PROJ}/figures"
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({"font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.dpi": 150,
                     "savefig.bbox": "tight"})
C_CL, C_O = "#c44e52", "#4c72b0"          # cl100k red, o200k blue


def telugu_font():
    for name in ("Nirmala UI", "Noto Sans Telugu", "Gautami", "Lohit Telugu"):
        try:
            font_manager.findfont(font_manager.FontProperties(family=name),
                                  fallback_to_default=False)
            return font_manager.FontProperties(family=name)
        except Exception:
            continue
    print("  ! no Telugu font found — fig1 will show boxes.\n"
          "    On Windows try family='Nirmala UI'.")
    return None


# ---------------------------------------------------------------- figure 1
# CL_PIECES = ['హ', 'ాయ', '్,', ' న', 'ేన', 'ు', ' పర', 'ీక', '్ష', 'ిస',
#              '్త', 'ున', '్న', 'ాన', 'ు.']
# O_PIECES = ['హాయ్', ',', ' నేను', ' పరీక్షిస్తున్నాను', '.']

_p = json.load(open(f"{PROJ}/figures/fig1_pieces.json", encoding="utf-8"))
CL_PIECES, O_PIECES = _p["cl100k"], _p["o200k"]


def fig1():
    fp = telugu_font()
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 2.5))
    for ax, pieces, title, col in (
            (axes[0], CL_PIECES,
             f"cl100k pattern  ($\\backslash$p{{L}}+)  →  {len(CL_PIECES)} pieces", C_CL),
            (axes[1], O_PIECES,
             f"o200k pattern  (+$\\backslash$p{{M}})  →  {len(O_PIECES)} pieces", C_O)):
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
        ax.set_title(title, loc="left", fontsize=9, color=col, pad=4)
        widths = [max(len(p), 1) for p in pieces]
        total = sum(widths)
        x = 0.0
        for p, w in zip(pieces, widths):
            frac = w / total
            ax.add_patch(plt.Rectangle((x + 0.004, 0.15), frac - 0.008, 0.55,
                                       facecolor=col, alpha=0.16,
                                       edgecolor=col, linewidth=0.8))
            kw = dict(fontproperties=fp) if fp else {}
            ax.text(x + frac / 2, 0.42, show(p), ha="center", va="center",
                    fontsize=11, **kw)
            x += frac
    fig.suptitle("Pre-tokenisation of a Telugu sentence", fontsize=10, y=1.06)
    fig.savefig(f"{OUT}/fig1_pretokenization.pdf")
    fig.savefig(f"{OUT}/fig1_pretokenization.png", dpi= 400)
    plt.close(fig)
    print("  fig1_pretokenization")


# ---------------------------------------------------------------- figure 2
CHARS_PER_TOK = {"cl100k_pat": (4.52, 4.65, 1.98),
                 "o200k_pat": (4.43, 4.53, 4.13)}


def fig2():
    langs = ["English", "German", "Telugu"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.0, 2.6),
                               gridspec_kw={"width_ratios": [2.2, 1]})
    w, xs = 0.36, range(len(langs))
    for i, (name, col) in enumerate((("cl100k_pat", C_CL), ("o200k_pat", C_O))):
        v = CHARS_PER_TOK[name]
        pos = [x + (i - 0.5) * w for x in xs]
        a.bar(pos, v, w, label=name, color=col, alpha=0.85)
        for p, y in zip(pos, v):
            a.text(p, y + 0.06, f"{y:.2f}", ha="center", fontsize=8)
    a.set_xticks(list(xs)); a.set_xticklabels(langs)
    a.set_ylabel("characters per token"); a.set_ylim(0, 5.4)
    a.legend(frameon=False, fontsize=8)
    a.set_title("Compression (higher is better)", fontsize=9, loc="left")

    ratios = [max(v) / min(v) for v in CHARS_PER_TOK.values()]
    b.bar(["cl100k", "o200k"], ratios, 0.5, color=[C_CL, C_O], alpha=0.85)
    for i, r in enumerate(ratios):
        b.text(i, r + 0.04, f"{r:.2f}", ha="center", fontsize=8)
    b.axhline(1.0, ls="--", lw=0.8, color="grey")
    b.set_ylabel("worst / best language"); b.set_ylim(0, 2.7)
    b.set_title("Parity ratio (1.0 = fair)", fontsize=9, loc="left")
    fig.savefig(f"{OUT}/fig2_fertility.pdf")
    fig.savefig(f"{OUT}/fig2_fertility.png")
    plt.close(fig)
    print("  fig2_fertility")


# ---------------------------------------------------------------- figure 3
CORPUS_TOK = {"cl100k_pat": (4265.3, 4270.1, 4932.5),
              "o200k_pat": (4348.6, 4386.2, 2375.2)}


def fig3():
    langs = ["English", "German", "Telugu"]
    fig, ax = plt.subplots(figsize=(4.6, 2.6))
    w, xs = 0.36, range(len(langs))
    for i, (name, col) in enumerate((("cl100k_pat", C_CL), ("o200k_pat", C_O))):
        v = CORPUS_TOK[name]
        pos = [x + (i - 0.5) * w for x in xs]
        ax.bar(pos, v, w, label=name, color=col, alpha=0.85)
        for p, y in zip(pos, v):
            ax.text(p, y + 60, f"{y:,.0f}", ha="center", fontsize=7)
    ax.annotate("", xy=(2 + 0.5 * w, 2500), xytext=(2 - 0.5 * w, 4800),
                arrowprops=dict(arrowstyle="->", lw=1.2, color="black"))
    ax.text(2.05, 3700, "-51.8 %", fontsize=9, fontweight="bold")
    ax.set_xticks(list(xs)); ax.set_xticklabels(langs)
    ax.set_ylabel("tokens (millions)"); ax.set_ylim(0, 5800)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title("Corpus size after tokenisation (identical text)",
                 fontsize=9, loc="left")
    fig.savefig(f"{OUT}/fig3_corpus.pdf")
    fig.savefig(f"{OUT}/fig3_corpus.png")
    plt.close(fig)
    print("  fig3_corpus")


# ---------------------------------------------------------------- figure 4
def fig4(logdir=f"{PROJ}/logs", tokenizer="o200k"):
    """Loss curves for ONE tokeniser's seeds.

    Cross-tokeniser loss is NOT comparable: different vocabularies mean
    different per-token difficulty, so plotting both arms would invite the
    wrong reading. This figure shows seed reproducibility and clean
    convergence. The valid cross-tokeniser comparison is BPB (fig5).
    Pass tokenizer="cl100k" for the other arm.
    """
    if not os.path.isdir(logdir):
        print("  fig4 skipped (no logs/ - pipe training output to a file)")
        return
    pat = re.compile(r"iter (\d+): loss ([\d.]+)")
    fig, ax = plt.subplots(figsize=(5.2, 3.0))
    col = C_O if tokenizer.startswith("o200k") else C_CL
    styles, found = ["-", "--", ":"], 0
    for fn in sorted(os.listdir(logdir)):
        if not fn.endswith(".log") or not fn.startswith(tokenizer):
            continue
        xs, ys = [], []
        for line in open(f"{logdir}/{fn}", errors="ignore"):
            m = pat.search(line)
            if m:
                xs.append(int(m.group(1))); ys.append(float(m.group(2)))
        if not xs:
            continue
        k = 50
        ys_s = [sum(ys[max(0, i - k):i + 1]) / len(ys[max(0, i - k):i + 1])
                for i in range(len(ys))]
        ax.plot(xs, ys_s, lw=1.2, color=col, alpha=0.9,
                ls=styles[found % len(styles)], label=fn[:-4])
        found += 1
    if not found:
        print(f"  fig4 skipped (no {tokenizer}*.log found)"); plt.close(fig); return
    ax.set_xlabel("iteration"); ax.set_ylabel("training loss")
    ax.legend(frameon=False, fontsize=8)
    ax.set_title(f"Pre-training loss, {tokenizer} tokeniser "
                 f"({found} seed{'s' if found > 1 else ''}, "
                 f"50-step moving average)", fontsize=9, loc="left")
    fig.savefig(f"{OUT}/fig4_loss.pdf"); fig.savefig(f"{OUT}/fig4_loss.png")
    plt.close(fig)
    print(f"  fig4_loss ({found} seeds, {tokenizer} only)")


# ---------------------------------------------------------------- figure 5
def fig5(path=f"{PROJ}/results/bpb.json"):
    if not os.path.exists(path):
        print("  fig5 skipped (run eval_bpb.py --all first)")
        return
    res = json.load(open(path))
    langs = ["en", "de", "te"]
    fig, ax = plt.subplots(figsize=(4.6, 2.8))
    w, xs = 0.36, range(len(langs))
    for i, (pref, col) in enumerate((("cl100k", C_CL), ("o200k", C_O))):
        runs = [r for k, r in res.items() if k.startswith(pref)]
        if not runs:
            continue
        means = [sum(r[l] for r in runs) / len(runs) for l in langs]
        lo = [means[j] - min(r[langs[j]] for r in runs) for j in range(3)]
        hi = [max(r[langs[j]] for r in runs) - means[j] for j in range(3)]
        pos = [x + (i - 0.5) * w for x in xs]
        ax.bar(pos, means, w, yerr=[lo, hi], capsize=3, color=col,
               alpha=0.85, label=f"{pref} (n={len(runs)})")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(["English", "German", "Telugu"])
    ax.set_ylabel("bits per byte (lower is better)")
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("Held-out BPB, min-max over seeds", fontsize=9, loc="left")
    fig.savefig(f"{OUT}/fig5_bpb.pdf"); fig.savefig(f"{OUT}/fig5_bpb.png")
    plt.close(fig)
    print("  fig5_bpb")


if __name__ == "__main__":
    print(f"writing to {OUT}")
    fig1(); fig2(); fig3(); fig4(); fig5()
    print("done")
