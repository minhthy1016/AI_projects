"""
CHALLENGE 1 — Hybrid retrieval: BM25 + vector, fuse bằng RRF, đa dạng hóa bằng MMR.

Đề bài:
  Cho một corpus nhỏ. Implement:
    1) BM25 ranking (lexical)
    2) Dense ranking (cosine trên embedding)
    3) Reciprocal Rank Fusion để gộp 2 danh sách rank
    4) MMR để chọn top-k vừa liên quan vừa không trùng lặp
  Không dùng thư viện ngoài. Chỉ stdlib.

Vì sao đây là câu hay hỏi:
  Nó kiểm tra bạn hiểu *vì sao* cần hybrid (vector miss exact-match token như mã lỗi,
  BM25 miss paraphrase), và hiểu RRF fuse theo RANK chứ không theo SCORE — nên không
  cần normalize hai thang điểm khác nhau. Đó là câu trả lời senior.

Chạy: python3 01_hybrid_retrieval.py

Test data: 

CORPUS = [
    "Error code E-4021 means the payment gateway rejected the card as expired.",       # 0
    "Refund policy: customers can request a refund within 30 days of purchase.",       # 1
    "Money back requests are accepted for one month after the order is placed.",       # 2
    "Refunds are processed to the original payment method within 5 business days.",    # 3
    "The warranty covers manufacturing defects for 24 months from delivery date.",     # 4
    "Shipping is free for orders above 500000 VND to all provinces.",                  # 5
]

Expected output:

PASS 01_hybrid_retrieval
  exact-match query 'E-4021'      -> Error code E-4021 means the payment gateway rejected the car
  paraphrase 'get refund'  -> Refund policy: customers can request a refund within 30 days
  paraphrase 'get money back'  -> Money back requests are accepted for one month after the ord


"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field

# --------------------------------------------------------------------------------------
# Tokenize
# --------------------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Giữ nguyên token có dấu gạch nối (E-4021) — quan trọng cho exact match."""
    return _TOKEN.findall(text.lower())


# --------------------------------------------------------------------------------------
# 1) BM25
# --------------------------------------------------------------------------------------


@dataclass
class BM25:
    """BM25 Okapi. k1 điều chỉnh độ bão hòa tần suất, b điều chỉnh chuẩn hóa độ dài."""

    k1: float = 1.5
    b: float = 0.75
    docs: list[list[str]] = field(default_factory=list)
    df: Counter = field(default_factory=Counter)
    avgdl: float = 0.0

    def fit(self, corpus: list[str]) -> "BM25":
        self.docs = [tokenize(d) for d in corpus]
        self.avgdl = sum(len(d) for d in self.docs) / max(len(self.docs), 1)
        self.df = Counter()
        for doc in self.docs:
            for term in set(doc):
                self.df[term] += 1
        return self

    def _idf(self, term: str) -> float:
        n = len(self.docs)
        df = self.df.get(term, 0)
        # +1 ở ngoài log để idf không bao giờ âm với term phổ biến
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score(self, query: str) -> list[float]:
        q_terms = tokenize(query)
        out = []
        for doc in self.docs:
            tf = Counter(doc)
            dl = len(doc)
            s = 0.0
            for term in q_terms:
                f = tf.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                s += self._idf(term) * (f * (self.k1 + 1)) / denom
            out.append(s)
        return out


# --------------------------------------------------------------------------------------
# 2) Dense retrieval (embedding giả lập, deterministic — thay bằng API thật trong prod)
# --------------------------------------------------------------------------------------

DIM = 1024


