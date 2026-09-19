#!/usr/bin/env python3
"""
Chạy lại `make coverage` của fabrion-extraction-evaluation với bộ đọc số có
nhận biết locale — KHÔNG sửa file nào trong repo đó.

Cách làm: nạp `tools.shared.text_match` rồi thay đúng một hàm `input_numbers`
trước khi `coverage.py` được import. Nhờ vậy so sánh được "nếu sửa thì điểm đổi
thế nào" trên cả ba schema, mà repo kia vẫn nguyên vẹn — kể cả nhánh
mini_project_greenwashing.

Chạy bằng venv của Fabrion (cần deps của họ):
    <fabrion>/.venv/bin/python run_coverage_patched.py [--original]
"""
import argparse, pathlib, sys

FABRION = pathlib.Path.home() / "Desktop/Fabrion/fabrion-extraction-evaluation"
HERE = pathlib.Path(__file__).resolve().parents[1]

ap = argparse.ArgumentParser()
ap.add_argument("--original", action="store_true", help="chạy nguyên bản, không vá")
args = ap.parse_args()

sys.path.insert(0, str(FABRION))
sys.path.insert(0, str(HERE))

if not args.original:
    import tools.shared.text_match as tm
    from shared.text_match_locale import input_numbers as locale_aware

    def patched(text: str) -> set[float]:
        # locale tự suy từ chính đoạn văn: tài liệu tiếng Anh giữ nguyên hành vi cũ,
        # tài liệu châu Âu mới đổi cách đọc.
        return locale_aware(text, None)

    tm.input_numbers = patched
    # coverage.py import trực tiếp tên hàm, nên phải vá TRƯỚC khi nó được nạp
    print("[đã vá] tools.shared.text_match.input_numbers -> text_match_locale\n", file=sys.stderr)

import os
os.chdir(FABRION)
from tools.schema_extraction.evaluate.coverage import main
sys.exit(main())
