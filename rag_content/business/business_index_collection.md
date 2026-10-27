# Business Index & Schema Documentation Collection

This collection contains domain terminology, calculation formulas, database table mappings, and code-decoding master data across all analytical pillars.

## Pillar 1: Inventory & Supply Chain Health

## metadata:
pillar: "Inventory & Supply Chain Health"
category: "Business Jargon & Terminology"
intent: "Map supply chain business terms to SQL formulas and table constructs"

### Key Terminology & Formulas

* **Low Inventory / Reorder Threshold:** Defined as `current_stock < 2` (or store-specific reorder point defined in `inventory.reorder_level`).

* **Shrinkage / Stock Loss:** Stock reduction due to non-sales reasons. Query `inventory_logs` where `reason_code IN ('EXPIRED', 'DAMAGED', 'SPOILAGE', 'STOLEN')`.

* **Days of Supply (DoS):** `current_stock / NULLIF(avg_daily_sales_7d, 0)`. Predicts stock depletion timeframe.

* **South Indian Region States:** Must explicitly include `'Karnataka'`, `'Tamil Nadu'`, `'Kerala'`, `'Andhra Pradesh'`, `'Telangana'`.

## metadata:
pillar: "Inventory & Supply Chain Health"
category: "Database Documentation & Joins"
intent: "Column data types, foreign keys, and lookup mappings for inventory tables"

### Table Schema Documentation

1. **`inventory` Table:**

   * `store_id` (FK -> `dark_stores.store_id`)

   * `product_id` (FK -> `products.product_id`)

   * `current_stock` (INT): Total available sellable units.

   * `sku_code` (VARCHAR): Stock Keeping Unit identifier.

2. **`inventory_logs` Table & Master Code Decoding:**

   * `reason_code` maps to `master_data.attribute_code` where `attribute_type = 'STOCK_LOG_REASON'`.

   * **Codes:** `'EXPIRED'` -> Item past expiry; `'DAMAGED'` -> Physical package damage; `'RESTOCK'` -> Inward shipment.

## Pillar 2: Sales & Revenue Performance

## metadata:
pillar: "Sales & Revenue Performance"
category: "Business Jargon & Terminology"
intent: "Define sales KPIs, status filters, and revenue calculation rules"

### Key Terminology & Formulas

* **Gross Merchandise Value (GMV):** `SUM(orders.final_amount)` or `SUM(order_items.quantity * order_items.unit_price)`.

* **Average Order Value (AOV):** `SUM(final_amount) / COUNT(DISTINCT order_id)`.

* **Valid Completed Sales Filter:** Always filter orders with `WHERE o.status = 'Delivered'` to exclude cancelled or pending transactions.

* **State Rank Filtering:** Window function rule — `ROW_NUMBER() OVER (PARTITION BY state ORDER BY sales DESC)` must be executed in a subquery/CTE before applying `WHERE rank <= N`.

## metadata:
pillar: "Sales & Revenue Performance"
category: "Database Documentation & Joins"
intent: "Column definitions and table join rules for revenue analytics"

### Table Schema Documentation

1. **`orders` Table:**

   * `order_id` (PK), `customer_id` (FK), `store_id` (FK -> `dark_stores.store_id`).

   * `status` (VARCHAR): Allowed values: `'Pending'`, `'Packed'`, `'Out for Delivery'`, `'Delivered'`, `'Cancelled'`.

   * `final_amount` (DECIMAL): Total price paid post discounts.

2. **`order_items` Table:**

   * `order_id` (FK -> `orders.order_id`), `product_id` (FK -> `products.product_id`).

   * `quantity` (INT): Units purchased per line item.

   * `unit_price` (DECIMAL): Price per unit at time of purchase.

## Pillar 3: Operational Efficiency & Logistics

## metadata:
pillar: "Operational Efficiency & Logistics"
category: "Business Jargon & Terminology"
intent: "Define operational metrics, SLA formulas, and failure codes"

### Key Terminology & Formulas

* **Order Failure Rate:** `COUNT(orders WHERE status = 'Cancelled') / COUNT(total_orders)`.

* **Delivery Time (Minutes):** `EXTRACT(EPOCH FROM (delivered_at - order_timestamp)) / 60`.

* **SLA Breach:** Deliveries taking greater than 15 minutes (`delivery_time > 15`).

* **Hub / Dark Store:** Micro-fulfillment centers located in urban centers (`dark_stores` table).

## metadata:
pillar: "Operational Efficiency & Logistics"
category: "Database Documentation & Joins"
intent: "Master data decoding and spatial schema relationships"

### Table Schema & Lookup Documentation

1. **`dark_stores` & `cities` Joins:**

   * Join `dark_stores.city_id` to `cities.city_id` to resolve regional attributes (`city_name`, `state`, `zone`).

2. **`master_data` Table (Status & Cancel Reason Decoding):**

   * Filter `attribute_type = 'CANCELLATION_REASON'`.

   * **Codes:** `'RIDER_UNAVAILABLE'`, `'OUT_OF_STOCK'`, `'CUSTOMER_CANCELLED'`, `'ADDRESS_NOT_FOUND'`.

## Pillar 4: Customer Behavior & Retention

## metadata:
pillar: "Customer Behavior & Retention"
category: "Business Jargon & Terminology"
intent: "Define customer metrics, loyalty tiers, and acquisition definitions"

### Key Terminology & Formulas

* **Customer Lifetime Value (LTV):** Sum of `final_amount` for all `Delivered` orders tied to a `customer_id`.

* **Active Customer:** Customer with at least 1 completed order within the past 30 days.

* **Acquisition Channels:** Source channels stored in `customers.acquisition_channel` (e.g., `'Organic'`, `'Google_Ads'`, `'Instagram_Influencer'`, `'Referral'`).

## metadata:
pillar: "Customer Behavior & Retention"
category: "Database Documentation & Master Lookups"
intent: "Customer profile and refund lookup documentation"

### Table Schema Documentation

1. **`customers` Table:**

   * `customer_id` (PK), `signup_timestamp` (TIMESTAMP), `acquisition_channel` (VARCHAR).

   * `loyalty_tier_code` (VARCHAR): Connects to `master_data.attribute_code`.

2. **`master_data` Table (Loyalty Tier & Refund Decoding):**

   * `attribute_type = 'LOYALTY_TIER'`:

     * `'LT_STD'` -> Standard Tier

     * `'LT_SLV'` -> Silver Tier

     * `'LT_GLD'` -> Gold Tier

     * `'LT_PLT'` -> Platinum Tier

   * `attribute_type = 'REFUND_REASON'`:

     * `'REF_QUAL'` -> Quality Issue / Damaged Perishable

     * `'REF_MISS'` -> Missing Item from Package

     * `'REF_LATE'` -> Excessive Delivery Delay