def embed(text: str) -> list[float]:
    """
    Hashing embedding trên word + char-trigram, đã L2-normalize.
    Trigram giúp bắt được biến thể hình thái (refund/refunds) -> giả lập tính "semantic".

    ĐÂY LÀ STUB. Trong production thay bằng embedding model thật; toàn bộ phần còn lại
    của file không đổi một dòng nào. Nói được điều này khi phỏng vấn = bạn hiểu chỗ nào
    là seam thay thế được trong kiến trúc retrieval.
    """
    vec = [0.0] * DIM
    toks = tokenize(text)
    grams = [t[i : i + 3] for t in toks for i in range(max(len(t) - 2, 1))]
    for feat in toks + grams:
        h = hashlib.blake2b(feat.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % DIM
        sign = 1.0 if h[4] % 2 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# --------------------------------------------------------------------------------------
# 3) Reciprocal Rank Fusion
# --------------------------------------------------------------------------------------


def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """
    rankings: mỗi phần tử là list doc-id đã sắp xếp giảm dần độ liên quan.
    Điểm = sum(1 / (k + rank)), rank bắt đầu từ 1.

    Điểm mấu chốt để nói khi phỏng vấn:
      RRF fuse theo RANK, không theo SCORE -> không cần normalize BM25 (không chặn trên)
      với cosine (chặn [-1,1]). Đó là lý do nó là default tốt trong thực tế.
      k lớn làm phẳng ảnh hưởng của top rank; k=60 là giá trị quen dùng.
    """
    scores: Counter = Counter()
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


# --------------------------------------------------------------------------------------
# 4) Maximal Marginal Relevance
# --------------------------------------------------------------------------------------


def mmr(
    query_vec: list[float],
    candidates: list[int],
    doc_vecs: list[list[float]],
    top_k: int = 3,
    lambda_: float = 0.7,
) -> list[int]:
    """
    Chọn lần lượt doc tối đa hóa: lambda*sim(q,d) - (1-lambda)*max sim(d, đã chọn).
    lambda=1 -> thuần liên quan; lambda=0 -> thuần đa dạng.
    Dùng để loại evidence trùng lặp trước khi nhồi vào context (tiết kiệm token thật).
    """
    selected: list[int] = []
    pool = list(candidates)
    while pool and len(selected) < top_k:
        best, best_score = None, -math.inf
        for doc_id in pool:
            rel = cosine(query_vec, doc_vecs[doc_id])
            red = max((cosine(doc_vecs[doc_id], doc_vecs[s]) for s in selected), default=0.0)
            score = lambda_ * rel - (1 - lambda_) * red
            if score > best_score:
                best, best_score = doc_id, score
        selected.append(best)  # type: ignore[arg-type]
        pool.remove(best)  # type: ignore[arg-type]
    return selected


# --------------------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------------------


class HybridRetriever:
    def __init__(self, corpus: list[str]):
        self.corpus = corpus
        self.bm25 = BM25().fit(corpus)
        self.doc_vecs = [embed(d) for d in corpus]

    def _rank(self, scores: list[float], top_n: int, floor: float = 0.0) -> list[int]:
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        return [i for i in order if scores[i] > floor][:top_n]

    def search(
        self,
        query: str,
        top_k: int = 3,
        pool_n: int = 10,
        diversify: bool = True,
        min_sim: float = 0.20,
    ):
        """
        min_sim = ngưỡng từ chối của tầng dense. Không có ngưỡng này thì vector search
        LUÔN trả về k document gần nhất kể cả khi corpus không chứa câu trả lời —
        đó là một trong những nguyên nhân hallucination phổ biến nhất của RAG.

        Ngưỡng phải được CALIBRATE trên golden set (chọn điểm cân bằng giữa
        no-answer rate và recall), không phải đoán. Đây là câu trả lời senior.
        """
        lex_rank = self._rank(self.bm25.score(query), pool_n)
        q_vec = embed(query)
        dense_scores = [cosine(q_vec, dv) for dv in self.doc_vecs]
        dense_rank = self._rank(dense_scores, pool_n, floor=min_sim)

        fused = [doc_id for doc_id, _ in rrf([lex_rank, dense_rank])]
        if not fused:
            return []  # đường từ chối: không có evidence -> không trả lời
        if diversify:
            fused = mmr(q_vec, fused[:pool_n], self.doc_vecs, top_k=top_k)
        return [(i, self.corpus[i]) for i in fused[:top_k]]


# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------

CORPUS = [
    "Error code E-4021 means the payment gateway rejected the card as expired.",       # 0
    "Refund policy: customers can request a refund within 30 days of purchase.",       # 1
    "Money back requests are accepted for one month after the order is placed.",       # 2
    "Refunds are processed to the original payment method within 5 business days.",    # 3
    "The warranty covers manufacturing defects for 24 months from delivery date.",     # 4
    "Shipping is free for orders above 500000 VND to all provinces.",                  # 5
]


def _tests() -> None:
    r = HybridRetriever(CORPUS)

    # (a) BM25 phải thắng tuyệt đối ở exact-token query — đây là lý do tồn tại của lexical.
    lex = r.bm25.score("E-4021")
    assert lex.index(max(lex)) == 0, "BM25 phải tìm ra doc chứa mã lỗi chính xác"

    # (b) RRF: doc xuất hiện tốt ở CẢ HAI danh sách phải lên trên doc chỉ tốt ở một.
    fused = rrf([[7, 1, 2], [1, 9, 3]])
    assert fused[0][0] == 1, "doc có mặt ở cả 2 ranking phải xếp đầu"
    top_ids = [d for d, _ in fused[:3]]
    assert 7 in top_ids and 9 in top_ids

    # (c) MMR phải giảm trùng lặp: doc 1/2/3 đều nói về refund.
    q = embed("refund policy")
    dup_pool = [1, 2, 3]
    picked = mmr(q, dup_pool, r.doc_vecs, top_k=2, lambda_=0.3)
    assert len(set(picked)) == 2

    # (d) End-to-end trả về đúng số lượng và đúng chủ đề.
    hits = r.search("get refund", top_k=3)
    assert 1 <= len(hits) <= 3
    assert any(i in (1, 2, 3) for i, _ in hits), "phải truy hồi được nhóm refund"

    # (e) Query không liên quan -> rỗng -> hệ thống phải REFUSE, không được bịa.
    assert r.search("quantum chromodynamics lagrangian") == []

    print("PASS 01_hybrid_retrieval")
    print("  exact-match query 'E-4021'      ->", r.search("E-4021", top_k=1)[0][1][:60])
    print("  paraphrase 'get refund'  ->", r.search("get refund", top_k=2)[0][1][:60])
    print("  paraphrase 'get money back'  ->", r.search("get money back", top_k=2)[0][1][:60])      


if __name__ == "__main__":
    _tests()
