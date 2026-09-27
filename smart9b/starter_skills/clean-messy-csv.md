---
name: clean-messy-csv
description: Fix headers, blank rows, duplicates and number formats in a CSV file.
status: taught
successes: 0
failures: 0
---

## Steps
1. Read the file with Python's `csv` module (`newline=""`, `encoding="utf-8-sig"` to drop a BOM).
2. Clean the header: strip spaces, lowercase, replace spaces and dashes with `_`.
3. Strip spaces from every cell. Drop rows where every cell is empty.
4. Turn number-like cells into plain numbers: remove `$`, `,` and `%`; keep the original if it doesn't parse.
5. Remove exact duplicate rows, keeping the first one.
6. Write the result to a NEW file (never overwrite the input) and print how many rows went in and out.

## Checklist
- The program ran without errors.
- The output file exists and the input file is unchanged.
- Row counts before and after are printed and make sense.
- Header names are lowercase with no spaces.

## Pitfalls
- Excel files saved as CSV often start with a BOM; `utf-8-sig` handles it.
- Don't turn ZIP codes or IDs with leading zeros into numbers.
- If the task gives no file, create a small sample file first so the program can be tested.

## Example
Input `sales.csv`:
```
 Order ID ,Amount
001,"$1,200"
001,"$1,200"
,
```
Output `sales_clean.csv`:
```
order_id,amount
001,1200
```
Printed: `rows in: 3, rows out: 1`
