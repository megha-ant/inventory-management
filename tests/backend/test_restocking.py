"""
Tests for restocking API endpoints (recommendations + submitted restock orders).
"""
import re

import pytest

# Mirrors the per-category delivery lead times defined for the restocking feature.
# Duplicated here on purpose so the tests assert the agreed product requirement,
# not just whatever constant happens to live in main.py.
EXPECTED_LEAD_TIMES = {
    "Circuit Boards": 14,
    "Controllers": 12,
    "Sensors": 7,
    "Actuators": 7,
    "Power Supplies": 10,
}
DEFAULT_LEAD_TIME_DAYS = 10

REQUIRED_RECOMMENDATION_FIELDS = [
    "sku",
    "name",
    "category",
    "current_stock",
    "forecasted_demand",
    "shortfall_units",
    "unit_cost",
    "recommended_quantity",
    "line_cost",
    "lead_time_days",
]


class TestRestockingRecommendations:
    """Test suite for GET /api/restocking/recommendations."""

    def test_get_all_recommendations(self, client):
        """Test getting all restocking recommendations."""
        response = client.get("/api/restocking/recommendations")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        for recommendation in data:
            for field in REQUIRED_RECOMMENDATION_FIELDS:
                assert field in recommendation

    def test_recommendation_field_types(self, client):
        """Test that recommendation fields have proper types and ranges."""
        response = client.get("/api/restocking/recommendations")
        data = response.json()

        for rec in data:
            assert isinstance(rec["sku"], str)
            assert isinstance(rec["name"], str)
            assert rec["category"] is None or isinstance(rec["category"], str)
            assert isinstance(rec["current_stock"], int)
            assert isinstance(rec["forecasted_demand"], int)
            assert isinstance(rec["shortfall_units"], int)
            assert isinstance(rec["unit_cost"], (int, float))
            assert isinstance(rec["recommended_quantity"], int)
            assert isinstance(rec["line_cost"], (int, float))
            assert isinstance(rec["lead_time_days"], int)

            assert rec["current_stock"] >= 0
            assert rec["unit_cost"] > 0
            assert rec["lead_time_days"] > 0

    def test_recommendation_shortfall_calculation(self, client):
        """Test that shortfall is forecasted demand minus current stock and always positive."""
        response = client.get("/api/restocking/recommendations")
        data = response.json()

        for rec in data:
            assert rec["shortfall_units"] == rec["forecasted_demand"] - rec["current_stock"]
            assert rec["shortfall_units"] > 0
            # Recommended quantity covers the full shortfall (no partial quantities)
            assert rec["recommended_quantity"] == rec["shortfall_units"]

    def test_recommendation_line_cost_calculation(self, client):
        """Test that line cost equals recommended quantity times unit cost."""
        response = client.get("/api/restocking/recommendations")
        data = response.json()

        for rec in data:
            calculated_cost = rec["recommended_quantity"] * rec["unit_cost"]
            assert abs(rec["line_cost"] - calculated_cost) < 0.01

    def test_recommendations_sorted_by_shortfall(self, client):
        """Test that recommendations are sorted by largest shortfall first."""
        response = client.get("/api/restocking/recommendations")
        data = response.json()

        shortfalls = [rec["shortfall_units"] for rec in data]
        assert shortfalls == sorted(shortfalls, reverse=True)

    def test_recommendations_exclude_fully_stocked_items(self, client):
        """Test that forecast items with enough stock on hand are not recommended."""
        forecasts = client.get("/api/demand").json()
        inventory = client.get("/api/inventory").json()
        recommendations = client.get("/api/restocking/recommendations").json()

        recommended_skus = {rec["sku"] for rec in recommendations}

        for forecast in forecasts:
            stock_on_hand = sum(
                item["quantity_on_hand"]
                for item in inventory
                if item["sku"] == forecast["item_sku"]
            )
            if stock_on_hand >= forecast["forecasted_demand"]:
                # Fully stocked items (e.g. PSU-501 in the current data) must be excluded
                assert forecast["item_sku"] not in recommended_skus
            else:
                assert forecast["item_sku"] in recommended_skus

    def test_recommendation_lead_times_match_categories(self, client):
        """Test that lead times follow the per-category lookup with a default fallback."""
        response = client.get("/api/restocking/recommendations")
        data = response.json()

        for rec in data:
            expected = EXPECTED_LEAD_TIMES.get(rec["category"], DEFAULT_LEAD_TIME_DAYS)
            assert rec["lead_time_days"] == expected


class TestRestockingOrders:
    """Test suite for POST/GET /api/restocking/orders."""

    def _build_valid_payload(self, client, budget=10000, line_count=2):
        """Build a valid create-order payload from the live recommendations."""
        recommendations = client.get("/api/restocking/recommendations").json()
        assert len(recommendations) >= line_count

        return {
            "budget": budget,
            "items": [
                {"sku": rec["sku"], "quantity": rec["recommended_quantity"]}
                for rec in recommendations[:line_count]
            ],
        }

    def test_create_restock_order(self, client):
        """Test submitting a valid restock order returns 201 with the full order."""
        payload = self._build_valid_payload(client)

        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert re.match(r"^RST-2025-\d{4}$", order["order_number"])
        assert order["status"] == "Submitted"
        assert order["budget"] == payload["budget"]
        assert len(order["items"]) == len(payload["items"])

        # Dates are ISO strings and delivery is after the order date
        assert "T" in order["order_date"]
        assert "T" in order["expected_delivery"]
        assert order["expected_delivery"] > order["order_date"]

        for item in order["items"]:
            assert item["lead_time_days"] > 0
            assert abs(item["line_cost"] - item["quantity"] * item["unit_cost"]) < 0.01

        calculated_total = sum(item["line_cost"] for item in order["items"])
        assert abs(order["total_cost"] - calculated_total) < 0.01

    def test_created_order_appears_in_list(self, client):
        """Test that a submitted order shows up in the restock orders list."""
        payload = self._build_valid_payload(client, budget=5000, line_count=1)

        created = client.post("/api/restocking/orders", json=payload).json()

        response = client.get("/api/restocking/orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        # Assert membership rather than list length: the in-memory restock_orders list
        # accumulates across tests within a session, so absolute counts are not stable.
        order_numbers = [order["order_number"] for order in data]
        assert created["order_number"] in order_numbers

    def test_create_restock_order_empty_items(self, client):
        """Test that an order with no items is rejected."""
        response = client.post(
            "/api/restocking/orders", json={"budget": 1000, "items": []}
        )
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "at least one item" in data["detail"].lower()

    def test_create_restock_order_unknown_sku(self, client):
        """Test that an order referencing a non-forecast SKU is rejected."""
        response = client.post(
            "/api/restocking/orders",
            json={"budget": 1000, "items": [{"sku": "NOT-A-SKU", "quantity": 5}]},
        )
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "not a restocking candidate" in data["detail"].lower()

    def test_create_restock_order_invalid_quantity(self, client):
        """Test that non-positive quantities fail validation."""
        response = client.post(
            "/api/restocking/orders",
            json={"budget": 1000, "items": [{"sku": "WDG-001", "quantity": 0}]},
        )
        assert response.status_code == 422

    def test_create_restock_order_negative_budget(self, client):
        """Test that a negative budget fails validation."""
        response = client.post(
            "/api/restocking/orders",
            json={"budget": -100, "items": [{"sku": "WDG-001", "quantity": 5}]},
        )
        assert response.status_code == 422
