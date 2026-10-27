# Prompt-SQL Collection: Unified Commerce Analytics

This document provides a consolidated, production-grade Prompt-to-SQL reference library optimized for RAG vector index retrieval. All queries adhere to strict MySQL/MariaDB standards, utilizing multi-table JOINs, Common Table Expressions (CTEs), window functions, aggregate functions, and business metric logic tailored for quick-commerce and retail operations.

---

# Part 1: Sales & Revenue Performance

---

## 1. Regional Best-Selling Products Ranking

```yaml
metadata:
  pillar: "Sales & Revenue Performance"
  category: "Product Analytics"
  intent: "rank_top_selling_products_by_region"
  complexity: "Advanced"
  tables: ["orders", "order_items", "dark_stores", "cities", "products", "categories"]
```

### User Prompt
"Show the top 3 best-selling products by quantity sold in each South Indian state over the past 30 days. Include category name, total gross revenue, and filter strictly for completed orders."

### Executable MySQL Query
```sql
WITH regional_sales AS (
    SELECT 
        c.state,
        cat.category_name,
        p.product_id,
        p.product_name,
        SUM(oi.quantity) AS total_units_sold,
        SUM(oi.quantity * oi.unit_price) AS total_gross_revenue
    FROM orders AS o
    INNER JOIN dark_stores AS ds ON o.store_id = ds.store_id
    INNER JOIN cities AS c ON ds.city_id = c.city_id
    INNER JOIN order_items AS oi ON o.order_id = oi.order_id
    INNER JOIN products AS p ON oi.product_id = p.product_id
    INNER JOIN categories AS cat ON p.category_id = cat.category_id
    WHERE c.state IN ('Karnataka', 'Tamil Nadu', 'Kerala', 'Andhra Pradesh', 'Telangana')
      AND o.status = 'Delivered'
      AND o.order_timestamp >= NOW() - INTERVAL 30 DAY
    GROUP BY c.state, cat.category_name, p.product_id, p.product_name
),
ranked_regional_sales AS (
    SELECT 
        state,
        category_name,
        product_id,
        product_name,
        total_units_sold,
        total_gross_revenue,
        DENSE_RANK() OVER (PARTITION BY state ORDER BY total_units_sold DESC, total_gross_revenue DESC) AS rank_in_state
    FROM regional_sales
)
SELECT 
    state,
    rank_in_state,
    category_name,
    product_name,
    total_units_sold,
    ROUND(total_gross_revenue, 2) AS total_gross_revenue_inr
FROM ranked_regional_sales
WHERE rank_in_state <= 3
ORDER BY state ASC, rank_in_state ASC;
```

---

## 2. Average Order Value (AOV) & Revenue Waterfall Analysis

```yaml
metadata:
  pillar: "Sales & Revenue Performance"
  category: "Revenue & Financial Metrics"
  intent: "calculate_aov_and_revenue_waterfall"
  complexity: "Advanced"
  tables: ["orders", "order_items", "dark_stores", "cities"]
```

### User Prompt
"Calculate the gross merchandise value (GMV), total discounts, net revenue, and average order value (AOV) broken down by city tier over the past 90 days."

### Executable MySQL Query
```sql
WITH order_financials AS (
    SELECT 
        c.tier AS city_tier,
        o.order_id,
        SUM(oi.quantity * oi.unit_price) AS gross_items_value,
        SUM(oi.discount) AS item_discounts,
        o.delivery_fee,
        o.final_amount AS order_net_value
    FROM orders AS o
    INNER JOIN dark_stores AS ds ON o.store_id = ds.store_id
    INNER JOIN cities AS c ON ds.city_id = c.city_id
    INNER JOIN order_items AS oi ON o.order_id = oi.order_id
    WHERE o.status = 'Delivered'
      AND o.order_timestamp >= NOW() - INTERVAL 90 DAY
    GROUP BY c.tier, o.order_id, o.delivery_fee, o.final_amount
)
SELECT 
    city_tier,
    COUNT(DISTINCT order_id) AS total_delivered_orders,
    ROUND(SUM(gross_items_value), 2) AS total_gmv_inr,
    ROUND(SUM(item_discounts), 2) AS total_discounts_inr,
    ROUND(SUM(delivery_fee), 2) AS total_delivery_fees_inr,
    ROUND(SUM(order_net_value), 2) AS total_net_revenue_inr,
    ROUND(AVG(gross_items_value), 2) AS gross_aov_inr,
    ROUND(AVG(order_net_value), 2) AS net_aov_inr
FROM order_financials
GROUP BY city_tier
ORDER BY total_net_revenue_inr DESC;
```

