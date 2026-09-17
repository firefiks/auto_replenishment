# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AutoReplenishmentAnalysis(models.Model):
    _inherit = 'auto.replenishment.analysis'

    @api.model
    def _existing_open_line(self, product, company):
        """Return True when an open RFQ or confirmed PO line already exists."""
        return bool(self.env['purchase.order.line'].sudo().search([
            ('product_id', '=', product.id),
            ('company_id', '=', company.id),
            ('order_id.state', 'in', ['draft', 'sent', 'to approve', 'purchase']),
        ], limit=1))

    def action_create_rfq(self):
        self.ensure_one()
        if self.recommended_qty <= 0:
            raise UserError(_(
                'No stock coverage gap for %s: current stock covers the expected demand. '
                'Nothing to order.') % self.product_id.display_name)
        if not self.vendor_id:
            raise UserError(_(
                'No vendor configured for %s. Add a supplier (Products -> %s -> Purchase) '
                'before creating an RFQ.') % (self.product_id.display_name, self.product_id.display_name))
        if self.rfq_id and self.rfq_id.state in ('draft', 'sent', 'to approve'):
            raise UserError(_(
                'A draft RFQ (%s) already exists for %s. Cancel or confirm it before creating a new one.')
                % (self.rfq_id.name, self.product_id.display_name))
        if self._existing_open_line(self.product_id, self.company_id):
            raise UserError(_(
                'An open RFQ / confirmed purchase order line already exists for %s (%s). '
                'No duplicate will be created.') % (
                self.product_id.display_name, self.company_id.name))

        product = self.product_id.with_company(self.company_id)
        qty = self.recommended_qty
        date_planned = fields.Datetime.now() + timedelta(days=self.vendor_lead_time or 0)

        line_vals = {
            'product_id': product.id,
            'product_qty': qty,
            'product_uom_id': product.uom_id.id,
            'date_planned': date_planned,
        }
        po_vals = {
            'partner_id': self.vendor_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.company_id.currency_id.id,
            'origin': '%s (%s)' % (self.product_id.default_code or self.product_id.name, self._name),
            'date_order': date_planned,
            'order_line': [(0, 0, line_vals)],
        }
        po = self.env['purchase.order'].sudo().with_company(self.company_id).create(po_vals)
        self.write({'rfq_id': po.id})
        return {
            'name': _('RFQ'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
        }