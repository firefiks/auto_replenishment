# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAutoReplenishment(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.ref('base.main_company')

        self.vendor = self.env['res.partner'].create({'name': 'Vendor Test'})
        self.customer = self.env['res.partner'].create({'name': 'Customer Test'})

        self.uom_unit = self.env.ref('uom.product_uom_unit')
        self.uom_box = self.env['uom.uom'].create({
            'name': 'Box-12',
            'relative_uom_id': self.uom_unit.id,
            'relative_factor': 12.0,
        })

        self.product = self.env['product.product'].create({
            'name': 'Test Product AR',
            'type': 'consu',
            'is_storable': True,
            'sale_ok': True,
            'purchase_ok': True,
            'default_code': 'AR-001',
            'uom_id': self.uom_unit.id,
            'seller_ids': [(0, 0, {
                'partner_id': self.vendor.id,
                'min_qty': 12.0,
                'delay': 5,
                'price': 10.0,
            })],
        })

        # Warehouse + stock
        self.warehouse = self.env['stock.warehouse'].create({
            'name': 'Test Warehouse',
            'code': 'TW1',
            'company_id': self.company.id,
        })
        self.store_loc = self.warehouse.lot_stock_id

        self.analysis = self.env['auto.replenishment.analysis']

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _make_order(self, product, qty, state='draft', date_back=0, website=False):
        order = self.env['sale.order'].sudo().create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
        })
        self.env['sale.order.line'].sudo().create({
            'order_id': order.id,
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom_id': product.uom_id.id,
            'price_unit': 1.0,
        })
        if date_back:
            order.write({'date_order': fields.Datetime.now() - timedelta(days=date_back)})
        if state != 'draft':
            order.write({'state': state})
        if website:
            order.write({'website_id': website})
        return order

    def _set_on_hand(self, qty):
        self.env['stock.quant'].sudo()._update_available_quantity(
            self.product, self.store_loc, qty)

    def _set_incoming(self, qty):
        move = self.env['stock.move'].sudo().create({
            'name': 'IN AR test',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.warehouse.in_type_id.default_location_src_id.id,
            'location_dest_id': self.store_loc.id,
        })
        move._action_confirm()
        move._action_assign()

    def _run(self):
        return self.analysis._run_analysis_company(self.company)

    def _record(self):
        return self.analysis.sudo().search([
            ('company_id', '=', self.company.id),
            ('product_id', '=', self.product.id),
        ], limit=1)

    # ------------------------------------------------------------------ #
    # Demand aggregation
    # ------------------------------------------------------------------ #

    def test_open_quotation_counted(self):
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertTrue(rec)
        self.assertEqual(rec.open_quotation_qty, 10.0)
        self.assertEqual(rec.open_quotation_count, 1)
        self.assertGreaterEqual(rec.quotation_qty_7, 10.0)

    def test_confirmed_order_counted(self):
        self._make_order(self.product, 5.0, state='sale', date_back=10)
        self._run()
        rec = self._record()
        self.assertEqual(rec.confirmed_qty_30, 5.0)
        self.assertEqual(rec.confirmed_count_30, 1)
        self.assertGreaterEqual(rec.quotation_qty_30, 0.0)

    def test_cancelled_order_excluded_from_demand(self):
        self._make_order(self.product, 7.0, state='cancel', date_back=5)
        self._run()
        rec = self._record()
        self.assertEqual(rec.open_quotation_qty, 0.0)
        self.assertEqual(rec.confirmed_qty_90, 0.0)
        self.assertEqual(rec.cancelled_count_90, 1)

    def test_display_type_lines_ignored(self):
        order = self._make_order(self.product, 5.0)
        self.env['sale.order.line'].sudo().create({
            'order_id': order.id,
            'display_type': 'line_section',
            'name': 'Section',
        })
        self._run()
        rec = self._record()
        self.assertEqual(rec.open_quotation_qty, 5.0)

    def test_windows_are_scoped(self):
        self._make_order(self.product, 2.0, date_back=200)
        self._run()
        rec = self._record()
        self.assertEqual(rec.quotation_qty_365, 2.0)
        self.assertEqual(rec.quotation_qty_90, 0.0)

    # ------------------------------------------------------------------ #
    # Conversion rate
    # ------------------------------------------------------------------ #

    def test_conversion_fallback_when_no_history(self):
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertTrue(rec.conversion_fallback)
        self.assertAlmostEqual(rec.conversion_rate, 30.0, places=1)

    def test_conversion_historical_used(self):
        for i in range(5):
            self._make_order(self.product, 1.0, state='sale', date_back=i + 1)
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertFalse(rec.conversion_fallback)
        self.assertAlmostEqual(rec.conversion_rate, 100.0, places=1)
        self.assertAlmostEqual(rec.expected_quotation_demand, 10.0, places=1)

    def test_conversion_denominator_includes_cancelled(self):
        for i in range(5):
            self._make_order(self.product, 1.0, state='sale', date_back=i + 1)
        for i in range(5):
            self._make_order(self.product, 1.0, state='cancel', date_back=i + 1)
        self._run()
        rec = self._record()
        self.assertAlmostEqual(rec.conversion_rate, 50.0, places=1)

    # ------------------------------------------------------------------ #
    # Trend
    # ------------------------------------------------------------------ #

    def test_trend_new_demand(self):
        self._set_on_hand(5.0)
        self._make_order(self.product, 3.0, date_back=5)
        self._run()
        rec = self._record()
        self.assertEqual(rec.demand_trend, 'new')

    def test_trend_flat_when_previous_exists(self):
        self._set_on_hand(9.0)
        self._make_order(self.product, 3.0, date_back=5)
        self._make_order(self.product, 3.0, date_back=45)
        self._run()
        rec = self._record()
        self.assertEqual(rec.demand_trend, 'flat')
        self.assertEqual(rec.prev_quotation_qty, 3.0)

    # ------------------------------------------------------------------ #
    # Status & recommendation
    # ------------------------------------------------------------------ #

    def test_status_normal_when_covered(self):
        self._set_on_hand(50.0)
        self._run()
        rec = self._record()
        self.assertEqual(rec.status, 'normal')
        self.assertEqual(rec.recommended_qty, 0.0)

    def test_status_replenish(self):
        self._set_on_hand(2.0)
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertEqual(rec.status, 'replenish')
        self.assertGreater(rec.recommended_qty, 0.0)

    def test_status_urgent_when_backordered(self):
        # negative on hand (backordered), no incoming, safety 0 -> urgent
        self._set_on_hand(-2.0)
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertEqual(rec.status, 'urgent')

    def test_status_replenish_when_out_of_stock(self):
        # zero on hand with open demand and vendor -> replenish (not urgent)
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertEqual(rec.status, 'replenish')

    def test_no_vendor_not_actionable(self):
        # out of stock with open demand but no vendor -> WATCH, not urgent/replenish
        self.product.seller_ids = [(5, 0, 0)]
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertEqual(rec.status, 'watch')
        self.assertGreater(rec.recommended_qty, 0.0)
        self.assertFalse(rec.has_vendor)

    def test_color_band(self):
        # no demand -> recommended 0 -> black
        self._run()
        self.assertEqual(self._record().color_band, 'black')
        # drop vendor min qty so recommendation follows demand directly
        self.product.seller_ids.write({'min_qty': 0.0})
        # 6 units open * 30% = 1.8 -> orange (1..5)
        self._make_order(self.product, 6.0)
        self._run()
        self.assertEqual(self._record().color_band, 'orange')
        # +40 more open units -> (6+40)*30% = 13.8 -> red (>=5)
        self._make_order(self.product, 40.0)
        self._run()
        self.assertEqual(self._record().color_band, 'red')

    def test_recommendation_respects_min_and_multiple(self):
        # fallback conversion 30%; expected = 10 * 0.3 = 3
        # on hand 0 -> deficit 3 -> min_qty 12 -> recommended 12
        orderpoint = self.env['stock.warehouse.orderpoint'].sudo().create({
            'product_id': self.product.id,
            'location_id': self.store_loc.id,
            'company_id': self.company.id,
            'product_min_qty': 0.0,
            'product_max_qty': 100.0,
            'replenishment_uom_id': self.uom_box.id,
        })
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertGreaterEqual(rec.recommended_qty, 12.0)
        self.assertEqual(rec.purchase_multiple, 12.0)
        # multiple of 12 (min_qty 12)
        self.assertEqual(rec.recommended_qty % 12.0, 0.0)
        self.assertTrue(orderpoint.id)

    def test_status_watch(self):
        # on hand covers expected demand (recommended 0), trend flat, but open
        # demand (6 units * 30% conversion = 1.8 expected) is not negligible
        # vs forecast (3 on hand) -> WATCH
        self._set_on_hand(3.0)
        self._make_order(self.product, 3.0, date_back=5)
        self._make_order(self.product, 3.0, date_back=45)
        self._run()
        rec = self._record()
        self.assertEqual(rec.demand_trend, 'flat')
        self.assertEqual(rec.status, 'watch')

    # ------------------------------------------------------------------ #
    # Company isolation
    # ------------------------------------------------------------------ #

    def test_company_isolation(self):
        other_company = self.env['res.company'].create({'name': 'Other AR Company'})
        order = self._make_order(self.product, 9.0)
        order.write({'company_id': other_company.id})
        # main company analysis must not see the other-company order
        self._run()
        self.assertEqual(self._record().open_quotation_qty, 0.0)
        # other company analysis must see it
        self.analysis.with_company(other_company)._run_analysis_company(other_company)
        rec_other = self.analysis.sudo().search([
            ('company_id', '=', other_company.id),
            ('product_id', '=', self.product.id),
        ], limit=1)
        self.assertEqual(rec_other.open_quotation_qty, 9.0)

    # ------------------------------------------------------------------ #
    # Channel filter
    # ------------------------------------------------------------------ #

    def test_channel_filter_webshop_vs_manual(self):
        # needs website_sale installed to have website_id on sale.order
        if 'website_id' not in self.env['sale.order']._fields:
            return
        website = self.env['website'].create({'name': 'Web AR'})
        self._make_order(self.product, 4.0, website=website)
        self._make_order(self.product, 6.0)
        self.env['ir.config_parameter'].sudo().set_param('auto_replenishment.channel_filter', 'webshop')
        self._run()
        self.assertEqual(self._record().open_quotation_qty, 4.0)
        self.env['ir.config_parameter'].sudo().set_param('auto_replenishment.channel_filter', 'manual')
        self._run()
        self.assertEqual(self._record().open_quotation_qty, 6.0)
        self.env['ir.config_parameter'].sudo().set_param('auto_replenishment.channel_filter', 'all')
        self._run()
        self.assertEqual(self._record().open_quotation_qty, 10.0)

    # ------------------------------------------------------------------ #
    # RFQ creation
    # ------------------------------------------------------------------ #

    def _record_replenish(self):
        self._set_on_hand(2.0)
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertEqual(rec.status, 'replenish')
        return rec

    def test_rfq_creation_creates_draft(self):
        rec = self._record_replenish()
        rec.action_create_rfq()
        self.assertTrue(rec.rfq_id)
        self.assertEqual(rec.rfq_id.state, 'draft')
        self.assertEqual(rec.rfq_id.order_line.product_qty, rec.recommended_qty)

    def test_rfq_no_duplicate_when_open_rfq_exists(self):
        rec = self._record_replenish()
        rec.action_create_rfq()
        with self.assertRaises(Exception):
            rec.action_create_rfq()

    def test_rfq_blocked_without_vendor(self):
        self.product.seller_ids = [(5, 0, 0)]
        self._set_on_hand(2.0)
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertEqual(rec.status, 'watch')
        self.assertGreater(rec.recommended_qty, 0.0)
        with self.assertRaises(Exception):
            rec.action_create_rfq()

    # ------------------------------------------------------------------ #
    # Discuss reporting / anti-spam
    # ------------------------------------------------------------------ #

    def test_report_channel_created_and_posted(self):
        # urgent (backordered) so it is reported under the default urgent-only policy
        self._set_on_hand(-2.0)
        self._make_order(self.product, 10.0)
        self._run()
        rec = self._record()
        self.assertEqual(rec.status, 'urgent')
        report = self.env['auto.replenishment.report']
        report._report_to_discuss()
        channel = self.env['discuss.channel'].sudo().search(
            [('name', '=', 'AutoReplenishment'), ('channel_type', '=', 'channel')], limit=1)
        self.assertTrue(channel)
        # posted exactly one message for the actionable record
        self.assertEqual(len(
            self.env['mail.message'].sudo().search(
                [('model', '=', 'discuss.channel'), ('res_id', '=', channel.id)])), 1)
        # record hash persisted -> second call must not re-post
        rec.invalidate_recordset()
        rec = self._record()
        self.assertTrue(rec.last_reported_hash)
        report._report_to_discuss()
        self.assertEqual(len(
            self.env['mail.message'].sudo().search(
                [('model', '=', 'discuss.channel'), ('res_id', '=', channel.id)])), 1)

    # ------------------------------------------------------------------ #
    # Idempotent cron
    # ------------------------------------------------------------------ #

    def test_cron_idempotent_upsert(self):
        self._make_order(self.product, 10.0)
        self._run()
        self._run()
        recs = self.analysis.sudo().search([
            ('company_id', '=', self.company.id),
            ('product_id', '=', self.product.id),
        ])
        self.assertEqual(len(recs), 1)