---

## 3. Month-over-Month (MoM) Category Revenue Growth

```yaml
metadata:
  pillar: "Sales & Revenue Performance"
  category: "Growth & Dynamics"
  intent: "calculate_mom_category_revenue_growth"
  complexity: "Advanced"
  tables: ["orders", "order_items", "products", "categories"]
```

### User Prompt
"Calculate Month-over-Month (MoM) revenue growth percentage and absolute growth for each product category over the last 3 months."

### Executable MySQL Query
```sql
WITH monthly_category_revenue AS (
    SELECT 
        DATE_FORMAT(o.order_timestamp, '%Y-%m-01') AS sales_month,
        cat.category_name,
        SUM(oi.quantity * oi.unit_price - oi.discount) AS monthly_net_revenue
    FROM orders AS o
    INNER JOIN order_items AS oi ON o.order_id = oi.order_id
    INNER JOIN products AS p ON oi.product_id = p.product_id
    INNER JOIN categories AS cat ON p.category_id = cat.category_id
    WHERE o.status = 'Delivered'
      AND o.order_timestamp >= DATE_SUB(NOW(), INTERVAL 3 MONTH)
    GROUP BY DATE_FORMAT(o.order_timestamp, '%Y-%m-01'), cat.category_name
),
revenue_lag_calc AS (
    SELECT 
        sales_month,
        category_name,
        monthly_net_revenue,
        LAG(monthly_net_revenue, 1) OVER (PARTITION BY category_name ORDER BY sales_month ASC) AS previous_month_revenue
    FROM monthly_category_revenue
)
SELECT 
    sales_month,
    category_name,
    ROUND(monthly_net_revenue, 2) AS current_month_revenue_inr,
    ROUND(previous_month_revenue, 2) AS previous_month_revenue_inr,
    ROUND(monthly_net_revenue - previous_month_revenue, 2) AS absolute_growth_inr,
    CASE 
        WHEN previous_month_revenue > 0 
        THEN ROUND(((monthly_net_revenue - previous_month_revenue) / previous_month_revenue) * 100.0, 2)
        ELSE NULL 
    END AS mom_growth_pct
FROM revenue_lag_calc
WHERE previous_month_revenue IS NOT NULL
ORDER BY sales_month DESC, mom_growth_pct DESC;
```

---

## 4. Dark Store Revenue Contribution & Pareto (80/20) Audit

```yaml
metadata:
  pillar: "Sales & Revenue Performance"
  category: "Store Performance"
  intent: "pareto_revenue_analysis_by_store"
  complexity: "Advanced"
  tables: ["orders", "dark_stores", "cities"]
```

### User Prompt
"Perform a Pareto (80/20) revenue distribution analysis on all active dark stores for the current year. Calculate cumulative revenue percentage contribution to classify top revenue-driving stores."

