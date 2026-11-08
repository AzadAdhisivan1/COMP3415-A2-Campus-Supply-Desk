"""Task 2 safety-net tests for Campus Supply Desk.

Expected values come from FUNCTIONAL_SPEC.md, not from the current code.
A failing test here documents a suspected defect; its expectation must not
be changed just to make it pass.

Categories (see the report, Task 2):
    NormalBehaviourTests      - valid operations
    BoundaryBehaviourTests    - limits and edge cases
    InvalidBehaviourTests     - rejected input / unsupported operations
    PreservedBehaviourTests   - behaviour the refactoring must not change
    InterfaceTests            - menu and command-line adapters
"""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from supplydesk import cli, menu
from supplydesk.service import OrderService


def item(product_id, quantity):
    return {"product_id": product_id, "quantity": quantity}


class ServiceTestCase(unittest.TestCase):
    """Gives every test its own temporary save file."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def stock_of(self, product_id):
        for product in self.service.catalog():
            if product["product_id"] == product_id:
                return product["stock"]
        raise AssertionError("product not in catalog: " + product_id)

    def write_state(self, catalog, orders=None, next_order_number=1):
        """Create a save file with a custom catalog (for limits the bundled catalog cannot reach)."""
        self.path.write_text(json.dumps({
            "schema_version": 1,
            "next_order_number": next_order_number,
            "catalog": catalog,
            "orders": orders or [],
        }), encoding="utf-8")

    def saved_text(self):
        return self.path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. Normal
class NormalBehaviourTests(ServiceTestCase):
    def test_place_order_deducts_stock_and_records_order(self):
        order = self.service.place_order("regular", [item("notebook", 3), item("mug", 2)])
        self.assertEqual(order["order_id"], "ORD-0001")
        self.assertEqual(order["status"], "placed")
        self.assertEqual(order["subtotal_cents"], 3 * 500 + 2 * 1500)
        self.assertEqual(order["total_cents"], 4500)
        self.assertEqual(self.stock_of("notebook"), 17)
        self.assertEqual(self.stock_of("mug"), 6)
        self.assertEqual(self.service.list_orders(), [order])

    def test_regular_delivery_three_hoodies_matches_spec_example(self):
        quote = self.service.quote("regular", [item("hoodie", 3)], "delivery")
        self.assertEqual(quote["subtotal_cents"], 12000)
        self.assertEqual(quote["discount_cents"], 0)
        self.assertEqual(quote["delivery_cents"], 0)
        self.assertEqual(quote["total_cents"], 12000)

    def test_quote_lines_contain_required_fields(self):
        quote = self.service.quote("student", [item("pen-pack", 2)])
        self.assertEqual(quote["customer_type"], "student")
        self.assertEqual(quote["fulfillment"], "pickup")
        self.assertEqual(quote["items"], [{
            "product_id": "pen-pack", "name": "Pen pack",
            "unit_price_cents": 750, "quantity": 2, "line_total_cents": 1500,
        }])

    def test_list_orders_keeps_placement_order_including_cancelled(self):
        first = self.service.place_order("regular", [item("notebook", 1)])
        second = self.service.place_order("regular", [item("mug", 1)])
        self.service.cancel_order(first["order_id"])
        ids = [o["order_id"] for o in self.service.list_orders()]
        statuses = [o["status"] for o in self.service.list_orders()]
        self.assertEqual(ids, [first["order_id"], second["order_id"]])
        self.assertEqual(statuses, ["cancelled", "placed"])


# ---------------------------------------------------------------- 2. Boundary
class BoundaryBehaviourTests(ServiceTestCase):
    BIG_CATALOG = [{"product_id": "widget", "name": "Widget", "unit_price_cents": 100, "stock": 500}]

    def test_quantity_1_and_99_are_accepted(self):
        self.write_state(self.BIG_CATALOG)
        self.assertEqual(self.service.quote("regular", [item("widget", 1)])["subtotal_cents"], 100)
        self.assertEqual(self.service.quote("regular", [item("widget", 99)])["subtotal_cents"], 9900)

    def test_quantity_0_and_100_are_rejected(self):
        self.write_state(self.BIG_CATALOG)
        for quantity in (0, 100):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.service.quote("regular", [item("widget", quantity)])

    def test_buying_exactly_all_stock_then_one_more_is_rejected(self):
        self.service.place_order("regular", [item("bag", 4)])
        self.assertEqual(self.stock_of("bag"), 0)
        with self.assertRaises(ValueError):
            self.service.quote("regular", [item("bag", 1)])

    def test_empty_item_list_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.quote("regular", [])

    def test_student_subtotal_just_below_5000_gets_no_discount(self):
        quote = self.service.quote("student", [item("notebook", 9)])  # 4500
        self.assertEqual(quote["discount_cents"], 0)

    def test_student_subtotal_exactly_5000_gets_discount(self):
        # Spec: discount applies when subtotal is AT LEAST 5,000 cents.
        quote = self.service.quote("student", [item("notebook", 10)])  # 5000
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["total_cents"], 4500)

    def test_discount_half_cent_rounds_up(self):
        self.write_state([{"product_id": "odd", "name": "Odd", "unit_price_cents": 5005, "stock": 5}])
        quote = self.service.quote("student", [item("odd", 1)])  # 10% = 500.5
        self.assertEqual(quote["discount_cents"], 501)

    def test_delivery_free_at_exactly_10000_after_discount(self):
        quote = self.service.quote("regular", [item("bag", 4)], "delivery")  # 10000
        self.assertEqual(quote["delivery_cents"], 0)
        self.assertEqual(quote["total_cents"], 10000)

    def test_delivery_charged_just_below_10000(self):
        quote = self.service.quote("regular", [item("hoodie", 2), item("mug", 1)], "delivery")  # 9500
        self.assertEqual(quote["delivery_cents"], 600)
        self.assertEqual(quote["total_cents"], 10100)


# ---------------------------------------------------------------- 3. Invalid
class InvalidBehaviourTests(ServiceTestCase):
    def test_invalid_customer_types_are_rejected(self):
        for customer in ("vip", "", 1, None, "Student"):
            with self.subTest(customer=customer), self.assertRaises(ValueError):
                self.service.quote(customer, [item("notebook", 1)])

    def test_invalid_fulfillment_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.quote("regular", [item("notebook", 1)], "shipping")

    def test_unknown_product_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.quote("regular", [item("laptop", 1)])

    def test_non_integer_quantities_are_rejected(self):
        for quantity in ("2", 2.0, True, None):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.service.quote("regular", [item("notebook", quantity)])

    def test_item_that_is_not_a_dict_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.quote("regular", ["notebook:2"])

    def test_invalid_placement_changes_nothing(self):
        self.service.place_order("regular", [item("notebook", 1)])
        before = self.saved_text()
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("notebook", 1), item("laptop", 1)])
        self.assertEqual(self.saved_text(), before)
        self.assertEqual(self.service.place_order("regular", [item("mug", 1)])["order_id"], "ORD-0002")

    def test_unknown_order_id_raises_for_get_and_cancel(self):
        self.service.place_order("regular", [item("notebook", 1)])
        before = self.saved_text()
        with self.assertRaises(ValueError):
            self.service.get_order("ORD-9999")
        with self.assertRaises(ValueError):
            self.service.cancel_order("ORD-9999")
        self.assertEqual(self.saved_text(), before)

    def test_duplicate_lines_exceeding_stock_are_rejected(self):
        # Spec: combined quantity of a repeated product must not exceed stock (bag stock = 4).
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("bag", 3), item("bag", 2)])
        self.assertEqual(self.stock_of("bag"), 4)

    def test_cancelling_twice_does_not_add_extra_stock(self):
        # Spec: cancelling an already cancelled order returns it without changing stock.
        order = self.service.place_order("regular", [item("mug", 2)])
        self.service.cancel_order(order["order_id"])
        again = self.service.cancel_order(order["order_id"])
        self.assertEqual(again["status"], "cancelled")
        self.assertEqual(self.stock_of("mug"), 8)

    def test_malformed_save_file_raises_instead_of_resetting(self):
        self.path.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.service.catalog()
        self.assertEqual(self.saved_text(), "{ not json")


# ---------------------------------------------------------------- 4. Preserve
class PreservedBehaviourTests(ServiceTestCase):
    def test_quote_matches_subsequent_placed_order(self):
        request = ("student", [item("hoodie", 1), item("bag", 1), item("pen-pack", 2)], "delivery")
        quote = self.service.quote(*request)
        order = self.service.place_order(*request)
        for key in quote:
            with self.subTest(key=key):
                self.assertEqual(order[key], quote[key])

    def test_quote_does_not_create_save_file_or_change_stock(self):
        self.service.quote("regular", [item("notebook", 5)])
        self.assertFalse(self.path.exists())
        self.assertEqual(self.stock_of("notebook"), 20)

    def test_quote_does_not_modify_existing_save_file(self):
        self.service.place_order("regular", [item("notebook", 1)])
        before = self.saved_text()
        self.service.quote("student", [item("hoodie", 2)], "delivery")
        self.assertEqual(self.saved_text(), before)

    def test_order_ids_increase_and_are_not_reused_after_cancel(self):
        first = self.service.place_order("regular", [item("notebook", 1)])
        self.service.cancel_order(first["order_id"])
        second = self.service.place_order("regular", [item("notebook", 1)])
        self.assertEqual([first["order_id"], second["order_id"]], ["ORD-0001", "ORD-0002"])

    def test_reopening_preserves_history_and_stock(self):
        order = self.service.place_order("student", [item("hoodie", 2)], "delivery")
        reopened = OrderService(self.path)
        self.assertEqual(reopened.list_orders(), [order])
        self.assertEqual(reopened.catalog(), self.service.catalog())
        self.assertEqual(self.stock_of("hoodie"), 3)

    def test_historical_prices_are_not_recalculated(self):
        order = self.service.place_order("regular", [item("mug", 1)])
        state = json.loads(self.saved_text())
        for product in state["catalog"]:
            product["unit_price_cents"] *= 2
        self.path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.service.get_order(order["order_id"])["total_cents"], 1500)

    def test_cancel_keeps_original_items_and_totals(self):
        order = self.service.place_order("student", [item("hoodie", 2)], "delivery")
        cancelled = self.service.cancel_order(order["order_id"])
        for key in ("items", "subtotal_cents", "discount_cents", "delivery_cents", "total_cents"):
            self.assertEqual(cancelled[key], order[key])


# ---------------------------------------------------------------- Interfaces
class InterfaceTests(ServiceTestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = cli.main(["--data", str(self.path), *args])
        return status, out.getvalue(), err.getvalue()

    def run_menu(self, *answers):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=list(answers)), contextlib.redirect_stdout(out):
            status = menu.run_menu(self.service)
        return status, out.getvalue()

    def test_cli_quote_prints_json_and_exits_0(self):
        status, out, _ = self.run_cli("quote", "--customer", "regular", "--item", "notebook:2")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["total_cents"], 1000)

    def test_cli_rejected_request_exits_2(self):
        status, _, err = self.run_cli("place", "--item", "laptop:1")
        self.assertEqual(status, 2)
        self.assertIn("Error", err)
        self.assertFalse(self.path.exists())

    def test_menu_quote_with_defaults_shows_total(self):
        # option 2, blank customer, notebook x2, finish, blank fulfillment, exit
        status, out = self.run_menu("2", "", "notebook", "2", "", "", "0")
        self.assertEqual(status, 0)
        self.assertIn("Total: $10.00", out)
        self.assertFalse(self.path.exists())

    def test_menu_declining_placement_saves_nothing(self):
        status, out = self.run_menu("3", "", "mug", "1", "", "", "n", "0")
        self.assertEqual(status, 0)
        self.assertIn("Order not placed.", out)
        self.assertFalse(self.path.exists())

    def test_menu_bad_quantity_text_asks_again(self):
        status, out = self.run_menu("2", "", "mug", "two", "mug", "1", "", "", "0")
        self.assertIn("Please enter a whole number", out)
        self.assertIn("Total: $15.00", out)


if __name__ == "__main__":
    unittest.main()
