"""Neo mọi đường dẫn vào gốc dự án, không vào thư mục chứa script.

Sau khi chia thư mục theo vai trò, `Path(__file__).parent` không còn là gốc dự án
nữa — nó là `validation/`, `extraction/`… Mọi script tham chiếu `data/` đều phải
đi qua đây, nếu không nó sẽ đi tìm `validation/data/` và im lặng không thấy gì.

Dùng:
    from shared.paths import ROOT, DATA, bootstrap
    bootstrap()          # đặt gốc dự án vào sys.path, gọi TRƯỚC khi import chéo
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONTRACTS = ROOT / "contracts"


def bootstrap() -> pathlib.Path:
    """Cho phép import chéo giữa các thư mục vai trò khi chạy dạng script."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return ROOT