### Executable MySQL Query
```sql
WITH store_revenue AS (
    SELECT 
        ds.store_id,
        ds.store_name,
        c.city_name,
        SUM(o.final_amount) AS store_total_revenue
    FROM orders AS o
    INNER JOIN dark_stores AS ds ON o.store_id = ds.store_id
    INNER JOIN cities AS c ON ds.city_id = c.city_id
    WHERE o.status = 'Delivered'
      AND o.order_timestamp >= DATE_FORMAT(NOW(), '%Y-01-01')
    GROUP BY ds.store_id, ds.store_name, c.city_name
),
total_system_revenue AS (
    SELECT SUM(store_total_revenue) AS overall_revenue FROM store_revenue
),
cumulative_revenue AS (
    SELECT 
        sr.store_name,
        sr.city_name,
        sr.store_total_revenue,
        SUM(sr.store_total_revenue) OVER (ORDER BY sr.store_total_revenue DESC) AS running_cumulative_revenue,
        tsr.overall_revenue
    FROM store_revenue AS sr
    CROSS JOIN total_system_revenue AS tsr
)
SELECT 
    store_name,
    city_name,
    ROUND(store_total_revenue, 2) AS store_revenue_inr,
    ROUND((store_total_revenue / overall_revenue) * 100.0, 2) AS revenue_share_pct,
    ROUND((running_cumulative_revenue / overall_revenue) * 100.0, 2) AS cumulative_revenue_pct,
    CASE 
        WHEN (running_cumulative_revenue / overall_revenue) * 100.0 <= 80.0 THEN 'Tier A: Top 80% Revenue Driver'
        ELSE 'Tier B: Remaining Contribution'
    END AS pareto_classification
FROM cumulative_revenue
ORDER BY store_total_revenue DESC;
```

---

## 5. Discount Reliance & Margin Erosion Matrix

```yaml
metadata:
  pillar: "Sales & Revenue Performance"
  category: "Margin & Discounts"
  intent: "analyze_discount_impact_on_margins"
  complexity: "Advanced"
  tables: ["orders", "order_items", "products", "categories"]
```

### User Prompt
"Identify products with over 15% discount impact relative to gross sales over the last 60 days. Show gross revenue, total discount loss, estimated product cost, net margin, and tag margin-eroded items."

### Executable MySQL Query
```sql
WITH product_financial_summary AS (
    SELECT 
        p.product_id,
        p.product_name,
        cat.category_name,
        SUM(oi.quantity) AS total_units_sold,
        SUM(oi.quantity * oi.unit_price) AS gross_sales,
        SUM(oi.discount) AS total_discounts,
        SUM(oi.quantity * p.unit_cost) AS total_cogs
    FROM order_items AS oi
    INNER JOIN orders AS o ON oi.order_id = o.order_id
    INNER JOIN products AS p ON oi.product_id = p.product_id
    INNER JOIN categories AS cat ON p.category_id = cat.category_id
    WHERE o.status = 'Delivered'
      AND o.order_timestamp >= NOW() - INTERVAL 60 DAY
    GROUP BY p.product_id, p.product_name, cat.category_name
),
margin_analysis AS (
    SELECT 
        product_name,
        category_name,
        total_units_sold,
        gross_sales,
        total_discounts,
        total_cogs,
        (gross_sales - total_discounts) AS net_sales,
        (gross_sales - total_discounts - total_cogs) AS net_margin,
        (total_discounts / NULLIF(gross_sales, 0)) * 100.0 AS discount_pct_of_gross
    FROM product_financial_summary
)
SELECT 
    product_name,
    category_name,
    total_units_sold,
    ROUND(gross_sales, 2) AS gross_sales_inr,
    ROUND(total_discounts, 2) AS total_discounts_inr,
    ROUND(net_margin, 2) AS net_margin_inr,
    ROUND(discount_pct_of_gross, 2) AS discount_pct_of_gross,
    ROUND((net_margin / NULLIF(net_sales, 0)) * 100.0, 2) AS net_margin_pct,
    CASE 
        WHEN net_margin < 0 THEN 'CRITICAL: Negative Margin Product'
        WHEN discount_pct_of_gross >= 20.0 THEN 'HIGH RISK: Excessive Discounting'
        ELSE 'MODERATE RISK'
    END AS erosion_risk_status
FROM margin_analysis
WHERE discount_pct_of_gross >= 15.0
ORDER BY net_margin ASC;
```

