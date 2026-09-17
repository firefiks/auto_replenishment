# Auto Replenishment (Odoo 19)

Intelligent, explainable replenishment recommendations driven by **sales quotations**
(not just confirmed orders). The module analyses demand, computes a transparent
recommended order quantity per product, reports actionable items to a Discuss
channel, and lets a manager create **draft** RFQs. Nothing is purchased or ordered
automatically unless explicitly enabled.

## What it does

The daily cron (`ir.cron`) runs once per day:

1. For every saleable product, per company, it aggregates quantities from
   `sale.order.line` joined to `sale.order`:

   - **Open quotations**: lines on orders still in `draft` / `sent`.
   - **Window demand**: quotations and confirmed orders in the *short / medium /
     long / longest* windows (default 7, 30, 90, 365 days).
   - Confirmed orders = state `sale`; cancelled orders = state `cancel`.

   Lines with a `display_type` (sections/notes) and cancelled orders are excluded
   from demand. Quantities are converted from the line UoM to the product UoM.

2. **Conversion rate** (historical, deterministic):

   ```
   conversion = confirmed_orders(90d) / (confirmed_orders(90d) + cancelled_orders(90d))
   ```

   Used only when the sample is large enough (`min_conversion_sample`, default 3),
   otherwise the configurable fallback applies (default **30%**).

3. **Expected quotation demand** = `open_quotation_qty × conversion_rate`.

4. **Trend** (deterministic, no forecasting): compares open-quotation quantity in
   the current *trend window* against the previous window of equal length.
   `NEW DEMAND` (previous window empty), `DEMAND INCREASING` (growth ≥ threshold,
   default 50%), decreasing or flat. The previous window must be non-empty.

5. **Stock position** is reused from the stock engine:
   `qty_available` (on hand), `incoming_qty`, `virtual_available` (forecast).

6. **Recommended order quantity**:

   ```
   recommended = max(0,
       expected_quotation_demand + safety_stock
       - qty_on_hand - qty_incoming)
   ```

   Rounded up to the reordering rule's purchase multiple
   (`stock.warehouse.orderpoint.replenishment_uom_id`, via `_get_multiple_rounded_qty`)
   and to the vendor's `min_qty`.

7. **Status** (stored, deterministic):

   | Status            | Condition                                                                   |
   |-------------------|-----------------------------------------------------------------------------|
   | `URGENT`          | recommended > 0, vendor configured, and on hand + incoming < safety stock   |
   | `REPLENISH`       | recommended > 0 and vendor configured                                       |
   | `DEMAND INCREASING` | recommended = 0 and (trend = NEW or growth ≥ threshold)                   |
   | `WATCH`           | recommended = 0 and open demand and expected demand ≥ 50% of forecast; also |
   |                   | recommended > 0 but no vendor configured (cannot be replenished yet)        |
   | `NORMAL`          | otherwise                                                                   |

   Every record stores a human readable `reason` (“Why this product was flagged”).
The Demand Analysis list shows the status as a colored badge (URGENT red,
  REPLENISH orange, WATCH / DEMAND INCREASING info blue) and the demand trend as
  a colored badge (NEW DEMAND red, DEMAND INCREASING orange, FLAT grey,
  DEMAND DECREASING blue).

8. **Discuss reporting**: by default `URGENT` and `REPLENISH` products are posted
   to the `#AutoReplenishment` channel (found by name, created only if missing,
   only when the setting is enabled). A setting ("Only report actionable products
   to Discuss") can be disabled to report every actionable status (non-`NORMAL`).
   Each product line in the message is color-coded by recommended quantity
   (5+ → red, 1–4 → orange, < 1 → black) and lines are sorted red → orange →
   black. Anti-spam: a content hash (`status | recommended | open | growth`) is
   stored per product; a product is re-posted only when the hash **changed** or
   its last post is older than the configured interval (default 1 day).

9. **RFQ (manual only by default)**: the “Create Draft RFQ” button creates a
   `purchase.order` in `draft` using the preferred vendor, with `date_planned =
   now + vendor delay`, respecting min qty and purchase multiple. Duplicates are
   refused when an open RFQ/PO line already exists. The `rfq_id` link is stored on
   the analysis record.

## Installation

```bash
# optional: copy the module into your addons path if not already there
cd /opt/odoo/addons
sudo -u odoo python3 /opt/odoo/odoo-bin -c <your.conf> -d <your_db> -i auto_replenishment --stop-after-init
# restart Odoo
```

Never install on a production database before testing.

## Configuration

Inventory → Configuration → Settings → **Auto Replenishment**:

- **Windows** — short/medium/long/longest (7/30/90/365) and trend window (30).
- **Conversion & signals** — fallback conversion (30%), minimum sample (3),
  growth threshold for `DEMAND INCREASING` (50%), safety stock.
- **Channel filter** — scope demand to All / Webshop / Manual / Other (rental-repair);
  “Webshop” requires `website_sale` (otherwise skipped gracefully).
- **Auto-create RFQ** — **OFF by default**. When enabled the cron creates draft
  RFQs for every actionable product (still never confirms them).
- **Reporting** — toggle Discuss integration, channel name, report interval
  (default posts URGENT + REPLENISH only).

The cron job “Auto Replenishment: Daily Demand Analysis” can be run manually from
Settings → Technical → Automation → Scheduled Actions.

## Tests

```bash
sudo -u odoo python3 /opt/odoo/odoo-bin -c <your.conf> -d fresh_test_db \
  -i auto_replenishment --stop-after-init --test-enable \
  --test-tags post_install:/auto_replenishment
```

Covered: open/confirmed/cancelled demand, display-type exclusion, window scoping,
conversion fallback vs historical, trend (new/flat), the five statuses, min qty and
multiple rounding, company isolation, channel filter, RFQ creation + duplicate
guard + missing-vendor guard, Discuss channel creation + message + anti-spam,
cron idempotency.

## Limitations

- Historical conversion uses *current* order states (confirmed / cancelled) in a
  90-day window; there is no full quotation-history staging.
- Trend is based on quotations that are still open in each window.
- `qty_available` / `incoming_qty` follow the standard per-company warehouse setup.
- RFQs are created draft-only; nothing is automatically confirmed or sent to vendors.
- Analysis covers products flagged `sale_ok` with `is_storable` (stock-tracked goods).

## Files

```
__manifest__.py
models/replenishment_analysis.py   # model + demand/trend/recommendation engine
models/replenishment_rfq.py        # Create Draft RFQ action
models/replenishment_report.py     # cron entry point + Discuss reporting + anti-spam
models/res_config_settings.py      # settings fields
security/…                         # groups + access rights
data/auto_replenishment_cron.xml   # daily cron
views/auto_replenishment_views.xml # menu + list/form/search/pivot/graph
views/res_config_settings_views.xml
tests/test_auto_replenishment.py
```