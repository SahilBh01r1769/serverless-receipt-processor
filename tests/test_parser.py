"""Focused parser regression tests.

These are small, sanitized scenarios based on failure classes seen while testing
receipts in the deployed application. They test only the custom parsing logic;
Amazon Textract remains the OCR engine in the live AWS workflow.
"""

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "lambdas"
    / "review-categorize"
    / "lambda_function.py"
)

spec = importlib.util.spec_from_file_location("receipt_parser", MODULE_PATH)
receipt_parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipt_parser)


class ReceiptParserRegressionTests(unittest.TestCase):
    def parse(self, text):
        return receipt_parser.parse_receipt_text(text)

    def test_final_total_beats_subtotal_and_tax_values(self):
        result = self.parse(
            """LOCAL MARKET
DATE 11/06/2026
SUBTOTAL 820.00
CGST 24.60
SGST 24.60
TOTAL 869.20"""
        )
        self.assertEqual(result["total"], 869.20)
        self.assertEqual(result["meta"]["total_strategy"], "labeled_line")

    def test_grand_total_beats_earlier_plain_total(self):
        result = self.parse(
            """CAFE TEST
TOTAL 470.00
SERVICE CHARGE 10.00
TAX 18.20
GRAND TOTAL 498.20"""
        )
        self.assertEqual(result["total"], 498.20)

    def test_labeled_total_beats_larger_item_price(self):
        result = self.parse(
            """TEST STORE
PREMIUM ITEM ₹999.00
DISCOUNT 600.00
TOTAL ₹399.00"""
        )
        self.assertEqual(result["total"], 399.00)

    def test_currency_fallback_is_used_when_no_total_label_exists(self):
        result = self.parse(
            """TEST STORE
ITEM A Rs. 120.00
ITEM B Rs. 180.00
INR 300.00"""
        )
        self.assertEqual(result["total"], 300.00)
        self.assertEqual(result["meta"]["total_strategy"], "largest_currency_amount")

    def test_common_indian_date_and_known_vendor(self):
        result = self.parse(
            """DMART
DATE: 11/06/2026
TOTAL Rs. 1249.50"""
        )
        self.assertEqual(result["vendor"], "DMART")
        self.assertEqual(result["date"], "2026-06-11")
        self.assertEqual(receipt_parser.auto_categorize(result), "Groceries")


if __name__ == "__main__":
    unittest.main()
