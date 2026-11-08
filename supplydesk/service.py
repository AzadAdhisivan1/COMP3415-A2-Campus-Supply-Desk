"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore

CUSTOMER_TYPES = ("regular", "student")
FULFILLMENT_OPTIONS = ("pickup", "delivery", "express")
MIN_QUANTITY = 1
MAX_QUANTITY = 99
STUDENT_DISCOUNT_THRESHOLD_CENTS = 5000
STUDENT_DISCOUNT_PERCENT = 10
DELIVERY_FEE_CENTS = 600
FREE_DELIVERY_THRESHOLD_CENTS = 10000
EXPRESS_DELIVERY_FEE_CENTS = 1200  # CR-01: flat fee, never waived
ORDER_ID_PREFIX = "ORD-"
ORDER_NUMBER_DIGITS = 4


class OrderService:
    def __init__(self, state_path=".supplydesk/state.json"):
        self.store = JsonStore(state_path)

    def catalog(self):
        return self.store.load()["catalog"]

    def quote(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        return self._price_request(state, customer_type, items, fulfillment)

    def place_order(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        priced = self._price_request(state, customer_type, items, fulfillment)
        order = {"order_id": self._next_order_id(state), "status": "placed", **priced}
        self._adjust_stock(state, order["items"], -1)
        state["next_order_number"] += 1
        state["orders"].append(order)
        self.store.save(state)
        return order

    # ----- request validation and pricing (shared by quote and place_order) -----

    def _price_request(self, state, customer_type, items, fulfillment):
        """Validate a request against current stock and return its priced lines and totals."""
        self._validate_options(customer_type, fulfillment, items)
        lines = []
        requested = {}  # combined quantity per product across repeated lines
        for item in items:
            line = self._build_line(state, item, requested)
            requested[line["product_id"]] = requested.get(line["product_id"], 0) + line["quantity"]
            lines.append(line)
        return {
            "customer_type": customer_type,
            "fulfillment": fulfillment,
            "items": lines,
            **self._calculate_totals(customer_type, fulfillment, lines),
        }

    @staticmethod
    def _validate_options(customer_type, fulfillment, items):
        if customer_type not in CUSTOMER_TYPES:
            raise ValueError("Customer type must be regular or student.")
        if fulfillment not in FULFILLMENT_OPTIONS:
            raise ValueError("Fulfillment must be pickup, delivery, or express.")
        if not isinstance(items, list) or not items:
            raise ValueError("An order must contain at least one item.")

    def _build_line(self, state, item, requested):
        """Validate one requested item and return its priced order line.

        ``requested`` holds quantities already requested on earlier lines, so a
        product repeated on several lines cannot exceed its stock in total.
        """
        if not isinstance(item, dict):
            raise ValueError("Each item must contain a product_id and quantity.")
        product = self._find_product(state, item.get("product_id"))
        if product is None:
            raise ValueError("Unknown product.")
        quantity = item.get("quantity")
        # Exact type check on purpose: isinstance() would accept True/False (bool is an int subclass).
        if type(quantity) is not int or quantity < MIN_QUANTITY or quantity > MAX_QUANTITY:
            raise ValueError("Quantity must be an integer from 1 to 99.")
        if quantity + requested.get(product["product_id"], 0) > product["stock"]:
            raise ValueError("Not enough stock for " + product["product_id"] + ".")
        return {
            "product_id": product["product_id"],
            "name": product["name"],
            "unit_price_cents": product["unit_price_cents"],
            "quantity": quantity,
            "line_total_cents": product["unit_price_cents"] * quantity,
        }

    @staticmethod
    def _calculate_totals(customer_type, fulfillment, lines):
        subtotal = sum(line["line_total_cents"] for line in lines)
        discount = 0
        if customer_type == "student" and subtotal >= STUDENT_DISCOUNT_THRESHOLD_CENTS:
            discount = (subtotal * STUDENT_DISCOUNT_PERCENT + 50) // 100  # round half up
        delivery = OrderService._delivery_fee(fulfillment, subtotal - discount)
        return {
            "subtotal_cents": subtotal,
            "discount_cents": discount,
            "delivery_cents": delivery,
            "total_cents": subtotal - discount + delivery,
        }

    @staticmethod
    def _delivery_fee(fulfillment, merchandise_after_discount):
        if fulfillment == "express":
            return EXPRESS_DELIVERY_FEE_CENTS
        if fulfillment == "delivery" and merchandise_after_discount < FREE_DELIVERY_THRESHOLD_CENTS:
            return DELIVERY_FEE_CENTS
        return 0

    # ----- small state helpers -----

    @staticmethod
    def _find_product(state, product_id):
        for product in state["catalog"]:
            if product["product_id"] == product_id:
                return product
        return None

    @staticmethod
    def _next_order_id(state):
        return ORDER_ID_PREFIX + str(state["next_order_number"]).zfill(ORDER_NUMBER_DIGITS)

    def _adjust_stock(self, state, lines, direction):
        """Add (direction=+1) or remove (direction=-1) each line's quantity from stock."""
        for line in lines:
            product = self._find_product(state, line["product_id"])
            if product is not None:
                product["stock"] += direction * line["quantity"]

    def list_orders(self):
        return self.store.load()["orders"]

    def get_order(self, order_id):
        state = self.store.load()
        for order in state["orders"]:
            if order["order_id"] == order_id:
                return order
        raise ValueError("Unknown order: " + order_id)

    def cancel_order(self, order_id):
        state = self.store.load()
        order = None
        for candidate in state["orders"]:
            if candidate["order_id"] == order_id:
                order = candidate
                break
        if order is None:
            raise ValueError("Unknown order: " + order_id)
        if order["status"] == "cancelled":
            return order  # already cancelled: do not restore stock again
        self._adjust_stock(state, order["items"], +1)
        order["status"] = "cancelled"
        self.store.save(state)
        return order
