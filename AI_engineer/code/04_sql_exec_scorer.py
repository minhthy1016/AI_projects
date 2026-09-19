"""
CHALLENGE 4 — SQL Execution-Equivalence Scorer (deterministic grader cho NL-to-SQL agent).

Đề bài:
  Chấm SQL do agent sinh ra so với gold SQL. KHÔNG so chuỗi (hai câu SQL khác nhau
  hoàn toàn có thể cùng đúng). Cách đúng là CHẠY cả hai rồi so kết quả, có xử lý:
    - thứ tự cột / alias khác nhau
    - thứ tự dòng (chỉ bắt buộc khi gold có ORDER BY)
    - dòng trùng lặp (multiset, không phải set — mất DISTINCT là lỗi thật)
    - sai số dấu phẩy động
    - NULL
    - lỗi thực thi
    - SQL không an toàn (DDL/DML) -> safety gate = 0
  Và phải trả về REASON có phân loại, để tự động hóa việc sửa lỗi.

Vì sao đây là câu hay hỏi:
  Đây chính là ranh giới Tier-1/Tier-2: khi tồn tại ground truth kiểm được bằng code thì
  KHÔNG dùng LLM judge. Grader này quyết định PASS/FAIL; judge (nếu có) chỉ advisory.

Chạy: python3 04_sql_exec_scorer.py
"""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from enum import Enum

# --------------------------------------------------------------------------------------
# Taxonomy — grader nói ĐÚNG LOẠI lỗi, không chỉ nói "sai"
# --------------------------------------------------------------------------------------


class Reason(str, Enum):
    """
    Taxonomy này là đầu vào của recovery controller: reason -> gợi ý re-prompt có
    định hướng, và TUYỆT ĐỐI không inject gold answer vào prompt vòng 2
    (làm thế là rò rỉ đáp án và eval mất giá trị).
    """

    PASS = "PASS"
    UNSAFE_SQL = "UNSAFE_SQL"              # -> chặn ở safety gate, G=0
    EXECUTION_ERROR = "EXECUTION_ERROR"    # -> Contract Violation (sai schema/cú pháp)
    WRONG_SHAPE = "WRONG_SHAPE"            # -> sai số cột
    WRONG_ROWCOUNT = "WRONG_ROWCOUNT"      # -> Grain Mismatch (thiếu DISTINCT / sai group by / sai join)
    WRONG_ORDER = "WRONG_ORDER"            # -> thiếu hoặc sai ORDER BY
    WRONG_VALUES = "WRONG_VALUES"          # -> Logic Error (sai filter / sai phép tính)


RECOVERY_HINT: dict[Reason, str] = {
    Reason.EXECUTION_ERROR: "Câu SQL không chạy được. Kiểm tra lại tên bảng/cột trong schema đã cho.",
    Reason.WRONG_SHAPE: "Số cột trả về không đúng yêu cầu. Đọc lại câu hỏi xem cần đúng những cột nào.",
    Reason.WRONG_ROWCOUNT: "Độ hạt (grain) của kết quả sai. Xem lại GROUP BY, DISTINCT và điều kiện JOIN.",
    Reason.WRONG_ORDER: "Kết quả đúng nhưng thứ tự sai. Câu hỏi yêu cầu một thứ tự cụ thể.",
    Reason.WRONG_VALUES: "Sai giá trị. Xem lại điều kiện lọc và biểu thức tính toán.",
    Reason.UNSAFE_SQL: "Chỉ được phép dùng câu SELECT đọc dữ liệu.",
}


@dataclass
class Score:
    passed: bool
    reason: Reason
    detail: str = ""
    gold_rows: int = 0
    pred_rows: int = 0

    @property
    def hint(self) -> str:
        return RECOVERY_HINT.get(self.reason, "")


# --------------------------------------------------------------------------------------
# Safety gate (G) — code, không phải model
# --------------------------------------------------------------------------------------

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|attach|pragma|replace|grant|vacuum)\b",
    re.I,
)