---

# Part 2: Inventory & Supply Chain Health

---

## 6. Real-Time Low Stock & Stockout Risk Warning

```yaml
metadata:
  pillar: "Inventory & Supply Chain Health"
  category: "Stock Monitoring"
  intent: "detect_stockout_risk_and_reorder_needs"
  complexity: "Advanced"
  tables: ["inventory", "products", "dark_stores", "cities"]
```

### User Prompt
"Identify all products across active dark stores where current stock levels are at or below reorder levels. Include days of available inventory based on average daily velocity over the last 14 days."

### Executable MySQL Query
```sql
WITH daily_product_velocity AS (
    SELECT 
        o.store_id,
        oi.product_id,
        SUM(oi.quantity) / 14.0 AS avg_daily_sales
    FROM orders AS o
    INNER JOIN order_items AS oi ON o.order_id = oi.order_id
    WHERE o.status = 'Delivered'
      AND o.order_timestamp >= NOW() - INTERVAL 14 DAY
    GROUP BY o.store_id, oi.product_id
)
SELECT 
    c.city_name,
    ds.store_name,
    p.product_name,
    i.current_stock,
    i.reorder_level,
    COALESCE(ROUND(dpv.avg_daily_sales, 2), 0.00) AS avg_daily_sales_units,
    CASE 
        WHEN COALESCE(dpv.avg_daily_sales, 0) = 0 THEN 999.0
        ELSE ROUND(i.current_stock / dpv.avg_daily_sales, 1)
    END AS estimated_days_stock_remaining,
    CASE 
        WHEN i.current_stock = 0 THEN 'CRITICAL: Out of Stock'
        WHEN i.current_stock <= (i.reorder_level * 0.5) THEN 'HIGH RISK: Immediate Restock Required'
        ELSE 'WARNING: Reorder Threshold Reached'
    END AS stock_status
FROM inventory AS i
INNER JOIN dark_stores AS ds ON i.store_id = ds.store_id
INNER JOIN cities AS c ON ds.city_id = c.city_id
INNER JOIN products AS p ON i.product_id = p.product_id
LEFT JOIN daily_product_velocity AS dpv ON i.store_id = dpv.store_id AND i.product_id = dpv.product_id
WHERE i.current_stock <= i.reorder_level
ORDER BY estimated_days_stock_remaining ASC, i.current_stock ASC;
```

---

## 7. Inventory Turnover Ratio & Aging Analysis

```yaml
metadata:
  pillar: "Inventory & Supply Chain Health"
  category: "Inventory Efficiency"
  intent: "analyze_inventory_turnover_and_holding_costs"
  complexity: "Advanced"
  tables: ["inventory", "products", "categories", "order_items", "orders"]
```

### User Prompt
"Calculate the inventory turnover ratio and average holding days by product category over the last 90 days. Flag categories with slow-moving inventory."

