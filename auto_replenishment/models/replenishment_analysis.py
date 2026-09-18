# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models


class AutoReplenishmentAnalysis(models.Model):
    _name = 'auto.replenishment.analysis'
    _description = 'Auto Replenishment Analysis'
    _order = 'date desc, product_id'
    _check_company_auto = True

    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        ondelete='cascade', index=True)
    product_tmpl_id = fields.Many2one(
        'product.template', string='Product Template',
        related='product_id.product_tmpl_id', readonly=True)
    default_code = fields.Char('Internal Reference', related='product_id.default_code', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    date = fields.Date('Analysis Date', required=True, index=True, default=fields.Date.context_today)
    last_analysis = fields.Datetime('Last Analysis', readonly=True)
    sales_channel = fields.Selection([
        ('all', 'All Sales'),
        ('webshop', 'Webshop'),
        ('manual', 'Manual Sales'),
        ('other', 'Other Sales Channels'),
    ], string='Sales Channel', index=True, readonly=True)

    # --- Sales demand (quotations vs confirmed), expressed in product UoM ---
    open_quotation_qty = fields.Float('Open Quotation Qty', readonly=True, digits='Product Unit')
    open_quotation_count = fields.Integer('Open Quotations', readonly=True)

    quotation_qty_7 = fields.Float('Quotation Qty (7d)', readonly=True, digits='Product Unit')
    quotation_count_7 = fields.Integer('Quotations (7d)', readonly=True)
    quotation_qty_30 = fields.Float('Quotation Qty (30d)', readonly=True, digits='Product Unit')
    quotation_count_30 = fields.Integer('Quotations (30d)', readonly=True)
    quotation_qty_90 = fields.Float('Quotation Qty (90d)', readonly=True, digits='Product Unit')
    quotation_count_90 = fields.Integer('Quotations (90d)', readonly=True)
    quotation_qty_365 = fields.Float('Quotation Qty (365d)', readonly=True, digits='Product Unit')
    quotation_count_365 = fields.Integer('Quotations (365d)', readonly=True)

    confirmed_qty_7 = fields.Float('Confirmed Qty (7d)', readonly=True, digits='Product Unit')
    confirmed_count_7 = fields.Integer('Confirmed Orders (7d)', readonly=True)
    confirmed_qty_30 = fields.Float('Confirmed Qty (30d)', readonly=True, digits='Product Unit')
    confirmed_count_30 = fields.Integer('Confirmed Orders (30d)', readonly=True)
    confirmed_qty_90 = fields.Float('Confirmed Qty (90d)', readonly=True, digits='Product Unit')
    confirmed_count_90 = fields.Integer('Confirmed Orders (90d)', readonly=True)
    confirmed_qty_365 = fields.Float('Confirmed Qty (365d)', readonly=True, digits='Product Unit')
    confirmed_count_365 = fields.Integer('Confirmed Orders (365d)', readonly=True)
    cancelled_count_90 = fields.Integer('Cancelled Orders (90d)', readonly=True)

    # --- Conversion & expected demand ---
    conversion_sample_size = fields.Integer('Conversion Sample Size', readonly=True)
    conversion_rate_base = fields.Float('Historical Conversion Rate (%)', readonly=True)
    conversion_rate = fields.Float('Effective Conversion Rate (%)', readonly=True)
    conversion_fallback = fields.Boolean(
        'Conversion From Fallback', readonly=True,
        help='True when the historical conversion rate could not be computed '
             'reliably and the configured fallback value was used instead.')
    expected_quotation_demand = fields.Float(
        'Expected Quotation Demand', readonly=True, digits='Product Unit',
        help='Open quotation quantity multiplied by the effective conversion rate.')

    # --- Trend ---
    trend_quotation_qty = fields.Float('Trend Window Quotation Qty', readonly=True, digits='Product Unit')
    prev_quotation_qty = fields.Float('Previous Window Quotation Qty', readonly=True, digits='Product Unit')
    trend_confirmed_qty = fields.Float('Trend Window Confirmed Qty', readonly=True, digits='Product Unit')
    prev_confirmed_qty = fields.Float('Previous Window Confirmed Qty', readonly=True, digits='Product Unit')
    demand_trend = fields.Selection([
        ('flat', 'FLAT'),
        ('increasing', 'DEMAND INCREASING'),
        ('new', 'NEW DEMAND'),
        ('decreasing', 'DEMAND DECREASING'),
    ], string='Demand Trend', default='flat', readonly=True,
        help='Deterministic comparison of the current trend window against the '
             'previous window of the same length. NEW DEMAND when there was no '
             'quotation activity in the previous window.')
    growth_rate = fields.Float('Demand Growth Rate (%)', readonly=True)

    # --- Stock position (reused from the stock engine) ---
    safety_stock = fields.Float('Safety Stock', readonly=True, digits='Product Unit')
    qty_on_hand = fields.Float('On Hand', readonly=True, digits='Product Unit')
    qty_incoming = fields.Float('Incoming', readonly=True, digits='Product Unit')
    qty_forecast = fields.Float('Forecast (Virtual Available)', readonly=True, digits='Product Unit')

    # --- Vendor / replenishment parameters ---
    vendor_id = fields.Many2one('res.partner', string='Preferred Vendor', readonly=True)
    vendor_lead_time = fields.Float('Vendor Lead Time (days)', readonly=True)
    vendor_min_qty = fields.Float('Vendor Min Qty', readonly=True, digits='Product Unit')
    purchase_multiple = fields.Float(
        'Purchase Multiple', readonly=True, digits='Product Unit',
        help='Order quantity is rounded up to a multiple of this value when a '
             'reordering rule defines one.')
    has_vendor = fields.Boolean('Vendor Configured', compute='_compute_has_vendor')

    # --- Recommendation ---
    expected_demand = fields.Float('Expected Demand + Safety', readonly=True, digits='Product Unit')
    recommended_qty = fields.Float('Recommended Order Qty', readonly=True, digits='Product Unit')
    status = fields.Selection([
        ('normal', 'NORMAL'),
        ('watch', 'WATCH'),
        ('demand_increasing', 'DEMAND INCREASING'),
        ('replenish', 'REPLENISH'),
        ('urgent', 'URGENT'),
    ], string='Status', index=True, readonly=True)
    color_band = fields.Selection([
        ('red', 'RED (5+)'),
        ('orange', 'ORANGE (1-4)'),
        ('black', 'BLACK (<1)'),
    ], string='Priority', compute='_compute_color_band', store=True, index=True)
    reason = fields.Text('Why this product was flagged', readonly=True)

    # --- Reporting (anti-spam) ---
    last_reported_hash = fields.Char('Last Reported Content Hash', readonly=True, copy=False)
    last_reported = fields.Datetime('Last Reported', readonly=True, copy=False)

    # --- RFQ ---
    rfq_id = fields.Many2one('purchase.order', string='Draft RFQ', readonly=True, index=True)
    rfq_state = fields.Selection(related='rfq_id.state', string='RFQ State', readonly=True)

    @api.depends('vendor_id')
    def _compute_has_vendor(self):
        for rec in self:
            rec.has_vendor = bool(rec.vendor_id)

    @api.depends('recommended_qty')
    def _compute_color_band(self):
        for rec in self:
            if rec.recommended_qty >= 5:
                rec.color_band = 'red'
            elif rec.recommended_qty >= 1:
                rec.color_band = 'orange'
            else:
                rec.color_band = 'black'

    # ------------------------------------------------------------------ #
    # Configuration helpers
    # ------------------------------------------------------------------ #

    @api.model
    def _get_cfg(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(key, default=default)

    @api.model
    def _get_cfg_float(self, key, default=0.0):
        try:
            return float(self._get_cfg(key) or default)
        except (TypeError, ValueError):
            return default

    @api.model
    def _get_cfg_int(self, key, default=0):
        return int(self._get_cfg_float(key, default))

    @api.model
    def _window_days(self):
        cfg = self.sudo()
        return {
            'short': cfg._get_cfg_int('auto_replenishment.period.short', 7),
            'medium': cfg._get_cfg_int('auto_replenishment.period.medium', 30),
            'long': cfg._get_cfg_int('auto_replenishment.period.long', 90),
            'long_term': cfg._get_cfg_int('auto_replenishment.period.long_term', 365),
            'trend': cfg._get_cfg_int('auto_replenishment.trend_window_days', 30),
        }

    @api.model
    def _fallback_conversion_rate(self):
        return self._get_cfg_float('auto_replenishment.fallback_conversion_rate', 30.0) / 100.0

    @api.model
    def _min_conversion_sample(self):
        return self._get_cfg_int('auto_replenishment.min_conversion_sample', 3)

    @api.model
    def _growth_threshold(self):
        return self._get_cfg_float('auto_replenishment.growth_threshold', 50.0) / 100.0

    @api.model
    def _safety_stock_value(self):
        return self._get_cfg_float('auto_replenishment.safety_stock', 0.0)

    @api.model
    def _channel_filter(self):
        return self._get_cfg('auto_replenishment.channel_filter', 'all')

    @api.model
    def _channel_name(self):
        return self._get_cfg('auto_replenishment.discuss_channel_name', 'AutoReplenishment')

    # ------------------------------------------------------------------ #
    # Sales demand aggregation (single pass over sale_order_line)
    # ------------------------------------------------------------------ #

    @api.model
    def _build_channel_sql(self, channel):
        """Return the SQL fragment restricting aggregation to a sales channel.

        Degrades gracefully when the website field is not available (website_sale
        not installed) or when no rental/repair type exists.
        """
        if channel == 'all':
            return ''
        has_website = 'website_id' in self.env['sale.order']._fields
        if channel == 'webshop':
            return "AND so.website_id IS NOT NULL" if has_website else "AND 1 = 0"
        if channel == 'manual':
            return "AND so.website_id IS NULL" if has_website else ""
        # 'other' => rental/repair channels when a sale_type field exists
        if 'sale_type' in self.env['sale.order']._fields:
            return "AND so.sale_type IN ('rental', 'repair')"
        return "AND 1 = 0"

    @api.model
    def _compute_sale_stats(self, company, product_ids, channel, windows):
        """Aggregate quotation/confirmed quantities and order counts.

        Expressed in the line UoM; converted to the product UoM on return.
        Returns {product_id: {metric: value}}.
        """
        stats = {pid: {
            'open_qty': 0.0, 'open_ord': 0,
            'quo_qty': {}, 'quo_ord': {}, 'conf_qty': {}, 'conf_ord': {},
            'canc_ord': {}, 'trend_quo_qty': 0.0, 'prev_quo_qty': 0.0,
            'trend_conf': 0.0, 'prev_conf': 0.0,
        } for pid in product_ids}

        if not product_ids:
            return stats

        now = fields.Datetime.now()
        w_cols = []
        params = {}
        max_back = max(max(windows.values()), 2 * windows['trend']) + 10
        params['cutoff'] = now - timedelta(days=max_back)
        params['company_id'] = company.id
        params['product_ids'] = list(product_ids)
        params['trend_start'] = now - timedelta(days=windows['trend'])
        params['trend_prev_start'] = now - timedelta(days=2 * windows['trend'])

        for key, w in windows.items():
            if key == 'trend':
                continue
            start = now - timedelta(days=w)
            params[f'q_s_{w}'] = start
            params[f'c_s_{w}'] = start
            w_cols += [
                f"SUM(CASE WHEN so.state IN ('draft','sent') AND so.date_order >= %(q_s_{w})s "
                f"THEN sol.product_uom_qty ELSE 0 END)::float AS quo_qty_{w}",
                f"COUNT(DISTINCT CASE WHEN so.state IN ('draft','sent') AND so.date_order >= %(q_s_{w})s "
                f"THEN so.id END)::int AS quo_ord_{w}",
                f"SUM(CASE WHEN so.state = 'sale' AND so.date_order >= %(c_s_{w})s "
                f"THEN sol.product_uom_qty ELSE 0 END)::float AS conf_qty_{w}",
                f"COUNT(DISTINCT CASE WHEN so.state = 'sale' AND so.date_order >= %(c_s_{w})s "
                f"THEN so.id END)::int AS conf_ord_{w}",
                f"COUNT(DISTINCT CASE WHEN so.state = 'cancel' AND so.date_order >= %(c_s_{w})s "
                f"THEN so.id END)::int AS canc_ord_{w}",
            ]

        channel_sql = self._build_channel_sql(channel)
        cols_sql = ', '.join(w_cols) if w_cols else 'NULL::double precision AS none_col'
        query = f"""
            SELECT sol.product_id AS product_id,
                   sol.product_uom_id AS product_uom_id,
                   SUM(CASE WHEN so.state IN ('draft','sent') THEN sol.product_uom_qty ELSE 0 END)::float AS open_qty,
                   COUNT(DISTINCT CASE WHEN so.state IN ('draft','sent') THEN so.id END)::int AS open_ord,
                   {cols_sql},
                   SUM(CASE WHEN so.state IN ('draft','sent') AND so.date_order >= %(trend_start)s
                       THEN sol.product_uom_qty ELSE 0 END)::float AS trend_quo_qty,
                   SUM(CASE WHEN so.state IN ('draft','sent') AND so.date_order >= %(trend_prev_start)s
                           AND so.date_order < %(trend_start)s
                       THEN sol.product_uom_qty ELSE 0 END)::float AS prev_quo_qty,
                   SUM(CASE WHEN so.state = 'sale' AND so.date_order >= %(trend_start)s
                       THEN sol.product_uom_qty ELSE 0 END)::float AS trend_conf,
                   SUM(CASE WHEN so.state = 'sale' AND so.date_order >= %(trend_prev_start)s
                           AND so.date_order < %(trend_start)s
                       THEN sol.product_uom_qty ELSE 0 END)::float AS prev_conf
            FROM sale_order_line sol
            INNER JOIN sale_order so ON so.id = sol.order_id
            WHERE sol.product_id = ANY(%(product_ids)s)
              AND sol.company_id = %(company_id)s
              AND so.state IN ('draft','sent','sale','cancel')
              AND so.date_order >= %(cutoff)s
              AND sol.display_type IS NULL
              {channel_sql}
            GROUP BY sol.product_id, sol.product_uom_id
        """
        self.env.flush_all()
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        uom_map = {u['id']: u['factor'] for u in self.env['uom.uom'].sudo().search_read(
            [('id', 'in', [r['product_uom_id'] for r in rows])], ['factor'])}
        product_uom = {p.id: p.uom_id.id for p in self.env['product.product'].sudo().browse(product_ids)}

        def conv(product_id, line_uom, qty):
            if not qty:
                return 0.0
            base = uom_map.get(product_uom.get(product_id))
            if not base:
                return qty
            return qty * uom_map.get(line_uom, base) / base

        for row in rows:
            pid = row['product_id']
            s = stats[pid]
            s['open_qty'] += conv(pid, row['product_uom_id'], row['open_qty'])
            s['open_ord'] += row['open_ord'] or 0
            for key, w in windows.items():
                if key == 'trend':
                    continue
                s['quo_qty'][w] = s['quo_qty'].get(w, 0.0) + conv(pid, row['product_uom_id'], row.get(f'quo_qty_{w}') or 0.0)
                s['quo_ord'][w] = s['quo_ord'].get(w, 0) + (row.get(f'quo_ord_{w}') or 0)
                s['conf_qty'][w] = s['conf_qty'].get(w, 0.0) + conv(pid, row['product_uom_id'], row.get(f'conf_qty_{w}') or 0.0)
                s['conf_ord'][w] = s['conf_ord'].get(w, 0) + (row.get(f'conf_ord_{w}') or 0)
                s['canc_ord'][w] = s['canc_ord'].get(w, 0) + (row.get(f'canc_ord_{w}') or 0)
            s['trend_quo_qty'] += conv(pid, row['product_uom_id'], row['trend_quo_qty'])
            s['prev_quo_qty'] += conv(pid, row['product_uom_id'], row['prev_quo_qty'])
            s['trend_conf'] += conv(pid, row['product_uom_id'], row['trend_conf'])
            s['prev_conf'] += conv(pid, row['product_uom_id'], row['prev_conf'])
        return stats

    @api.model
    def _conversion_rate_for(self, stats):
        """Historical conversion rate = confirmed / (confirmed + cancelled).

        Uses the counts of the 90-day window. Falls back to the configured
        conversion rate when the sample is too small.
        """
        sample_orders = stats['conf_ord'].get(90, 0) + stats['canc_ord'].get(90, 0)
        if sample_orders >= self._min_conversion_sample():
            rate = stats['conf_ord'].get(90, 0) / float(sample_orders)
            return rate, False, sample_orders
        return self._fallback_conversion_rate(), True, sample_orders

    @api.model
    def _assign_status(self, rec_values):
        """Deterministic status assignment from computed values."""
        recommended = rec_values['recommended_qty']
        on_hand = rec_values['qty_on_hand']
        incoming = rec_values['qty_incoming']
        safety = rec_values['safety_stock']
        expected = rec_values['expected_demand']
        forecast = rec_values['qty_forecast']
        growth = rec_values['growth_rate']
        trend = rec_values['demand_trend']
        open_qty = rec_values['open_quotation_qty']
        has_vendor = bool(rec_values.get('vendor_id'))

        if recommended > 0 and has_vendor and (on_hand + incoming) < safety:
            return 'urgent'
        if recommended > 0 and has_vendor:
            return 'replenish'
        if recommended > 0:
            # coverage gap but no vendor configured -> cannot be replenished yet
            return 'watch'
        if trend == 'new' or growth >= self._growth_threshold():
            return 'demand_increasing'
        if open_qty > 0 and expected >= forecast * 0.5:
            return 'watch'
        return 'normal'

    # ------------------------------------------------------------------ #
    # Master analysis run
    # ------------------------------------------------------------------ #

    @api.model
    def _run_analysis_company(self, company):
        """Compute and persist today's analysis records for one company."""
        env = self.env
        channel = self._channel_filter()
        windows = self._window_days()

        products = env['product.product'].with_company(company).sudo().search([
            ('active', '=', True),
            ('sale_ok', '=', True),
            ('is_storable', '=', True),
        ])
        stats = self._compute_sale_stats(company, products.ids, channel, windows)

        # orderpoints for rounding, grouped by product
        orderpoints = env['stock.warehouse.orderpoint'].with_company(company).sudo().search([
            ('company_id', '=', company.id),
            ('active', '=', True),
        ])
        orderpoint_by_product = {op.product_id.id: op for op in orderpoints}

        # preferred vendors grouped by product template
        suppliers = env['product.supplierinfo'].with_company(company).sudo().search([
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
        ])
        vendor_by_tmpl = {}
        for sup in suppliers.sorted(lambda s: (not s.product_tmpl_id, s.sequence, s.partner_id.id)):
            tmpl = sup.product_tmpl_id.id
            if tmpl not in vendor_by_tmpl:
                vendor_by_tmpl[tmpl] = sup

        now = fields.Datetime.now()
        safety = self._safety_stock_value()

        # batch-read stock quantities once (single prefetch for the whole recordset)
        products_ctx = products.with_company(company)
        prod_qty = {p.id: (p.qty_available, p.incoming_qty, p.virtual_available) for p in products_ctx}

        records = []
        for product in products:
            s = stats.get(product.id)
            if s is None:
                continue
            conversion, is_fallback, sample_size = self._conversion_rate_for(s)
            expected_quot = s['open_qty'] * conversion
            trend = 'flat'
            growth = 0.0
            if s['prev_quo_qty'] <= 0:
                if s['trend_quo_qty'] > 0:
                    trend = 'new'
                else:
                    trend = 'flat'
            elif s['trend_quo_qty'] > s['prev_quo_qty']:
                trend = 'increasing'
                growth = (s['trend_quo_qty'] - s['prev_quo_qty']) / s['prev_quo_qty']
            elif s['trend_quo_qty'] < s['prev_quo_qty']:
                trend = 'decreasing'
                growth = -((s['prev_quo_qty'] - s['trend_quo_qty']) / s['prev_quo_qty'])

            on_hand, incoming, forecast = prod_qty.get(product.id, (0.0, 0.0, 0.0))

            vendor = vendor_by_tmpl.get(product.product_tmpl_id.id)
            vendor_id = vendor.partner_id.id if vendor else False
            lead_time = vendor.delay if vendor else 0.0
            vendor_min = vendor.min_qty if vendor else 0.0

            deficit = expected_quot + safety - on_hand - incoming
            raw = max(0.0, deficit)
            multiple = 0.0
            orderpoint = orderpoint_by_product.get(product.id)
            if orderpoint and raw > 0:
                rounded = orderpoint._get_multiple_rounded_qty(raw)
                raw = max(raw, rounded)
                if orderpoint.replenishment_uom_id:
                    multiple = orderpoint.replenishment_uom_id._compute_quantity(1.0, product.uom_id)
            recommended = 0.0
            if raw > 0:
                recommended = max(raw, vendor_min)

            values = {
                'open_quotation_qty': s['open_qty'],
                'open_quotation_count': s['open_ord'],
                **{f'quotation_qty_{k}': s['quo_qty'].get(int(k), 0.0) for k in ('7', '30', '90', '365')},
                **{f'quotation_count_{k}': s['quo_ord'].get(int(k), 0) for k in ('7', '30', '90', '365')},
                **{f'confirmed_qty_{k}': s['conf_qty'].get(int(k), 0.0) for k in ('7', '30', '90', '365')},
                **{f'confirmed_count_{k}': s['conf_ord'].get(int(k), 0) for k in ('7', '30', '90', '365')},
                'cancelled_count_90': s['canc_ord'].get(90, 0),
                'conversion_rate_base': round(conversion * 100, 1),
                'conversion_rate': round(conversion * 100, 1),
                'conversion_fallback': is_fallback,
                'conversion_sample_size': sample_size,
                'expected_quotation_demand': expected_quot,
                'trend_quotation_qty': s['trend_quo_qty'],
                'prev_quotation_qty': s['prev_quo_qty'],
                'trend_confirmed_qty': s['trend_conf'],
                'prev_confirmed_qty': s['prev_conf'],
                'demand_trend': trend,
                'growth_rate': round(growth * 100, 1),
                'safety_stock': safety,
                'qty_on_hand': on_hand,
                'qty_incoming': incoming,
                'qty_forecast': forecast,
                'vendor_id': vendor_id,
                'vendor_lead_time': lead_time,
                'vendor_min_qty': vendor_min,
                'purchase_multiple': multiple,
                'expected_demand': expected_quot + safety,
                'recommended_qty': recommended,
                'last_analysis': now,
            }
            values['status'] = self._assign_status(values)
            values['reason'] = self._build_reason(values, product, vendor)
            records.append((product.id, values))

        # upsert per (product, company, date)
        today = fields.Date.context_today(self)
        existing = self.sudo().search([('company_id', '=', company.id), ('date', '=', today)])
        existing_by_product = {r.product_id.id: r for r in existing}
        to_create, to_write = [], []
        for pid, values in records:
            values = dict(values)
            values['sales_channel'] = channel
            if pid in existing_by_product:
                to_write.append((existing_by_product[pid].id, values))
            else:
                values['product_id'] = pid
                values['company_id'] = company.id
                values['date'] = today
                to_create.append(values)
        if to_create:
            self.sudo().create(to_create)
        for rid, vals in to_write:
            self.sudo().browse(rid).write(vals)
        return len(records)

    @api.model
    def _build_reason(self, values, product, vendor):
        """Human readable explanation of why a product was flagged."""
        parts = []
        trend_label = dict(self._fields['demand_trend'].selection).get(values['demand_trend'], '')
        parts.append(
            "Demand: %s open quotations (%.1f units, %d orders); window demand 7d=%.1f, 30d=%.1f, 90d=%.1f." % (
                '', values['open_quotation_qty'], values['open_quotation_count'],
                values['quotation_qty_7'], values['quotation_qty_30'], values['quotation_qty_90']))
        if values['conversion_fallback']:
            conv_txt = 'fallback (%.0f%%)' % values['conversion_rate_base']
        else:
            conv_txt = '%.1f%% (sample %d)' % (values['conversion_rate_base'], values['conversion_sample_size'])
        parts.append("Conversion rate: %s." % conv_txt)
        parts.append(
            "Expected demand = %.1f units open quotations x conversion => %.1f units (+ safety %.1f)." % (
                values['open_quotation_qty'], values['expected_quotation_demand'], values['safety_stock']))
        parts.append(
            "Stock: on hand %.1f, incoming %.1f, forecast %.1f." % (
                values['qty_on_hand'], values['qty_incoming'], values['qty_forecast']))
        parts.append(
            "Trend: %s (growth %.1f%%, previous window %.1f units)." % (
                trend_label, values['growth_rate'], values['prev_quotation_qty']))
        if vendor:
            parts.append(
                "Vendor: %s (lead time %.0f days, min qty %.1f%s)." % (
                    vendor.partner_id.name, values['vendor_lead_time'], values['vendor_min_qty'],
                    (' target multiple %.1f' % values['purchase_multiple']) if values['purchase_multiple'] else ''))
        else:
            parts.append('Vendor: not configured - no RFQ can be created for this product.')
        if values['recommended_qty'] > 0 and vendor:
            parts.append("Coverage gap = %.1f + safety %.1f - on hand %.1f - incoming %.1f => recommend ordering %.1f units." % (
                values['expected_quotation_demand'], values['safety_stock'],
                values['qty_on_hand'], values['qty_incoming'], values['recommended_qty']))
        elif values['recommended_qty'] > 0:
            parts.append("Coverage gap of %.1f units exists but no vendor is configured, so it cannot be replenished yet." % (
                values['recommended_qty']))
        else:
            parts.append('Current stock covers expected demand; no replenishment needed.')
        return '\n'.join(parts)

    @api.model
    def _run_analysis_all(self):
        counts = []
        for company in self.env.companies.sudo():
            counts.append((company.name, self._run_analysis_company(company)))
        self._cleanup_old_analyses()
        return counts

    @api.model
    def _cleanup_old_analyses(self):
        """Remove analysis records older than the longest window + margin.

        The engine never looks further back than the longest demand window plus
        two trend windows, so anything older is dead weight. Keeps the daily
        snapshot history bounded (about one year by default).
        """
        days = max(self._window_days().values()) + 2 * self._window_days()['trend'] + 30
        cutoff = fields.Date.context_today(self) - timedelta(days=days)
        old = self.sudo().search([('date', '<', cutoff)])
        count = len(old)
        if count:
            old.unlink()
        return count

    def action_run_analysis_now(self):
        self._run_analysis_all()
        action = self.env.ref('auto_replenishment.action_auto_replenishment_demand')
        return action.read()[0]