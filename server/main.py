from datetime import datetime, timedelta
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel, Field
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders, restock_orders, tasks

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

# Restocking configuration: delivery lead time (days) per category for submitted
# restock orders; categories outside this map (or unknown) use the default.
LEAD_TIME_BY_CATEGORY = {
    'Circuit Boards': 14,
    'Controllers': 12,
    'Sensors': 7,
    'Actuators': 7,
    'Power Supplies': 10,
}
DEFAULT_LEAD_TIME_DAYS = 10
DEFAULT_UNIT_COST = 25.0

# Mock pricing/category for demand-forecast SKUs that exist in neither inventory.json
# nor orders.json item lines (8 of the 9 forecast SKUs today). These are intentionally
# made-up demo values, NOT derived from data — see resolve_sku_pricing() for the
# lookup precedence. Category is only set where the item name clearly maps to an
# existing category; None means "unknown" and falls back to the default lead time.
RESTOCK_SKU_FALLBACK = {
    'WDG-001': {'unit_cost': 12.50, 'category': None},           # Industrial Widget Type A
    'BRG-102': {'unit_cost': 8.75, 'category': None},            # Steel Bearing Assembly
    'GSK-203': {'unit_cost': 3.20, 'category': None},            # High-Temperature Gasket
    'MTR-304': {'unit_cost': 145.00, 'category': 'Actuators'},   # Electric Motor 5HP
    'FLT-405': {'unit_cost': 6.40, 'category': None},            # Oil Filter Cartridge
    'VLV-506': {'unit_cost': 27.80, 'category': 'Actuators'},    # Pressure Relief Valve
    'SNR-420': {'unit_cost': 15.50, 'category': 'Sensors'},      # Temperature Sensor Module
    'CTL-330': {'unit_cost': 89.00, 'category': 'Controllers'},  # Logic Controller Board
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

def get_lead_time_days(category: Optional[str]) -> int:
    """Delivery lead time for a category; unknown/None categories get the default."""
    if not category:
        return DEFAULT_LEAD_TIME_DAYS
    return LEAD_TIME_BY_CATEGORY.get(category, DEFAULT_LEAD_TIME_DAYS)

def resolve_sku_pricing(sku: str) -> dict:
    """Resolve unit cost and category for a SKU.

    Precedence: inventory.json record -> average unit_price (and order-level category)
    derived from orders.json item lines -> RESTOCK_SKU_FALLBACK mock catalog -> generic
    default. The fallback tiers exist because most demand-forecast SKUs have no matching
    inventory or order-line record in the current mock data.
    """
    # 1. Inventory record (authoritative when present)
    inventory_match = next((item for item in inventory_items if item["sku"] == sku), None)
    if inventory_match:
        return {"unit_cost": inventory_match["unit_cost"], "category": inventory_match.get("category")}

    # 2. Derive from historical order lines: average unit_price across all orders that
    #    include this SKU; category comes from the first order carrying it.
    prices = []
    derived_category = None
    for order in orders:
        for line in order.get("items", []):
            if line.get("sku") == sku and line.get("unit_price") is not None:
                prices.append(line["unit_price"])
                if derived_category is None:
                    derived_category = order.get("category")
    if prices:
        return {"unit_cost": round(sum(prices) / len(prices), 2), "category": derived_category}

    # 3. Mock fallback catalog for forecast SKUs absent from all data files
    if sku in RESTOCK_SKU_FALLBACK:
        return dict(RESTOCK_SKU_FALLBACK[sku])

    # 4. Last-resort generic default
    return {"unit_cost": DEFAULT_UNIT_COST, "category": None}

def build_restock_recommendations() -> list:
    """Build the prioritized restock candidate list from demand forecasts.

    shortfall = forecasted_demand - quantity_on_hand (summed across warehouses; 0 when
    the SKU has no inventory record, i.e. nothing on hand anywhere). Items with no
    shortfall are excluded. Sorted by largest shortfall first so the frontend can
    greedily fill a budget from the top of the list.
    """
    recommendations = []
    for forecast in demand_forecasts:
        sku = forecast["item_sku"]
        # Sum across warehouses in case the same SKU is stocked in multiple locations
        current_stock = sum(
            item["quantity_on_hand"] for item in inventory_items if item["sku"] == sku
        )
        shortfall = forecast["forecasted_demand"] - current_stock
        if shortfall <= 0:
            continue

        pricing = resolve_sku_pricing(sku)
        recommendations.append({
            "sku": sku,
            "name": forecast["item_name"],
            "category": pricing["category"],
            "current_stock": current_stock,
            "forecasted_demand": forecast["forecasted_demand"],
            "shortfall_units": shortfall,
            "unit_cost": pricing["unit_cost"],
            "recommended_quantity": shortfall,
            "line_cost": round(shortfall * pricing["unit_cost"], 2),
            "lead_time_days": get_lead_time_days(pricing["category"]),
        })

    recommendations.sort(key=lambda rec: rec["shortfall_units"], reverse=True)
    return recommendations

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False
    # The dashboard's "Create PO" / "View PO" toggle and the view-mode purchase order
    # modal both key off the PO id (not just the boolean flag), so it is exposed here.
    purchase_order_id: Optional[str] = None

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

# Task fields use camelCase (dueDate) instead of snake_case to match the existing
# client-side task shape (useAuth.js mock tasks / TasksModal.vue), since App.vue merges
# API tasks and mock tasks into a single list.
class Task(BaseModel):
    id: str
    title: str
    priority: str
    dueDate: str
    status: str

class CreateTaskRequest(BaseModel):
    title: str
    priority: str = "medium"
    dueDate: str

class RestockRecommendation(BaseModel):
    sku: str
    name: str
    category: Optional[str] = None
    current_stock: int
    forecasted_demand: int
    shortfall_units: int
    unit_cost: float
    recommended_quantity: int
    line_cost: float
    lead_time_days: int

class RestockOrderItemRequest(BaseModel):
    sku: str
    quantity: int = Field(gt=0)

class CreateRestockOrderRequest(BaseModel):
    budget: float = Field(ge=0)
    items: List[RestockOrderItemRequest]

class RestockOrderItem(BaseModel):
    sku: str
    name: str
    category: Optional[str] = None
    quantity: int
    unit_cost: float
    line_cost: float
    lead_time_days: int

class RestockOrder(BaseModel):
    id: str
    order_number: str
    status: str
    order_date: str
    expected_delivery: str
    budget: float
    total_cost: float
    items: List[RestockOrderItem]

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add purchase order info to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order; expose its id so the
        # dashboard can show "View PO" (and load it) instead of "Create PO".
        po = next((po for po in purchase_orders if po["backlog_item_id"] == item["id"]), None)
        item_dict["has_purchase_order"] = po is not None
        item_dict["purchase_order_id"] = po["id"] if po else None
        result.append(item_dict)
    return result

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

@app.get("/api/restocking/recommendations", response_model=List[RestockRecommendation])
def get_restocking_recommendations():
    """Get prioritized restock candidates derived from demand forecasts (largest shortfall first)"""
    return build_restock_recommendations()

@app.post("/api/restocking/orders", response_model=RestockOrder, status_code=201)
def create_restock_order(request: CreateRestockOrderRequest):
    """Submit a restocking order (stored in memory only; resets on server restart)"""
    if not request.items:
        raise HTTPException(status_code=400, detail="Restock order must contain at least one item")

    forecasts_by_sku = {forecast["item_sku"]: forecast for forecast in demand_forecasts}

    order_items = []
    for line in request.items:
        forecast = forecasts_by_sku.get(line.sku)
        # Only demand-forecast SKUs are valid restock candidates — rejects typos/stale SKUs
        if not forecast:
            raise HTTPException(status_code=400, detail=f"SKU {line.sku} is not a restocking candidate")

        # Pricing is re-derived server-side so the stored order never trusts client-sent costs
        pricing = resolve_sku_pricing(line.sku)
        order_items.append({
            "sku": line.sku,
            "name": forecast["item_name"],
            "category": pricing["category"],
            "quantity": line.quantity,
            "unit_cost": pricing["unit_cost"],
            "line_cost": round(line.quantity * pricing["unit_cost"], 2),
            "lead_time_days": get_lead_time_days(pricing["category"]),
        })

    order_date = datetime.now()
    # The order is only complete once the slowest line arrives, so the order-level
    # expected delivery uses the maximum lead time across its items.
    max_lead_time = max(item["lead_time_days"] for item in order_items)

    restock_order = {
        "id": str(uuid.uuid4()),
        "order_number": f"RST-2025-{len(restock_orders) + 1:04d}",
        "status": "Submitted",
        "order_date": order_date.strftime("%Y-%m-%dT%H:%M:%S"),
        "expected_delivery": (order_date + timedelta(days=max_lead_time)).strftime("%Y-%m-%dT%H:%M:%S"),
        "budget": request.budget,
        "total_cost": round(sum(item["line_cost"] for item in order_items), 2),
        "items": order_items,
    }
    restock_orders.append(restock_order)
    return restock_order

@app.get("/api/restocking/orders", response_model=List[RestockOrder])
def get_restock_orders():
    """Get restocking orders submitted since server start (newest first)"""
    return list(reversed(restock_orders))

@app.get("/api/tasks", response_model=List[Task])
def get_tasks():
    """Get tasks created via the API since server start"""
    return tasks

@app.post("/api/tasks", response_model=Task, status_code=201)
def create_task(request: CreateTaskRequest):
    """Create a new task (stored in memory only; resets on server restart)"""
    if not request.title.strip():
        raise HTTPException(status_code=400, detail="Task title must not be empty")

    task = {
        # uuid instead of a sequence so ids stay unique after deletions and never
        # collide with the numeric ids of the client-side mock tasks (useAuth.js).
        "id": str(uuid.uuid4()),
        "title": request.title.strip(),
        "priority": request.priority,
        "dueDate": request.dueDate,
        "status": "pending",
    }
    tasks.append(task)
    return task

@app.patch("/api/tasks/{task_id}", response_model=Task)
def toggle_task(task_id: str):
    """Toggle a task between pending and completed"""
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    task["status"] = "completed" if task["status"] == "pending" else "pending"
    return task

@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    """Delete a task"""
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    tasks.remove(task)
    return None

@app.post("/api/purchase-orders", response_model=PurchaseOrder, status_code=201)
def create_purchase_order(request: CreatePurchaseOrderRequest):
    """Create a purchase order for a backlog item (stored in memory only)"""
    backlog_item = next((b for b in backlog_items if b["id"] == request.backlog_item_id), None)
    if not backlog_item:
        raise HTTPException(status_code=404, detail=f"Backlog item {request.backlog_item_id} not found")

    # One PO per backlog item: the dashboard switches from "Create PO" to "View PO"
    # based on this, so a duplicate would be unreachable in the UI anyway.
    existing = next((po for po in purchase_orders if po["backlog_item_id"] == request.backlog_item_id), None)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Backlog item {request.backlog_item_id} already has purchase order {existing['id']}"
        )

    if request.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")
    if request.unit_cost <= 0:
        raise HTTPException(status_code=400, detail="Unit cost must be greater than zero")

    purchase_order = {
        # POs are never deleted, so a sequence-based readable id is safe and nicer to
        # display in the UI than a uuid.
        "id": f"PO-2025-{len(purchase_orders) + 1:04d}",
        "backlog_item_id": request.backlog_item_id,
        "supplier_name": request.supplier_name,
        "quantity": request.quantity,
        "unit_cost": request.unit_cost,
        "expected_delivery_date": request.expected_delivery_date,
        "status": "Pending",
        "created_date": datetime.now().strftime("%Y-%m-%d"),
        "notes": request.notes,
    }
    purchase_orders.append(purchase_order)
    return purchase_order

@app.get("/api/purchase-orders/{backlog_item_id}", response_model=PurchaseOrder)
def get_purchase_order_by_backlog_item(backlog_item_id: str):
    """Get the purchase order associated with a backlog item"""
    po = next((po for po in purchase_orders if po["backlog_item_id"] == backlog_item_id), None)
    if not po:
        raise HTTPException(status_code=404, detail=f"No purchase order found for backlog item {backlog_item_id}")
    return po

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
