# Prompt-SQL Index Collection

This collection contains few-shot prompt examples and target SQL queries mapped across all analytical pillars.

---

## Pillar 1: Inventory & Supply Chain Health

---
metadata:
  pillar: "Inventory & Supply Chain Health"
  category: "Low Stock Alert"
  intent: "Identify SKUs falling below reorder thresholds in specific geographic regions"
  complexity: "Intermediate"
user_query: "Identify low inventory stock products in South Indian cities with stock below 2 units."
sql_query: |
  SELECT 
      p.product_id,
      p.product_name,
      i.sku_code,
      i.current_stock,
      ds.store_name,
      c.city_name,
      c.state
  FROM inventory AS i
  JOIN dark_stores AS ds ON i.store_id = ds.store_id
  JOIN cities AS c ON ds.city_id = c.city_id
  JOIN products AS p ON i.product_id = p.product_id
  WHERE c.state IN ('Karnataka', 'Tamil Nadu', 'Kerala', 'Andhra Pradesh', 'Telangana')
    AND i.current_stock < 2
  ORDER BY i.current_stock ASC;
---

---
metadata:
  pillar: "Inventory & Supply Chain Health"
  category: "Inventory Shrinkage & Damage"
  intent: "Calculate total stock loss due to damage or expiration per dark store"
  complexity: "Intermediate"
user_query: "Show me the top 5 dark stores with the highest inventory shrinkage due to expired or damaged items this month."
sql_query: |
  SELECT 
      ds.store_id,
      ds.store_name,
      c.city_name,
      SUM(il.quantity) AS total_units_lost,
      SUM(il.quantity * p.unit_cost) AS total_financial_loss
  FROM inventory_logs AS il
  JOIN dark_stores AS ds ON il.store_id = ds.store_id
  JOIN cities AS c ON ds.city_id = c.city_id
  JOIN products AS p ON il.product_id = p.product_id
  WHERE il.reason_code IN ('EXPIRED', 'DAMAGED', 'SPOILAGE')
    AND il.created_at >= DATE_TRUNC('month', CURRENT_DATE)
  GROUP BY ds.store_id, ds.store_name, c.city_name
  ORDER BY total_financial_loss DESC
  LIMIT 5;
---

---
metadata:
  pillar: "Inventory & Supply Chain Health"
  category: "Stockout Risk & Days of Supply"
  intent: "Estimate days of supply remaining based on average 7-day velocity"
  complexity: "Advanced"
user_query: "Which fast-moving products are at risk of stocking out within 2 days based on recent sales speed?"
sql_query: |
  WITH daily_velocity AS (
      SELECT 
          oi.product_id,
          o.store_id,
          SUM(oi.quantity) / 7.0 AS avg_daily_sales
      FROM order_items AS oi
      JOIN orders AS o ON oi.order_id = o.order_id
      WHERE o.order_timestamp >= CURRENT_DATE - INTERVAL '7 days'
        AND o.status = 'Delivered'
      GROUP BY oi.product_id, o.store_id
  )
  SELECT 
      p.product_name,
      ds.store_name,
      i.current_stock,
      ROUND(v.avg_daily_sales, 2) AS daily_sales_rate,
      ROUND(i.current_stock / NULLIF(v.avg_daily_sales, 0), 1) AS estimated_days_of_supply
  FROM inventory AS i
  JOIN daily_velocity AS v ON i.product_id = v.product_id AND i.store_id = v.store_id
  JOIN products AS p ON i.product_id = p.product_id
  JOIN dark_stores AS ds ON i.store_id = ds.store_id
  WHERE (i.current_stock / NULLIF(v.avg_daily_sales, 0)) < 2.0
  ORDER BY estimated_days_of_supply ASC;
---

---

## Pillar 2: Sales & Revenue Performance

---
metadata:
  pillar: "Sales & Revenue Performance"
  category: "Regional Sales Ranking"
  intent: "Rank top selling products within each state using window functions"
  complexity: "Advanced"
user_query: "What are the top 5 best-selling products in each South Indian state?"
sql_query: |
  WITH product_sales AS (
      SELECT
          p.product_id,
          p.product_name,
          c.state,
          SUM(oi.quantity) AS total_quantity_sold,
          SUM(oi.quantity * oi.unit_price) AS total_revenue
      FROM orders AS o
      JOIN dark_stores AS ds ON o.store_id = ds.store_id
      JOIN cities AS c ON ds.city_id = c.city_id
      JOIN order_items AS oi ON o.order_id = oi.order_id
      JOIN products AS p ON oi.product_id = p.product_id
      WHERE c.state IN ('Karnataka', 'Tamil Nadu', 'Kerala', 'Andhra Pradesh', 'Telangana')
        AND o.status = 'Delivered'
      GROUP BY p.product_id, p.product_name, c.state
  ),
  ranked_sales AS (
      SELECT
          product_id,
          product_name,
          state,
          total_quantity_sold,
          total_revenue,
          ROW_NUMBER() OVER (PARTITION BY state ORDER BY total_quantity_sold DESC) AS rank_in_state
      FROM product_sales
  )
  SELECT
      product_id,
      product_name,
      state,
      total_quantity_sold,
      total_revenue,
      rank_in_state
  FROM ranked_sales
  WHERE rank_in_state <= 5
  ORDER BY state, rank_in_state;
---

---
metadata:
  pillar: "Sales & Revenue Performance"
  category: "Category Revenue Contribution"
  intent: "Calculate gross merchandise value (GMV) breakdown by category and state"
  complexity: "Intermediate"
