# A2 working notes (Tasks 2, 4 and defects)

Draft material for the final PDF report. Rewrite it in your own words, because you must be able to explain every decision.
Test logs are in [`evidence/`](evidence/). Commits follow the sequence baseline → tests → refactoring → fixes.

## Running the tests

```sh
python -m unittest discover -s tests -v
```

## Task 2 – Testing safety net

New file: [`tests/test_safety_net.py`](tests/test_safety_net.py), with 35 tests. Together with the 4 starter tests in `test_smoke.py`, that makes 39.
Expected values come from `FUNCTIONAL_SPEC.md`, not from what the code currently does.

| Category | Example tests | Why it matters |
|---|---|---|
| Normal | `test_place_order_deducts_stock_and_records_order`, `test_regular_delivery_three_hoodies_matches_spec_example`, `test_list_orders_keeps_placement_order_including_cancelled` | These are the core operations the desk exists for |
| Boundary | quantity 1/99 accepted and 0/100 rejected, buy all stock then 1 more, empty list, student 4500 vs **5000**, half-cent rounding (5005 → 501), delivery at 9500 vs exactly 10000 | Off-by-one errors in business rules cost money |
| Invalid | bad customer type or fulfillment, unknown product, `"2"`/`2.0`/`True` quantities, non-dict item, invalid placement leaves the file unchanged, unknown order ID, **duplicate lines over stock**, **double cancel**, malformed save file | The spec says invalid requests must raise `ValueError` and change nothing |
| Preserve | quote == placed order, quote creates no file and changes no stock, IDs increase and are never reused, reopen preserves state, historical prices are frozen, cancel keeps totals | This behaviour is what the planned refactoring of `quote`/`place_order` could break |
| Interfaces | CLI quote exits 0 with JSON, rejected CLI request exits 2, menu quote with defaults shows `$10.00`, declining placement saves nothing, bad quantity text re-prompts | Both adapters call the service, so they check the refactoring end to end |

### Baseline result (original code): 39 run, 36 pass, 3 fail
See [`evidence/01_baseline_tests.txt`](evidence/01_baseline_tests.txt). The expected values were **not** changed to make these pass.

| Failing test | Expected (spec) | Actual | Cause |
|---|---|---|---|
| `test_student_subtotal_exactly_5000_gets_discount` | discount 500 | 0 | `subtotal > 5000`, but the spec says "at least" (`>=`) |
| `test_duplicate_lines_exceeding_stock_are_rejected` | `ValueError` (bag 3 + bag 2 > stock 4) | accepted, stock goes to −1 | Stock is checked per line, not as a combined quantity |
| `test_cancelling_twice_does_not_add_extra_stock` | mug stock 8 | 10 | `cancel_order()` never checks the status |

> **Corrections to Checkpoint A.** Mention these in the report, since they show what you learned:
> - The strategy said a student order of exactly $50 gets *no* discount. The spec says it *does*, so the original code is the one that's wrong.
> - Diagnosis 5 proposed raising `ValueError` on a second cancel. The spec says to *return the cancelled order unchanged*, so the fix follows the spec.
> - Diagnosis 4 mentions "two defects". Testing found three.

## Task 4 – Refactorings (one commit each, behaviour preserved)

After each refactoring the result was identical to the baseline: **36 pass, the same 3 fail** (logs 02–04).

**1. Magic Numbers.** Commit `985ddeb`.
- *Before:* `5000`, `10`, `600`, `10000`, `99`, `1`, `"ORD-"` and `4` appeared inline, twice each.
- *Refactoring:* Replace Magic Number with Named Constant, for example `STUDENT_DISCOUNT_THRESHOLD_CENTS` and `DELIVERY_FEE_CENTS`.
- *Reason:* The names state the business rule, and each value is defined once.
- *Verification:* `evidence/02_...txt`. Note that `>` was deliberately left as it was, because fixing the defect inside a refactoring would change behaviour.

**2. Duplicated Code.** Commit `1a87224`.
- *Before:* Lines 14–52 of `quote()` and 64–102 of `place_order()` were copies of each other.
- *Refactoring:* Extract Method into `_price_request()`, which both methods call. `place_order()` adds `order_id`/`status` in front, so the JSON key order is unchanged.
- *After:* There is one place to change a pricing rule, so a quote and its order cannot drift apart.
- *Verification:* `test_quote_matches_subsequent_placed_order`, the smoke tests and `evidence/03_...txt`.

**3. Long Method.** Commit `7b594fa`.
- *Before:* The 59-line `place_order()` loaded, validated, looked up products, priced, assigned IDs, changed stock and saved, all in one method. Product lookup loops were repeated in three places.
- *Refactoring:* Extract Method into `_validate_options`, `_build_line`, `_calculate_totals`, `_find_product`, `_next_order_id` and `_adjust_stock` (now also used by `cancel_order`).
- *After:* `place_order()` is about 8 lines that read as steps, and pricing can be understood or tested on its own.
- *Verification:* `evidence/04_...txt`.

## Defect fixes (separate from refactoring)

Commit `44a0747`. These intentionally change behaviour to match the spec: `>=` for the discount threshold, a combined-quantity stock check, and an idempotent cancel.
Result: **39/39 pass** (`evidence/05_after_defect_fixes.txt`). A manual CLI check also passed: student `notebook:10` gives discount 500, and `place --item bag:3 --item bag:2` gives exit 2.

## Still to do
- **Task 5:** wait for CR-01 from MyCourseLink. Write the Part A prediction *before* implementing it.
- **Task 6:** choose 3 AI recommendations from this session, using at least 2 of ACCEPT / MODIFY / REJECT, and export the transcript as the AI-use record.
- **Repo:** create your own **public** GitHub repo and push. `origin` currently points at the instructor's repo.