### Executable MySQL Query
```sql
WITH category_sales_cogs AS (
    SELECT 
        cat.category_id,
        cat.category_name,
        SUM(oi.quantity * p.unit_cost) AS total_cogs_90_days
    FROM order_items AS oi
    INNER JOIN orders AS o ON oi.order_id = o.order_id
    INNER JOIN products AS p ON oi.product_id = p.product_id
    INNER JOIN categories AS cat ON p.category_id = cat.category_id
    WHERE o.status = 'Delivered'
      AND o.order_timestamp >= NOW() - INTERVAL 90 DAY
    GROUP BY cat.category_id, cat.category_name
),
category_inventory_valuation AS (
    SELECT 
        cat.category_id,
        SUM(i.current_stock * p.unit_cost) AS current_inventory_value
    FROM inventory AS i
    INNER JOIN products AS p ON i.product_id = p.product_id
    INNER JOIN categories AS cat ON p.category_id = cat.category_id
    GROUP BY cat.category_id
)
SELECT 
    csc.category_name,
    ROUND(civ.current_inventory_value, 2) AS current_inventory_value_inr,
    ROUND(csc.total_cogs_90_days, 2) AS total_cogs_90_days_inr,
    ROUND(csc.total_cogs_90_days / NULLIF(civ.current_inventory_value, 0), 2) AS inventory_turnover_ratio,
    ROUND(90.0 / NULLIF((csc.total_cogs_90_days / NULLIF(civ.current_inventory_value, 0)), 0), 1) AS avg_days_to_sell_inventory,
    CASE 
        WHEN (csc.total_cogs_90_days / NULLIF(civ.current_inventory_value, 0)) < 1.5 THEN 'SLOW MOVING: High Carrying Cost Risk'
        WHEN (csc.total_cogs_90_days / NULLIF(civ.current_inventory_value, 0)) >= 4.0 THEN 'HIGH TURNOVER: Fast Moving'
        ELSE 'HEALTHY TURNOVER'
    END AS inventory_health_status
FROM category_sales_cogs AS csc
INNER JOIN category_inventory_valuation AS civ ON csc.category_id = civ.category_id
ORDER BY inventory_turnover_ratio ASC;
```

---

## 8. Supplier Delivery Performance & On-Time In-Full (OTIF) Metric

```yaml
metadata:
  pillar: "Inventory & Supply Chain Health"
  category: "Supplier Performance"
  intent: "evaluate_supplier_otif_compliance"
  complexity: "Advanced"
  tables: ["purchase_orders", "suppliers", "dark_stores"]
```

### User Prompt
"Evaluate supplier fulfillment performance over the last 180 days using On-Time, In-Full (OTIF) rates, average delay days, and total order fulfillment rate."

### Executable MySQL Query
```sql
WITH po_metrics AS (
    SELECT 
        s.supplier_id,
        s.supplier_name,
        po.po_id,
        po.expected_delivery_date,
        po.actual_delivery_date,
        po.ordered_quantity,
        po.received_quantity,
        CASE WHEN po.actual_delivery_date <= po.expected_delivery_date THEN 1 ELSE 0 END AS is_on_time,
        CASE WHEN po.received_quantity >= po.ordered_quantity THEN 1 ELSE 0 END AS is_in_full,
        CASE WHEN (po.actual_delivery_date <= po.expected_delivery_date AND po.received_quantity >= po.ordered_quantity) THEN 1 ELSE 0 END AS is_otif,
        DATEDIFF(po.actual_delivery_date, po.expected_delivery_date) AS delay_days
    FROM purchase_orders AS po
    INNER JOIN suppliers AS s ON po.supplier_id = s.supplier_id
    WHERE po.status = 'Received'
      AND po.created_at >= NOW() - INTERVAL 180 DAY
)
SELECT 
    supplier_name,
    COUNT(po_id) AS total_purchase_orders,
    ROUND((SUM(is_on_time) / COUNT(po_id)) * 100.0, 2) AS on_time_rate_pct,
    ROUND((SUM(is_in_full) / COUNT(po_id)) * 100.0, 2) AS in_full_rate_pct,
    ROUND((SUM(is_otif) / COUNT(po_id)) * 100.0, 2) AS otif_compliance_rate_pct,
    ROUND(AVG(GREATEST(delay_days, 0)), 1) AS avg_delay_days,
    CASE 
        WHEN (SUM(is_otif) / COUNT(po_id)) * 100.0 >= 90.0 THEN 'Preferred Supplier (Tier 1)'
        WHEN (SUM(is_otif) / COUNT(po_id)) * 100.0 >= 75.0 THEN 'Standard Supplier (Tier 2)'
        ELSE 'Underperforming: SLA Penalty Risk'
    END AS supplier_rating
FROM po_metrics
GROUP BY supplier_id, supplier_name
HAVING COUNT(po_id) >= 3
ORDER BY otif_compliance_rate_pct DESC;
```