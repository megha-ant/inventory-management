"""
Tests for tasks API endpoints (GET/POST/PATCH/DELETE /api/tasks).
"""
import pytest

import mock_data

REQUIRED_TASK_FIELDS = ["id", "title", "priority", "dueDate", "status"]


@pytest.fixture(autouse=True)
def reset_tasks_state():
    """Snapshot and restore the in-memory tasks list around each test.

    Tasks are stored in a module-level list that mutates across requests, so without
    this reset the tests would depend on execution order.
    """
    saved_tasks = list(mock_data.tasks)
    yield
    mock_data.tasks[:] = saved_tasks


class TestTasksEndpoints:
    """Test suite for task-related endpoints."""

    def _create_task(self, client, **overrides):
        """Create a task via the API and return the response JSON."""
        payload = {
            "title": "Review Q4 supplier contracts",
            "priority": "high",
            "dueDate": "2025-10-15",
        }
        payload.update(overrides)
        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 201
        return response.json()

    def test_get_all_tasks(self, client):
        """Test getting all tasks returns a list."""
        response = client.get("/api/tasks")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_create_task(self, client):
        """Test creating a task returns the full task with defaults applied."""
        task = self._create_task(client)

        for field in REQUIRED_TASK_FIELDS:
            assert field in task

        assert isinstance(task["id"], str)
        assert len(task["id"]) > 0
        assert task["title"] == "Review Q4 supplier contracts"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-15"
        # New tasks always start as pending
        assert task["status"] == "pending"

    def test_created_task_appears_in_list(self, client):
        """Test that a created task shows up in the tasks list."""
        created = self._create_task(client)

        response = client.get("/api/tasks")
        assert response.status_code == 200

        task_ids = [task["id"] for task in response.json()]
        assert created["id"] in task_ids

    def test_create_task_strips_title_whitespace(self, client):
        """Test that surrounding whitespace in the title is trimmed."""
        task = self._create_task(client, title="  Approve Tokyo orders  ")
        assert task["title"] == "Approve Tokyo orders"

    def test_create_task_default_priority(self, client):
        """Test that priority defaults to medium when omitted."""
        response = client.post(
            "/api/tasks", json={"title": "Check inventory levels", "dueDate": "2025-10-20"}
        )
        assert response.status_code == 201
        assert response.json()["priority"] == "medium"

    def test_create_task_empty_title(self, client):
        """Test that a blank title is rejected."""
        response = client.post(
            "/api/tasks", json={"title": "   ", "priority": "low", "dueDate": "2025-10-20"}
        )
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "title" in data["detail"].lower()

    def test_create_task_missing_due_date(self, client):
        """Test that a missing due date fails validation."""
        response = client.post("/api/tasks", json={"title": "No due date"})
        assert response.status_code == 422

    def test_toggle_task_status(self, client):
        """Test that PATCH toggles a task between pending and completed."""
        created = self._create_task(client)

        response = client.patch(f"/api/tasks/{created['id']}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        # Toggling again returns it to pending
        response = client.patch(f"/api/tasks/{created['id']}")
        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_toggle_nonexistent_task(self, client):
        """Test toggling a task that doesn't exist."""
        response = client.patch("/api/tasks/nonexistent-task-999")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_delete_task(self, client):
        """Test deleting a task removes it from the list."""
        created = self._create_task(client)

        response = client.delete(f"/api/tasks/{created['id']}")
        assert response.status_code == 204

        task_ids = [task["id"] for task in client.get("/api/tasks").json()]
        assert created["id"] not in task_ids

    def test_delete_nonexistent_task(self, client):
        """Test deleting a task that doesn't exist."""
        response = client.delete("/api/tasks/nonexistent-task-999")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