def strip_sql(sql: str) -> str:
    """Bỏ comment trước khi kiểm — nếu không, `-- ` và `/* */` che được từ khóa nguy hiểm."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql.strip().rstrip(";").strip()


def is_safe_select(sql: str) -> bool:
    """
    Whitelist, không phải blacklist: phải bắt đầu bằng SELECT hoặc WITH, một câu lệnh duy nhất,
    và không chứa từ khóa ghi. Ngoài lớp này, production còn phải chạy bằng role READ-ONLY —
    guardrail ở tầng ứng dụng không bao giờ được là hàng phòng thủ duy nhất.
    """
    s = strip_sql(sql)
    if not s or ";" in s:  # chặn stacked query
        return False
    if not re.match(r"^\s*(select|with)\b", s, re.I):
        return False
    return not _FORBIDDEN.search(s)


# --------------------------------------------------------------------------------------
# So sánh kết quả
# --------------------------------------------------------------------------------------


def _norm(v, float_tol: float):
    """Chuẩn hóa một ô để so sánh: NULL, số nguyên vs thực, khoảng trắng/hoa thường của chuỗi."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return str(v)
        # Làm tròn về lưới tol: 10.0 và 10 phải bằng nhau, 10.001 và 10.0 cũng vậy nếu tol=0.01
        return round(float(v) / float_tol) * float_tol if float_tol > 0 else float(v)
    return str(v).strip().lower()


def _rowset(rows, float_tol: float):
    return [tuple(_norm(c, float_tol) for c in r) for r in rows]


def compare(
    gold_rows: list[tuple],
    pred_rows: list[tuple],
    order_matters: bool,
    float_tol: float = 1e-6,
) -> tuple[bool, Reason, str]:
    g, p = _rowset(gold_rows, float_tol), _rowset(pred_rows, float_tol)

    if g and p and len(g[0]) != len(p[0]):
        return False, Reason.WRONG_SHAPE, f"gold có {len(g[0])} cột, pred có {len(p[0])}"
    if len(g) != len(p):
        return False, Reason.WRONG_ROWCOUNT, f"gold {len(g)} dòng, pred {len(p)} dòng"

    if order_matters:
        if g == p:
            return True, Reason.PASS, ""
        # Cùng multiset nhưng khác thứ tự => lỗi ORDER BY, không phải lỗi logic.
        if sorted(g, key=repr) == sorted(p, key=repr):
            return False, Reason.WRONG_ORDER, "đúng tập dòng, sai thứ tự"
        return False, Reason.WRONG_VALUES, "giá trị khác nhau"

    # So như MULTISET (giữ trùng lặp) — mất DISTINCT phải bị bắt.
    if sorted(g, key=repr) == sorted(p, key=repr):
        return True, Reason.PASS, ""
    missing = [r for r in g if g.count(r) > p.count(r)][:2]
    return False, Reason.WRONG_VALUES, f"thiếu/khác ở các dòng ví dụ: {missing}"


# --------------------------------------------------------------------------------------
# Scorer
# --------------------------------------------------------------------------------------

_ORDER_BY = re.compile(r"\border\s+by\b", re.I)


def score_sql(conn: sqlite3.Connection, gold_sql: str, pred_sql: str, timeout_ops: int = 1_000_000) -> Score:
    """
    Gold quyết định order_matters: nếu câu hỏi cần thứ tự thì gold SQL sẽ có ORDER BY.
    Đừng suy ra từ pred — agent thêm ORDER BY thừa không được coi là sai.
    """
    if not is_safe_select(pred_sql):
        return Score(False, Reason.UNSAFE_SQL, "chỉ chấp nhận một câu SELECT/WITH đọc dữ liệu")

    # Chặn query chạy vô hạn — grader không bao giờ được treo cả suite eval.
    conn.set_progress_handler(lambda: 1, timeout_ops)
    try:
        gold_rows = conn.execute(strip_sql(gold_sql)).fetchall()
    except sqlite3.Error as e:
        conn.set_progress_handler(None, 0)
        raise AssertionError(f"GOLD SQL hỏng — lỗi của bộ dữ liệu, không phải của agent: {e}") from e
    try:
        pred_rows = conn.execute(strip_sql(pred_sql)).fetchall()
    except sqlite3.Error as e:
        return Score(False, Reason.EXECUTION_ERROR, str(e), len(gold_rows), 0)
    finally:
        conn.set_progress_handler(None, 0)

    ok, reason, detail = compare(gold_rows, pred_rows, order_matters=bool(_ORDER_BY.search(gold_sql)))
    return Score(ok, reason, detail, len(gold_rows), len(pred_rows))


# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------

