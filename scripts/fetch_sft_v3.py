"""Download QA datasets, unify schema, dedup, balance by language.

Output: sft/train.jsonl, sft/test.jsonl, sft/train_balanced.jsonl
Fields: {context, question, answer, lang, source, answerable}

Run:  python fetch_sft.py --probe    (30s, no download — DO THIS FIRST)
      python fetch_sft.py            (full download)

Sources
  en  squad_v2          train + validation
  de  germanquad        train + test
  te  tydiqa (telugu)   train + validation   <- TRAIN
  te  IndicQA (telugu)  test                 <- TEST ONLY, never train on it
"""
import os, sys, ast, json, random
from hashlib import blake2b
from collections import Counter
from datasets import load_dataset

ROOT = "D:/Tasks/Project_SLM"
OUT = f"{ROOT}/sft"
MAX_CONTEXT_CHARS = 4000
MIN_CONTEXT_CHARS = 20
random.seed(0)

PARQUET = "refs/convert/parquet"       # HF auto-converts script datasets here
INDICQA_TE = {"data_files": {"test": "indicqa.te/test/*.parquet"},
              "revision": PARQUET}


# ---------------------------------------------------------------- normalisers
def first_answer(ans):
    """SQuAD answers as dict / list / str / stringified-dict -> (text, answerable)."""
    if ans is None:
        return None, False
    if isinstance(ans, str) and ans.lstrip().startswith("{"):
        try:
            ans = ast.literal_eval(ans)        # parquet conversion stringifies it
        except (ValueError, SyntaxError):
            return None, False
    if isinstance(ans, dict):
        texts = ans.get("text") or []
    elif isinstance(ans, list):
        texts = [a.get("text") if isinstance(a, dict) else a for a in ans]
    elif isinstance(ans, str):
        texts = [ans]
    else:
        texts = []
    if not isinstance(texts, list):
        texts = [texts]
    texts = [t for t in texts if t]
    return (texts[0], True) if texts else (None, False)


def telugu_ratio(s):
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    return sum("\u0c00" <= c <= "\u0c7f" for c in letters) / len(letters)


def emit(rows, ctx, q, ans, lang, source, stats):
    stats["seen"] += 1
    if not ctx or not q:
        stats["drop_empty"] += 1; return
    ctx = " ".join(str(ctx).split())
    q = " ".join(str(q).split())
    if not (MIN_CONTEXT_CHARS <= len(ctx) <= MAX_CONTEXT_CHARS):
        stats["drop_len"] += 1; return
    if lang == "te" and telugu_ratio(ctx) < 0.70:
        stats["drop_wrong_lang"] += 1; return   # guards against merged-config data
    text, answerable = first_answer(ans)
    if answerable:
        text = " ".join(text.split()) ## same as normalisation as ctx
    if answerable and text not in ctx:
        stats["drop_not_span"] += 1; return     # answer must be a literal span
    rows.append({"context": ctx, "question": q,
                 "answer": text if answerable else "",
                 "lang": lang, "source": source, "answerable": answerable})
    stats["kept"] += 1


def report(name, stats):
    print(f"  {name:<28} kept {stats['kept']:>7,} / {stats['seen']:>7,}  "
          f"(empty {stats['drop_empty']:,}, len {stats['drop_len']:,}, "
          f"wrong-lang {stats['drop_wrong_lang']:,}, "
          f"not-span {stats['drop_not_span']:,})", flush=True)


def get(row, *keys):
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


# ---------------------------------------------------------------- loading
def try_load(repo, split, **kw):
    """Load; on a dataset-script error retry against the parquet branch."""
    try:
        return load_dataset(repo, split=split, **kw)
    except Exception as e:
        if "script" in str(e).lower():
            try:
                ds = load_dataset(repo, split=split, revision=PARQUET, **kw)
                print(f"  (used {PARQUET} for {repo})")
                return ds
            except Exception as e2:
                print(f"  SKIP {repo} split={split}: {type(e2).__name__}: {e2}")
                return None
        print(f"  SKIP {repo} split={split}: {type(e).__name__}: {e}")
        return None

def try_load(repo, split, **kw):

    """Load; on any error retry against the parquet branch."""

    if "revision" not in kw:

        try:

            return load_dataset(repo, split=split, **kw)

        except Exception as e:

            print(f"  (main failed: {type(e).__name__}) retrying {PARQUET}")

    try:

        kw2 = {k: v for k, v in kw.items() if k != "revision"}

        ds = load_dataset(repo, split=split, revision=PARQUET, **kw2)

        print(f"  (used {PARQUET} for {repo})")

        return ds

    except Exception as e2:

        print(f"  SKIP {repo} split={split}: {type(e2).__name__}: {e2}")

        return None
 

