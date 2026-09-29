"""No-network parser regression and fail-closed integrity tests for ST C5 capture."""
from __future__ import annotations
import unittest
from acquire_st_c5_estore import parse_html


def fixture(ids, facet=172, pages=18, status="Active", series="STM32C5 series"):
    cards = "\n".join(
        '<li class="item product product-item"><div><span class="marketing">'
        f'{status}</span><strong class="product name product-item-name">'
        f'<a href="/en/{identity}.html">{identity}</a></strong>'
        '<span class="stock">Coming Soon</span></div></li>'
        for identity in ids
    )
    return (
        f'<!doctype html><html><body><h1>{series}</h1>'
        f'<ol class="products list items product-items">{cards}</ol>'
        f'<div class="pages">Page 1 of {pages}</div>'
        f'<aside>Marketing Status Active {facet}item</aside></body></html>'
    ).encode()


class C5ParserTests(unittest.TestCase):
    def setUp(self):
        self.ten = [f"STM32C531CBT{n:02d}" for n in range(10)]
        self.two = ["STM32C5A3VGT6", "STM32C5A3ZGT6"]

    def blocked(self, raw, page):
        with self.assertRaises(ValueError):
            parse_html(raw, page)

    def test_first_seventeen_pages_expect_ten(self):
        for page in (1, 2, 17):
            self.assertEqual(self.ten, parse_html(fixture(self.ten), page))

    def test_eighteenth_page_two(self):
        self.assertEqual(self.two, parse_html(fixture(self.two), 18))

    def test_active_can_have_coming_soon_stock(self):
        self.assertEqual(2, len(parse_html(fixture(self.two), 18)))

    def test_page_count_mismatch(self):
        self.blocked(fixture(self.two, pages=17), 18)

    def test_facet_mismatch(self):
        self.blocked(fixture(self.ten, facet=171), 1)

    def test_nonactive(self):
        self.blocked(fixture(self.two, status="NRND"), 18)

    def test_malformed_identity_not_inferred(self):
        self.blocked(fixture(self.two + ["STM32C5A3VGTX"]), 18)

    def test_duplicate_identity(self):
        self.blocked(fixture([self.ten[0]] * 10), 1)

    def test_out_of_scope_page(self):
        self.blocked(fixture(self.two, series="STM32H5 series"), 18)

    def test_card_without_identity(self):
        self.blocked(fixture([self.two[0], "nonexistant"]), 18)

    def test_wrong_row_count(self):
        self.blocked(fixture(self.ten), 18)


if __name__ == "__main__":
    unittest.main()
