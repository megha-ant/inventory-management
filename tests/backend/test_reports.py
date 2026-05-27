"""
Tests for reports API endpoints (GET /api/reports/quarterly, GET /api/reports/monthly-trends),
including the global filters (warehouse, category, status, month).
"""
import pytest

REQUIRED_QUARTERLY_FIELDS = [
    "quarter",
    "total_orders",
    "total_revenue",
    "delivered_orders",
    "avg_order_value",
    "fulfillment_rate",
]

REQUIRED_MONTHLY_FIELDS = ["month", "order_count", "revenue", "delivered_count"]


class TestQuarterlyReports:
    """Test suite for GET /api/reports/quarterly."""

    def test_get_quarterly_reports(self, client):
        """Test getting quarterly reports without filters."""
        response = client.get("/api/reports/quarterly")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 4  # Q1-Q4 2025

        for quarter in data:
            for field in REQUIRED_QUARTERLY_FIELDS:
                assert field in quarter

    def test_quarterly_reports_sorted_by_quarter(self, client):
        """Test that quarters come back in chronological order."""
        data = client.get("/api/reports/quarterly").json()
        quarters = [q["quarter"] for q in data]
        assert quarters == sorted(quarters)

    def test_quarterly_totals_match_orders(self, client):
        """Test that quarterly order counts and revenue add up to the full orders list."""
        orders = client.get("/api/orders").json()
        data = client.get("/api/reports/quarterly").json()

        assert sum(q["total_orders"] for q in data) == len(orders)
        total_revenue = sum(q["total_revenue"] for q in data)
        expected_revenue = sum(order["total_value"] for order in orders)
        assert abs(total_revenue - expected_revenue) < 0.01

    def test_quarterly_avg_order_value_calculation(self, client):
        """Test that average order value is revenue divided by order count."""
        data = client.get("/api/reports/quarterly").json()

        for q in data:
            if q["total_orders"] > 0:
                expected = q["total_revenue"] / q["total_orders"]
                assert abs(q["avg_order_value"] - expected) < 0.01

    def test_quarterly_reports_warehouse_filter(self, client):
        """Test filtering quarterly reports by warehouse."""
        response = client.get("/api/reports/quarterly?warehouse=Tokyo")
        assert response.status_code == 200

        data = response.json()
        tokyo_orders = client.get("/api/orders?warehouse=Tokyo").json()
        assert sum(q["total_orders"] for q in data) == len(tokyo_orders)

    def test_quarterly_reports_status_filter(self, client):
        """Test filtering quarterly reports by status."""
        data = client.get("/api/reports/quarterly?status=Delivered").json()

        for q in data:
            # Every order included is delivered, so fulfillment rate must be 100%
            assert q["total_orders"] == q["delivered_orders"]
            assert q["fulfillment_rate"] == 100.0

    def test_quarterly_reports_month_filter(self, client):
        """Test filtering quarterly reports by a single month."""
        data = client.get("/api/reports/quarterly?month=2025-01").json()

        # Only Q1 should remain when filtering to January
        assert len(data) == 1
        assert data[0]["quarter"] == "Q1-2025"

        january_orders = client.get("/api/orders?month=2025-01").json()
        assert data[0]["total_orders"] == len(january_orders)

    def test_quarterly_reports_all_filter_values(self, client):
        """Test that explicit 'all' filter values behave like no filter."""
        unfiltered = client.get("/api/reports/quarterly").json()
        all_filters = client.get(
            "/api/reports/quarterly?warehouse=all&category=all&status=all&month=all"
        ).json()
        assert unfiltered == all_filters


class TestMonthlyTrends:
    """Test suite for GET /api/reports/monthly-trends."""

    def test_get_monthly_trends(self, client):
        """Test getting monthly trends without filters."""
        response = client.get("/api/reports/monthly-trends")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 12  # Jan-Dec 2025

        for month in data:
            for field in REQUIRED_MONTHLY_FIELDS:
                assert field in month

    def test_monthly_trends_sorted_by_month(self, client):
        """Test that months come back in chronological order."""
        data = client.get("/api/reports/monthly-trends").json()
        months = [m["month"] for m in data]
        assert months == sorted(months)

    def test_monthly_totals_match_orders(self, client):
        """Test that monthly order counts add up to the full orders list."""
        orders = client.get("/api/orders").json()
        data = client.get("/api/reports/monthly-trends").json()
        assert sum(m["order_count"] for m in data) == len(orders)

    def test_monthly_trends_warehouse_filter(self, client):
        """Test filtering monthly trends by warehouse."""
        data = client.get("/api/reports/monthly-trends?warehouse=London").json()
        london_orders = client.get("/api/orders?warehouse=London").json()
        assert sum(m["order_count"] for m in data) == len(london_orders)

    def test_monthly_trends_category_filter(self, client):
        """Test filtering monthly trends by category."""
        data = client.get("/api/reports/monthly-trends?category=Sensors").json()
        sensor_orders = client.get("/api/orders?category=Sensors").json()
        assert sum(m["order_count"] for m in data) == len(sensor_orders)

    def test_monthly_trends_month_filter(self, client):
        """Test filtering monthly trends to a single month."""
        data = client.get("/api/reports/monthly-trends?month=2025-03").json()

        assert len(data) == 1
        assert data[0]["month"] == "2025-03"

        march_orders = client.get("/api/orders?month=2025-03").json()
        assert data[0]["order_count"] == len(march_orders)

    def test_monthly_trends_combined_filters(self, client):
        """Test combining warehouse and status filters."""
        data = client.get(
            "/api/reports/monthly-trends?warehouse=San Francisco&status=Delivered"
        ).json()
        matching_orders = client.get(
            "/api/orders?warehouse=San Francisco&status=Delivered"
        ).json()
        assert sum(m["order_count"] for m in data) == len(matching_orders)
        # Delivered-only data means delivered_count equals order_count everywhere
        for m in data:
            assert m["order_count"] == m["delivered_count"]
