# Business Index: Unified Commerce Analytics (Sales, Revenue, Inventory & Supply Chain)

This index provides a comprehensive, domain-driven knowledge base designed to bridge natural language prompts, analytical metrics, and SQL schema mappings across two core pillars: **Sales & Revenue Performance** and **Inventory & Supply Chain Health**.

---

## 1. Executive Summary & Domain Taxonomy

### 1.1 Core Business Pillars
1. **Sales & Revenue Performance**: Tracks commercial health, top-line growth, order value mechanics, revenue dynamics, discount impact, and regional demand patterns.
2. **Inventory & Supply Chain Health**: Measures stock availability, inventory turnover velocity, stockout risks, carrying costs, and supplier procurement performance (OTIF).

### 1.2 Unified Business Jargon & Synonyms Dictionary
| Term / Abbreviation | Domain Context | Canonical Meaning & Synonyms | SQL Field / Context Mapping |
| :--- | :--- | :--- | :--- |
| **GMV** | Revenue | Gross Merchandise Value; total sales value before discounts and fees. | `SUM(oi.quantity * oi.unit_price)` |
| **Net Revenue** | Revenue | Realized revenue after item discounts and promotions. | `SUM(oi.quantity * oi.unit_price - oi.discount)` |
| **AOV** | Revenue | Average Order Value; average monetary value of completed orders. | `AVG(o.final_amount)` |
| **COGS** | Financials | Cost of Goods Sold; cost to acquire or produce products sold. | `SUM(oi.quantity * p.unit_cost)` |
| **Net Margin** | Financials | Profit remaining after COGS and item discounts. | `Net Revenue - COGS` |
| **Dark Store** | Operations | Micro-fulfillment center for quick-commerce delivery. | `dark_stores.store_id` |
| **Out of Stock (OOS)** | Inventory | Zero available units of a stock-keeping unit in a store. | `inventory.current_stock = 0` |
| **Reorder Level** | Inventory | Minimum threshold of units triggering a supplier purchase order. | `inventory.reorder_level` |
| **Days of Supply (DOS)**| Inventory | Estimated days current stock will last based on run-rate. | `current_stock / avg_daily_sales` |
| **Inventory Turnover** | Supply Chain | Ratio of total COGS to average current inventory value. | `Total COGS / Current Inventory Value` |
| **OTIF** | Supply Chain | On-Time, In-Full; percentage of POs delivered complete on date. | `(On-Time POs & In-Full POs) / Total POs` |

---

## 2. Canonical Business Metrics & Formulas

### 2.1 Sales & Revenue Metrics
* **Gross Merchandise Value (GMV)**
  $$\text{GMV} = \sum (\text{quantity} \times \text{unit\_price})$$
* **Net Revenue**
  $$\text{Net Revenue} = \sum (\text{quantity} \times \text{unit\_price} - \text{discount}) + \text{delivery\_fee}$$
* **Average Order Value (AOV)**
  $$\text{AOV} = \frac{\text{Total Delivered Net Revenue}}{\text{Total Delivered Orders Count}}$$
* **Month-over-Month (MoM) Growth Rate (%)**
  $$\text{MoM Growth \%} = \left( \frac{\text{Revenue}_{\text{Current Month}} - \text{Revenue}_{\text{Previous Month}}}{\text{Revenue}_{\text{Previous Month}}} \right) \times 100$$
* **Discount Erosion Percentage (%)**
  $$\text{Discount Rate \%} = \left( \frac{\text{Total Discounts}}{\text{Gross Merchandise Value}} \right) \times 100$$

### 2.2 Inventory & Supply Chain Metrics
* **Daily Sales Velocity (Units/Day)**
  $$\text{Daily Sales Velocity} = \frac{\sum_{\text{Last 14 Days}} \text{Quantity Sold}}{14}$$
* **Days of Stock Remaining**
  $$\text{Days of Supply} = \frac{\text{Current Stock}}{\text{Daily Sales Velocity}}$$
* **Inventory Turnover Ratio (90-Day Basis)**
  $$\text{Turnover Ratio} = \frac{\sum_{\text{90 Days}} (\text{Quantity Sold} \times \text{Unit Cost})}{\sum (\text{Current Stock} \times \text{Unit Cost})}$$
* **On-Time In-Full (OTIF) Rate (%)**
  $$\text{OTIF \%} = \left( \frac{\text{Count of POs with Actual Delivery Date} \le \text{Expected Delivery Date AND Received Qty} \ge \text{Ordered Qty}}{\text{Total Received POs}} \right) \times 100$$