user_query: "Show total gross revenue and total orders breakdown by product category for Maharashtra last month."
sql_query: |
  SELECT 
      cat.category_name,
      COUNT(DISTINCT o.order_id) AS total_orders,
      SUM(o.final_amount) AS total_gmv,
      AVG(o.final_amount) AS average_order_value
  FROM orders AS o
  JOIN dark_stores AS ds ON o.store_id = ds.store_id
  JOIN cities AS c ON ds.city_id = c.city_id
  JOIN order_items AS oi ON o.order_id = oi.order_id
  JOIN products AS p ON oi.product_id = p.product_id
  JOIN categories AS cat ON p.category_id = cat.category_id
  WHERE c.state = 'Maharashtra'
    AND o.status = 'Delivered'
    AND o.order_timestamp >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
    AND o.order_timestamp < DATE_TRUNC('month', CURRENT_DATE)
  GROUP BY cat.category_name
  ORDER BY total_gmv DESC;
---

---

## Pillar 3: Operational Efficiency & Logistics

---
metadata:
  pillar: "Operational Efficiency & Logistics"
  category: "Order Cancellation & Failure Analysis"
  intent: "Analyze failed orders aggregated by city and state with hierarchical rankings"
  complexity: "Advanced"
user_query: "Which cities and states have the highest order failure counts, and how are states ranked overall?"
sql_query: |
  WITH city_failures AS (
      SELECT
          c.state,
          c.city_name,
          COUNT(*) AS failed_orders
      FROM orders AS o
      JOIN dark_stores AS ds ON o.store_id = ds.store_id
      JOIN cities AS c ON ds.city_id = c.city_id
      WHERE o.status = 'Cancelled'
      GROUP BY c.state, c.city_name
  ),
  state_failures AS (
      SELECT
          state,
          SUM(failed_orders) AS state_failed_orders
      FROM city_failures
      GROUP BY state
  )
  SELECT
      cf.state,
      cf.city_name,
      cf.failed_orders,
      sf.state_failed_orders,
      RANK() OVER (ORDER BY sf.state_failed_orders DESC) AS state_rank
  FROM city_failures cf
  JOIN state_failures sf ON cf.state = sf.state
  ORDER BY sf.state_failed_orders DESC, cf.failed_orders DESC;
---

---
metadata:
  pillar: "Operational Efficiency & Logistics"
  category: "Delivery SLA & Delay Analysis"
  intent: "Calculate average delivery time breach across dark stores"
  complexity: "Intermediate"
user_query: "Find dark stores where average delivery time exceeds the promised 15-minute SLA threshold."
sql_query: |
  SELECT 
      ds.store_id,
      ds.store_name,
      c.city_name,
      COUNT(o.order_id) AS total_deliveries,
      ROUND(AVG(EXTRACT(EPOCH FROM (o.delivered_at - o.order_timestamp))/60), 2) AS avg_delivery_time_minutes,
      COUNT(CASE WHEN EXTRACT(EPOCH FROM (o.delivered_at - o.order_timestamp))/60 > 15 THEN 1 END) AS sla_breached_orders
  FROM orders AS o
  JOIN dark_stores AS ds ON o.store_id = ds.store_id
  JOIN cities AS c ON ds.city_id = c.city_id
  WHERE o.status = 'Delivered'
    AND o.delivered_at IS NOT NULL
  GROUP BY ds.store_id, ds.store_name, c.city_name
  HAVING AVG(EXTRACT(EPOCH FROM (o.delivered_at - o.order_timestamp))/60) > 15.0
  ORDER BY avg_delivery_time_minutes DESC;
---

---

## Pillar 4: Customer Behavior & Retention

---
metadata:
  pillar: "Customer Behavior & Retention"
  category: "Cohort Analysis & Customer Lifetime Value"
  intent: "Analyze spend and order frequency segmented by customer loyalty tier and acquisition channel"
  complexity: "Intermediate"
user_query: "What is the average customer spend and order count across different loyalty tiers and acquisition channels?"
sql_query: |
  SELECT 
      m.attribute_value AS loyalty_tier,
      cust.acquisition_channel,
      COUNT(DISTINCT cust.customer_id) AS total_customers,
      ROUND(AVG(cust_summary.total_spend), 2) AS avg_lifetime_spend,
      ROUND(AVG(cust_summary.total_orders), 1) AS avg_orders_per_customer
  FROM customers AS cust
  JOIN master_data AS m ON cust.loyalty_tier_code = m.attribute_code AND m.attribute_type = 'LOYALTY_TIER'
  JOIN (
      SELECT 
          customer_id,
          SUM(final_amount) AS total_spend,
          COUNT(order_id) AS total_orders
      FROM orders
      WHERE status = 'Delivered'
      GROUP BY customer_id
  ) AS cust_summary ON cust.customer_id = cust_summary.customer_id
  GROUP BY m.attribute_value, cust.acquisition_channel
  ORDER BY avg_lifetime_spend DESC;
---

---
metadata:
  pillar: "Customer Behavior & Retention"
  category: "Refund & Feedback Analysis"
  intent: "Identify top refund reasons mapped from master lookup tables"
  complexity: "Basic"
user_query: "List top reasons for customer refund requests along with refund volume and total refunded amount."
sql_query: |
  SELECT 
      m.attribute_value AS refund_reason,
      COUNT(r.refund_id) AS total_refund_claims,
      SUM(r.refund_amount) AS total_refunded_value
  FROM refunds AS r
  JOIN master_data AS m ON r.reason_code = m.attribute_code AND m.attribute_type = 'REFUND_REASON'
  WHERE r.status = 'Approved'
  GROUP BY m.attribute_value
  ORDER BY total_refunded_value DESC;
---