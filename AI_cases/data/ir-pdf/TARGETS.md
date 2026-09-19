# Báo cáo phải tải tay

Không có registry cho báo cáo ESG — GRI Sustainability Disclosure Database đã đóng từ
tháng 4/2021. Phần dưới phải vào IR page lấy thủ công, rồi đặt PDF vào đúng thư mục.

## Tier 2 — không có XBRL, đây là chỗ đáng tiêu ngân sách annotation

| Công ty   | Nguồn                          | Trục khó nó phủ                        | Thư mục            |
|-----------|--------------------------------|----------------------------------------|--------------------|
| Petronas  | petronas.com (Media/Reports)   | MYR, sustainability report nặng đồ hoạ  | `petronas/`        |
| Pertamina | pertamina.com                  | IDR, song ngữ ID/EN                     | `pertamina/`       |
| PVN       | pvn.vn                         | VND, tiếng Việt — khó nhất về layout/OCR| `pvn/`             |
| Saudi Aramco | aramco.com                  | SAR, niêm yết Tadawul, không SEC        | `aramco/`          |

## Tier 1 — bản PDF thiết kế đẹp, để đối chiếu với bản iXBRL đã tải tự động

Đây là mấu chốt của eval: **cùng công ty, cùng năm, hai định dạng**. Bản iXBRL trong
`data/sec/` và `data/esef/` là bản dễ và đã có số chuẩn; bản PDF dưới đây là bản khó.
Con số giống nhau, nên bản dễ chính là ground truth miễn phí cho bản khó —
không cần annotate tay phần financial.

| Công ty   | Trang                                                | Thư mục       |
|-----------|------------------------------------------------------|---------------|
| Equinor   | equinor.com/investors/annual-reports                  | `equinor/`    |
| Shell     | shell.com/investors/results-and-reporting             | `shell/`      |
| TotalEnergies | totalenergies.com (Document d'enregistrement universel) | `totalenergies/` |
| BP        | bp.com/en/global/corporate/investors                  | `bp/`         |

Chú ý khi tải: nhiều công ty EU bản 2025 xuất **ESRS Index** thay cho GRI content index.
Ghi lại framework thực tế của từng file — Silver B cần biết nó là GRI, ESRS, IFRS S1/S2
hay TCFD trước khi parse.
