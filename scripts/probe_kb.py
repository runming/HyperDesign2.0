import sys

sys.path.insert(0, r"D:\hyperdesign2\backend")
from app.kb.knowledge import HashingEmbedder, KnowledgeBase
from app.kb.seed import seed

kb = KnowledgeBase(HashingEmbedder())
seed(kb)
emb = kb.embedder
vec = kb._vec

for q in ("PC+ABS 外壳 名义壁厚 多少", "注塑 拔模斜度 要求", "量子芯片光刻胶的极紫外掩膜缺陷", "今天天气怎么样"):
    qv = emb.encode(q)
    sims = vec @ qv
    order = sims.argsort()[::-1][:3]
    print(f"Q={q}")
    for i in order:
        c = kb.chunks[i]
        print(f"   sim={sims[i]:.4f}  {c.doc_title[:22]}  {c.text[:36]}")
    print(f"   max={sims.max():.4f}  median={sorted(sims)[len(sims)//2]:.4f}")
