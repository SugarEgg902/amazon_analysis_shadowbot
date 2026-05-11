# Excel Review Flow Design

## Goal

Replace `summarize_reviews` review retrieval with a file-driven workflow:

1. Overwrite `/Users/wei/Desktop/商品1/asin_list.xlsx` with exactly one Amazon review URL for the requested ASIN.
2. Poll `/Users/wei/Desktop/商品1/result/all_reviews.xlsx`.
3. As soon as that workbook contains any data, read the workbook once.
4. Use the loaded reviews for local LLM summarization.

## Constraints

- Keep the existing `asin_list.xlsx` shape unchanged.
- Do not add a header row.
- Do not compare rows in `all_reviews.xlsx` against the requested ASIN.
- As soon as `all_reviews.xlsx` has data, stop polling and continue.

## Data Flow

- Input: `asin`
- Derived value: `https://www.amazon.com/product-reviews/<asin>/ref=cm_cr_dp_d_show_all_btm?ie=UTF8&reviewerType=all_reviews`
- Write target: `/Users/wei/Desktop/商品1/asin_list.xlsx`
- Read target: `/Users/wei/Desktop/商品1/result/all_reviews.xlsx`
- Output: existing `summarize_reviews` response shape with `reviews`, counts, and LLM `pros`/`cons`/`overall`

## Implementation Notes

- Add small XLSX helpers for:
  - writing a single-cell workbook
  - reading worksheet rows from simple XLSX files
- Poll for workbook existence and non-empty rows with timeout protection.
- Preserve the current review bucketing and local LLM summary logic.

## Risks

- The local Python environment does not include `openpyxl` or `pandas`, so XLSX handling must avoid third-party dependencies.
- `all_reviews.xlsx` may contain rows without headers; parsing should tolerate unknown column names and sparse rows.