DDL = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, country TEXT);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, status TEXT);
INSERT INTO customers VALUES (1,'Anh','VN'),(2,'Binh','VN'),(3,'Chi','SG');
INSERT INTO orders VALUES
  (1,1,100.0,'paid'),(2,1,250.0,'paid'),(3,2,75.5,'refunded'),
  (4,2,300.0,'paid'),(5,3,120.0,'paid'),(6,3,60.0,'pending');
"""


def _tests() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(DDL)

    GOLD = """
      SELECT c.name, SUM(o.amount) AS total
      FROM orders o JOIN customers c ON c.id = o.customer_id
      WHERE o.status = 'paid' GROUP BY c.name ORDER BY total DESC
    """

    # (a) SQL viết khác hoàn toàn nhưng tương đương -> PASS. So chuỗi sẽ fail ở đây.
    s = score_sql(conn, GOLD, """
        WITH paid AS (SELECT customer_id, amount FROM orders WHERE status='paid')
        SELECT cu.name AS customer, ROUND(SUM(p.amount),6) AS revenue
        FROM paid p, customers cu WHERE cu.id = p.customer_id
        GROUP BY cu.name ORDER BY revenue DESC
    """)
    assert s.passed, (s.reason, s.detail)

    # (b) Thiếu ORDER BY khi gold có -> WRONG_ORDER, không phải WRONG_VALUES.
    s = score_sql(conn, GOLD, """
        SELECT c.name, SUM(o.amount) FROM orders o JOIN customers c ON c.id=o.customer_id
        WHERE o.status='paid' GROUP BY c.name ORDER BY c.name DESC
    """)
    assert not s.passed and s.reason is Reason.WRONG_ORDER, s

    # (c) Sai filter -> WRONG_VALUES (Logic Error).
    s = score_sql(conn, GOLD, """
        SELECT c.name, SUM(o.amount) AS total FROM orders o JOIN customers c ON c.id=o.customer_id
        GROUP BY c.name ORDER BY total DESC
    """)
    assert not s.passed and s.reason is Reason.WRONG_VALUES, s

    # (d) Grain mismatch: quên GROUP BY -> WRONG_ROWCOUNT.
    s = score_sql(conn, GOLD, "SELECT c.name, o.amount FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.status='paid'")
    assert not s.passed and s.reason is Reason.WRONG_ROWCOUNT, s
    assert "Grain" in s.hint or "grain" in s.hint.lower()

    # (e) Sai số cột -> WRONG_SHAPE.
    s = score_sql(conn, GOLD, "SELECT c.name, SUM(o.amount) AS t, COUNT(*) FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.status='paid' GROUP BY c.name ORDER BY t DESC")
    assert not s.passed and s.reason is Reason.WRONG_SHAPE, s

    # (f) SQL lỗi -> EXECUTION_ERROR, và grader KHÔNG được crash.
    s = score_sql(conn, GOLD, "SELECT revenu FROM orders")
    assert not s.passed and s.reason is Reason.EXECUTION_ERROR and "revenu" in s.detail

    # (g) Safety gate: mọi thao tác ghi bị chặn TRƯỚC khi chạm database.
    for bad in [
        "DROP TABLE orders",
        "SELECT 1; DROP TABLE orders",
        "SELECT 1 -- \nDELETE FROM orders",
        "DELETE /* x */ FROM orders",
    ]:
        assert score_sql(conn, GOLD, bad).reason is Reason.UNSAFE_SQL, bad
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 6, "database phải còn nguyên"

    # (h) DISTINCT có ý nghĩa: so multiset, không phải set.
    G2 = "SELECT country FROM customers"                      # VN, VN, SG
    assert not score_sql(conn, G2, "SELECT DISTINCT country FROM customers").passed

    # (i) Sai số dấu phẩy động trong ngưỡng -> vẫn PASS.
    assert score_sql(conn, "SELECT 0.1+0.2", "SELECT 0.3").passed

    # (j) NULL so được với NULL, và NULL != 0.
    assert score_sql(conn, "SELECT NULL", "SELECT NULL").passed
    assert not score_sql(conn, "SELECT NULL", "SELECT 0").passed

    print("PASS 04_sql_exec_scorer")
    bad = score_sql(conn, GOLD, "SELECT c.name, o.amount FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.status='paid'")
    print(f"  ví dụ output grader: reason={bad.reason.value} gold={bad.gold_rows} pred={bad.pred_rows}")
    print(f"  recovery hint (vòng 2, KHÔNG lộ đáp án): {bad.hint}")


if __name__ == "__main__":
    _tests()
