"""
Tests for purchase order API endpoints (POST /api/purchase-orders,
GET /api/purchase-orders/{backlog_item_id}) and their effect on /api/backlog.
"""
import re

import pytest

import mock_data

REQUIRED_PO_FIELDS = [
    "id",
    "backlog_item_id",
    "supplier_name",
    "quantity",
    "unit_cost",
    "expected_delivery_date",
    "status",
    "created_date",
    "notes",
]


@pytest.fixture(autouse=True)
def reset_purchase_orders_state():
    """Snapshot and restore the in-memory purchase orders list around each test.

    Purchase orders are limited to one per backlog item (409 on duplicates), so
    without this reset later tests would fail purely because of execution order.
    """
    saved_orders = list(mock_data.purchase_orders)
    yield
    mock_data.purchase_orders[:] = saved_orders


class TestPurchaseOrderEndpoints:
    """Test suite for purchase-order-related endpoints."""

    def _build_payload(self, client, **overrides):
        """Build a valid create-PO payload from the first backlog item without a PO."""
        backlog = client.get("/api/backlog").json()
        item = next(b for b in backlog if not b["has_purchase_order"])

        payload = {
            "backlog_item_id": item["id"],
            "supplier_name": "Industrial Supply Co",
            "quantity": item["quantity_needed"] - item["quantity_available"],
            "unit_cost": 12.5,
            "expected_delivery_date": "2025-10-20",
            "notes": "Expedited to cover the shortage",
        }
        payload.update(overrides)
        return payload

    def test_create_purchase_order(self, client):
        """Test creating a purchase order returns 201 with the full PO."""
        payload = self._build_payload(client)

        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 201

        po = response.json()
        for field in REQUIRED_PO_FIELDS:
            assert field in po

        assert re.match(r"^PO-2025-\d{4}$", po["id"])
        assert po["backlog_item_id"] == payload["backlog_item_id"]
        assert po["supplier_name"] == payload["supplier_name"]
        assert po["quantity"] == payload["quantity"]
        assert abs(po["unit_cost"] - payload["unit_cost"]) < 0.01
        assert po["expected_delivery_date"] == payload["expected_delivery_date"]
        assert po["status"] == "Pending"
        # created_date is an ISO date (YYYY-MM-DD)
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", po["created_date"])
        assert po["notes"] == payload["notes"]

    def test_create_purchase_order_without_notes(self, client):
        """Test that notes are optional."""
        payload = self._build_payload(client)
        payload.pop("notes")

        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 201
        assert response.json()["notes"] is None

    def test_create_purchase_order_nonexistent_backlog_item(self, client):
        """Test creating a PO for a backlog item that doesn't exist."""
        payload = self._build_payload(client, backlog_item_id="nonexistent-999")

        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_create_duplicate_purchase_order(self, client):
        """Test that a backlog item can only have one purchase order."""
        payload = self._build_payload(client)

        first = client.post("/api/purchase-orders", json=payload)
        assert first.status_code == 201

        second = client.post("/api/purchase-orders", json=payload)
        assert second.status_code == 409

        data = second.json()
        assert "detail" in data
        assert "already has purchase order" in data["detail"].lower()

    def test_create_purchase_order_invalid_quantity(self, client):
        """Test that non-positive quantities are rejected."""
        payload = self._build_payload(client, quantity=0)

        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 400
        assert "quantity" in response.json()["detail"].lower()

    def test_create_purchase_order_invalid_unit_cost(self, client):
        """Test that non-positive unit costs are rejected."""
        payload = self._build_payload(client, unit_cost=-5)

        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 400
        assert "unit cost" in response.json()["detail"].lower()

    def test_get_purchase_order_by_backlog_item(self, client):
        """Test fetching the PO associated with a backlog item."""
        payload = self._build_payload(client)
        created = client.post("/api/purchase-orders", json=payload).json()

        response = client.get(f"/api/purchase-orders/{payload['backlog_item_id']}")
        assert response.status_code == 200

        po = response.json()
        assert po["id"] == created["id"]
        assert po["backlog_item_id"] == payload["backlog_item_id"]

    def test_get_purchase_order_nonexistent_backlog_item(self, client):
        """Test fetching a PO for a backlog item that has none."""
        response = client.get("/api/purchase-orders/nonexistent-999")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "no purchase order" in data["detail"].lower()

    def test_backlog_exposes_purchase_order_fields(self, client):
        """Test that backlog items always include purchase order status fields."""
        response = client.get("/api/backlog")
        assert response.status_code == 200

        for item in response.json():
            assert "has_purchase_order" in item
            assert "purchase_order_id" in item
            assert isinstance(item["has_purchase_order"], bool)
            assert item["purchase_order_id"] is None or isinstance(item["purchase_order_id"], str)
            # The id is only present when the flag says there is a PO
            assert item["has_purchase_order"] == (item["purchase_order_id"] is not None)

    def test_backlog_reflects_created_purchase_order(self, client):
        """Test that creating a PO is reflected on the matching backlog item."""
        payload = self._build_payload(client)
        created = client.post("/api/purchase-orders", json=payload).json()

        backlog = client.get("/api/backlog").json()
        item = next(b for b in backlog if b["id"] == payload["backlog_item_id"])

        assert item["has_purchase_order"] is True
        assert item["purchase_order_id"] == created["id"]
