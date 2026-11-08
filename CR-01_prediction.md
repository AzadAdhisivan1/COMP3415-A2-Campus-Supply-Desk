# CR-01 Part A – Prediction (recorded before implementation)

Drafted with AI assistance after Checkpoint A, and committed before any CR-01 code was written.

## 1. Behaviour or requirements that will change
- The set of valid fulfillment values grows from `pickup`/`delivery` to `pickup`/`delivery`/`express`.
- Delivery-fee rule: express always costs 1200 cents and has no free threshold. Standard delivery keeps the 600-cent fee and the free-at-10,000 threshold.
- The discount rule does **not** change. It is still calculated on the merchandise subtotal only.
- Menu prompts, CLI `--fulfillment` choices and help, the README and the functional spec need to mention express.

## 2. Files, classes and methods expected to change
- `supplydesk/service.py`
  - Constants: add `"express"` to `FULFILLMENT_OPTIONS` and add `EXPRESS_DELIVERY_FEE_CENTS = 1200`.
  - `OrderService._validate_options()`: update the error message.
  - `OrderService._calculate_totals()`: add the express fee branch.
  - Expected to be unchanged: `quote()`, `place_order()` and `cancel_order()`. Because the refactoring put the pricing logic in one place, the change should touch only the helpers.
- `supplydesk/cli.py`: `build_parser()`, where `--fulfillment` has a hard-coded `choices=("pickup", "delivery")`.
- `supplydesk/menu.py`: `read_request()`, where the fulfillment prompt text lists the options.
- `README.md` and `FUNCTIONAL_SPEC.md`: documentation.

## 3. Tests needed
- **New** (`tests/test_cr01_express.py`):
  - The three CR-01 examples: $22, $84, and $132 vs $120.
  - The express fee is not waived above $100.
  - Express quote == express order.
  - An express order keeps its data after reopening and cancelling, with stock restored.
  - Other values such as `"Express"` and `"shipping"` are still rejected.
  - CLI `--fulfillment express` gives `total_cents` 8400.
  - The menu accepts `express`, and the prompt text mentions it.
- **Existing:** the full suite (39 tests) must still pass unchanged, especially the standard-delivery boundary tests (9500 → fee, 10000 → free) and the pickup/regular defaults.
- **Possibly updated:** none expected. `test_invalid_fulfillment_is_rejected` uses `"shipping"`, which remains invalid.