def generic(repo, split, lang, source, tag, kw=None, id_prefix=None):
    ds = try_load(repo, split, **(kw or {}))
    if ds is None:
        return []
    rows, stats = [], Counter()
    for r in ds:
        if id_prefix and not str(r.get("id", "")).startswith(id_prefix):
            continue
        emit(rows,
             get(r, "context", "passage", "paragraph"),
             get(r, "question", "query"),
             get(r, "answers", "answer"),
             lang, source, stats)
    report(f"{source}/{split}", stats)
    return [(tag, rows)]


def load_all():
    splits = []
    print("\n--- english ---")
    splits += generic("rajpurkar/squad_v2", "train", "en", "squad_v2", "train")
    splits += generic("rajpurkar/squad_v2", "validation", "en", "squad_v2", "test")

    print("\n--- german ---")
    splits += generic("deepset/germanquad", "train", "de", "germanquad", "train")
    splits += generic("deepset/germanquad", "test", "de", "germanquad", "test")

    print("\n--- telugu (TRAIN) ---")
    for sp in ("train", "validation"):
        splits += generic("google-research-datasets/tydiqa", sp, "te", "tydiqa",
                          "train", kw={"name": "secondary_task"},
                          id_prefix="telugu")

    print("\n--- telugu (TEST ONLY — never train on this) ---")
    splits += generic("ai4bharat/IndicQA", "test", "te", "indicqa", "test",
                      kw=dict(INDICQA_TE))
    return splits


# ---------------------------------------------------------------- output
def dedup(rows):
    seen, out, dropped = set(), [], 0
    for r in rows:
        h = blake2b((r["context"] + "\x00" + r["question"]).encode(),
                    digest_size=16).digest()
        if h in seen:
            dropped += 1; continue
        seen.add(h); out.append(r)
    return out, dropped


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  -> {path}  {len(rows):,} rows")


def summarise(tag, rows):
    print(f"\n{tag}: {len(rows):,} examples")
    print(f"   by language: {dict(Counter(r['lang'] for r in rows))}")
    print(f"   by source:   {dict(Counter(r['source'] for r in rows))}")
    un = sum(1 for r in rows if not r["answerable"])
    print(f"   unanswerable: {un:,} ({un/max(len(rows),1):.1%})")
    for lang in sorted({r["lang"] for r in rows}):
        sub = [r for r in rows if r["lang"] == lang]
        u = sum(1 for r in sub if not r["answerable"])
        print(f"     {lang}: {len(sub):,} examples, {u/max(len(sub),1):.1%} unanswerable")


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    if "--probe" in sys.argv:
        print("=== schema probe (no download) ===")
        targets = [("rajpurkar/squad_v2", "train", {}),
                   ("deepset/germanquad", "train", {}),
                   ("google-research-datasets/tydiqa", "train",
                    {"name": "secondary_task"}),
                   ("ai4bharat/IndicQA", "test", dict(INDICQA_TE))]
        for repo, split, kw in targets:
            for rev in (None, PARQUET):
                try:
                    kw2 = dict(kw)
                    if rev:
                        kw2["revision"] = rev
                    ds = load_dataset(repo, streaming=True, split=split, **kw2)
                    r = next(iter(ds))
                    print(f"OK   {repo} rev={rev or 'main'}")
                    print(f"     keys: {list(r.keys())}")
                    print(f"     ctx : {str(get(r,'context'))[:70]}")
                    print(f"     ans : {str(get(r,'answers','answer'))[:70]}")
                    break
                except Exception as e:
                    if rev:
                        print(f"FAIL {repo}: {type(e).__name__}: {e}")
        sys.exit(0)

    os.makedirs(OUT, exist_ok=True)
    splits = load_all()

    train = [r for t, rs in splits for r in rs if t == "train"]
    test = [r for t, rs in splits for r in rs if t == "test"]
    train, d1 = dedup(train)
    test, d2 = dedup(test)
    print(f"\ndedup: dropped {d1:,} train, {d2:,} test duplicates")

    random.shuffle(train); random.shuffle(test)
    summarise("train", train)
    summarise("test", test)
    write_jsonl(f"{OUT}/train.jsonl", train)
    write_jsonl(f"{OUT}/test.jsonl", test)

    counts = Counter(r["lang"] for r in train)
    if counts:
        n = min(counts.values())
        bal = []
        for lang in counts:
            pool = [r for r in train if r["lang"] == lang]
            bal += random.sample(pool, min(n, len(pool)))
        random.shuffle(bal)
        summarise("train_balanced", bal)
        write_jsonl(f"{OUT}/train_balanced.jsonl", bal)
        print(f"\nbalanced by DOWNSAMPLING to {n:,} per language "
              f"(smallest = {min(counts, key=counts.get)})")
        print("If this discards most of your English, train on train.jsonl "
              "instead and report the imbalance.")
