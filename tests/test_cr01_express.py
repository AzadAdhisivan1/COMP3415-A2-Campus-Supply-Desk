"""CR-01 Express Delivery acceptance tests (expected values from CR-01.md)."""

import contextlib
import io
import json
import unittest
from unittest import mock

from supplydesk import cli, menu
from supplydesk.service import OrderService
from tests.test_safety_net import ServiceTestCase, item


class ExpressPricingTests(ServiceTestCase):
    def test_regular_two_notebooks_express_is_22_dollars(self):
        quote = self.service.quote("regular", [item("notebook", 2)], "express")
        self.assertEqual(quote["fulfillment"], "express")
        self.assertEqual(quote["subtotal_cents"], 1000)
        self.assertEqual(quote["delivery_cents"], 1200)
        self.assertEqual(quote["total_cents"], 2200)

    def test_student_two_hoodies_express_discount_on_merchandise_only(self):
        quote = self.service.quote("student", [item("hoodie", 2)], "express")
        self.assertEqual(quote["discount_cents"], 800)  # 10% of 8000, not of 9200
        self.assertEqual(quote["delivery_cents"], 1200)
        self.assertEqual(quote["total_cents"], 8400)

    def test_three_hoodies_standard_120_vs_express_132(self):
        standard = self.service.quote("regular", [item("hoodie", 3)], "delivery")
        express = self.service.quote("regular", [item("hoodie", 3)], "express")
        self.assertEqual(standard["total_cents"], 12000)
        self.assertEqual(express["delivery_cents"], 1200)  # never waived
        self.assertEqual(express["total_cents"], 13200)

    def test_express_fee_not_waived_at_exactly_10000(self):
        quote = self.service.quote("regular", [item("bag", 4)], "express")
        self.assertEqual(quote["delivery_cents"], 1200)

    def test_student_discount_threshold_unchanged_for_express(self):
        below = self.service.quote("student", [item("notebook", 9)], "express")   # 4500
        at = self.service.quote("student", [item("notebook", 10)], "express")     # 5000
        self.assertEqual(below["discount_cents"], 0)
        self.assertEqual(at["discount_cents"], 500)

    def test_pickup_and_standard_delivery_unchanged(self):
        self.assertEqual(self.service.quote("regular", [item("notebook", 2)])["delivery_cents"], 0)
        self.assertEqual(self.service.quote("regular", [item("notebook", 2)], "delivery")["delivery_cents"], 600)


class ExpressOrderLifecycleTests(ServiceTestCase):
    REQUEST = ("student", [item("hoodie", 2), item("mug", 1)], "express")

    def test_express_quote_matches_placed_order(self):
        quote = self.service.quote(*self.REQUEST)
        order = self.service.place_order(*self.REQUEST)
        for key in quote:
            with self.subTest(key=key):
                self.assertEqual(order[key], quote[key])

    def test_express_order_survives_reopen_and_cancel(self):
        order = self.service.place_order(*self.REQUEST)
        self.assertEqual(OrderService(self.path).get_order(order["order_id"]), order)
        cancelled = OrderService(self.path).cancel_order(order["order_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        for key in ("fulfillment", "items", "discount_cents", "delivery_cents", "total_cents"):
            self.assertEqual(cancelled[key], order[key])
        self.assertEqual(self.stock_of("hoodie"), 5)
        self.assertEqual(self.stock_of("mug"), 8)

    def test_express_uses_normal_numbering_and_stock(self):
        first = self.service.place_order("regular", [item("bag", 1)], "express")
        second = self.service.place_order("regular", [item("bag", 1)], "pickup")
        self.assertEqual([first["order_id"], second["order_id"]], ["ORD-0001", "ORD-0002"])
        self.assertEqual(self.stock_of("bag"), 2)

    def test_other_fulfillment_values_still_invalid(self):
        for value in ("Express", "EXPRESS", "shipping", "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.service.quote("regular", [item("notebook", 1)], value)


class ExpressInterfaceTests(ServiceTestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = cli.main(["--data", str(self.path), *args])
        return status, out.getvalue(), err.getvalue()

    def test_cli_express_quote_matches_cr01_example(self):
        status, out, _ = self.run_cli("quote", "--customer", "student",
                                      "--fulfillment", "express", "--item", "hoodie:2")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["total_cents"], 8400)

    def test_cli_help_lists_express(self):
        help_text = cli.build_parser()._subparsers._group_actions[0].choices["quote"].format_help()
        self.assertIn("express", help_text)

    def test_cli_default_fulfillment_still_pickup(self):
        status, out, _ = self.run_cli("quote", "--item", "notebook:2")
        self.assertEqual(json.loads(out)["fulfillment"], "pickup")

    def test_menu_accepts_express_and_prompt_mentions_it(self):
        prompts = []
        answers = iter(["2", "", "notebook", "2", "", "express", "0"])

        def fake_input(prompt=""):
            prompts.append(prompt)
            return next(answers)

        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=fake_input), contextlib.redirect_stdout(out):
            menu.run_menu(self.service)
        self.assertTrue(any("express" in p for p in prompts if "Fulfillment" in p))
        self.assertIn("Delivery: $12.00", out.getvalue())
        self.assertIn("Total: $22.00", out.getvalue())


if __name__ == "__main__":
    unittest.main()