---

## 3. Database Schema & Join Graph Specifications

### 3.1 Primary Entity Relationship Schema
* **`cities`**: `city_id` (PK), `city_name`, `state`, `tier` (`Tier 1`, `Tier 2`, `Tier 3`)
* **`dark_stores`**: `store_id` (PK), `store_name`, `city_id` (FK), `is_active`
* **`categories`**: `category_id` (PK), `category_name`, `department`
* **`products`**: `product_id` (PK), `category_id` (FK), `product_name`, `unit_cost`, `mrp`
* **`inventory`**: `inventory_id` (PK), `store_id` (FK), `product_id` (FK), `current_stock`, `reorder_level`
* **`orders`**: `order_id` (PK), `store_id` (FK), `customer_id`, `order_timestamp`, `status`, `delivery_fee`, `final_amount`
* **`order_items`**: `order_item_id` (PK), `order_id` (FK), `product_id` (FK), `quantity`, `unit_price`, `discount`
* **`suppliers`**: `supplier_id` (PK), `supplier_name`, `contact_email`
* **`purchase_orders`**: `po_id` (PK), `supplier_id` (FK), `store_id` (FK), `ordered_quantity`, `received_quantity`, `expected_delivery_date`, `actual_delivery_date`, `status`

### 3.2 Standard Join Pathways
```
[cities] ──(city_id)──> [dark_stores] ──(store_id)──> [orders] ──(order_id)──> [order_items]
                                 │                                                    │
                                 ├──(store_id)──> [inventory] <──(product_id)─────────┤
                                 │                                                    │
                                 └──(store_id)──> [purchase_orders]             [products]
                                                         │                            │
                                                  (supplier_id)                  (category_id)
                                                         │                            │
                                                   [suppliers]                  [categories]
```

---

## 4. Enumeration Decode & Lookup Tables

### 4.1 Order Status Enums (`orders.status`)
* **`Delivered`**: Order successfully fulfilled and handed over to customer. **(Default inclusion for revenue queries)**.
* **`Cancelled`**: Order cancelled by customer or platform prior to delivery. Exclude from revenue metrics.
* **`Returned`**: Order returned post-delivery. Requires refund deduction logic.
* **`In-Transit`**: Active order currently with delivery partner.

### 4.2 Purchase Order Status Enums (`purchase_orders.status`)
* **`Received`**: PO delivered and checked in at dark store inventory.
* **`Pending`**: PO placed with supplier, awaiting delivery.
* **`Cancelled`**: PO cancelled due to supplier stock unavailability or breach of agreement.

---

## 5. Analytical Decision Logic Matrices

### 5.1 Stock Alert & Reorder Classification
| Current Stock Level (`current_stock`) | Estimated Days of Supply | Risk / Action Classification |
| :--- | :--- | :--- |
| `= 0` | 0 Days | **CRITICAL: Out of Stock** (Immediate PO creation) |
| `<= 0.5 * reorder_level` | `< 3 Days` | **HIGH RISK: Immediate Restock Required** |
| `<= reorder_level` | `3 to 7 Days` | **WARNING: Reorder Threshold Reached** |
| `> reorder_level` | `> 7 Days` | **HEALTHY: Adequate Stock** |

### 5.2 Inventory Velocity & Turnover Health
| 90-Day Inventory Turnover Ratio | Average Holding Period | Inventory Health Category |
| :--- | :--- | :--- |
| `< 1.5` | `> 60 Days` | **SLOW MOVING**: Excess Capital Lockup & Expiry Risk |
| `1.5 to 4.0` | `22.5 to 60 Days` | **HEALTHY TURNOVER**: Balanced Operations |
| `> 4.0` | `< 22.5 Days` | **HIGH TURNOVER**: Fast-Moving, Stockout Vulnerable |

### 5.3 Supplier SLA Rating Matrix
| OTIF Compliance Percentage | Average Delivery Delay | Supplier Performance Tier |
| :--- | :--- | :--- |
| `>= 90.0%` | `<= 1.0 Day` | **Preferred Supplier (Tier 1)** |
| `75.0% to 89.9%` | `1.1 to 3.0 Days` | **Standard Supplier (Tier 2)** |
| `< 75.0%` | `> 3.0 Days` | **Underperforming**: Contract SLA Penalty Risk |