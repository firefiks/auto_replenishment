# -*- coding: utf-8 -*-

import hashlib
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models


class AutoReplenishmentReport(models.TransientModel):
    _name = 'auto.replenishment.report'
    _description = 'Auto Replenishment Report Engine'

    @api.model
    def _find_or_create_channel(self):
        """Locate the #AutoReplenishment channel; create it only if configured."""
        name = self.env['auto.replenishment.analysis']._channel_name()
        channel = self.env['discuss.channel'].sudo().search([
            ('name', '=', name),
            ('channel_type', '=', 'channel'),
        ], limit=1)
        if not channel:
            if self.env['auto.replenishment.analysis']._get_cfg(
                    'auto_replenishment.discuss_enabled', 'True') == 'True':
                channel = self.env['discuss.channel'].sudo().create({
                    'name': name,
                    'channel_type': 'channel',
                })
        return channel

    @api.model
    def _report_hash(self, values):
        raw = '|'.join(str(v) for v in [
            values.get('status', ''),
            round(values.get('recommended_qty', 0), 2),
            round(values.get('open_quotation_qty', 0), 2),
            round(values.get('growth_rate', 0), 2),
        ])
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    def _build_message(self, records, company):
        """Compose a single summary message for one company."""
        if not records:
            return Markup('')
        colors = {'red': '#d9534f', 'orange': '#f0ad4e', 'black': '#333333'}
        band_order = {'red': 0, 'orange': 1, 'black': 2}

        def band(rec):
            if rec.recommended_qty >= 5:
                return 'red'
            if rec.recommended_qty >= 1:
                return 'orange'
            return 'black'

        lines = [
            '<strong>Auto Replenishment Update — %s</strong>' % escape(company.name),
            '',
            'Products with actionable status:',
            '',
        ]
        for rec in sorted(records, key=lambda r: band_order[band(r)]):
            status_label = dict(rec._fields['status'].selection).get(rec.status, rec.status)
            vendor_txt = escape(rec.vendor_id.name) if rec.vendor_id else 'not configured'
            lead_txt = ' (lead time %s days)' % int(rec.vendor_lead_time) if rec.vendor_lead_time else ''
            lines.append(
                '<span style="color:%s">• <strong>%s</strong> (%s) — %s. '
                'Recommended order: %.1f units. Vendor: %s%s.</span>' % (
                    colors[band(rec)],
                    escape(rec.product_tmpl_id.display_name),
                    escape(rec.product_id.default_code or '-'),
                    escape(status_label),
                    rec.recommended_qty,
                    vendor_txt,
                    lead_txt,
                ))
        return Markup('<br>'.join(lines))

    def _cron_run_analysis_and_report(self):
        """Cron entry point: run analysis, then post actionable changes to Discuss."""
        analysis_model = self.env['auto.replenishment.analysis']
        analysis_model._run_analysis_all()
        self._report_to_discuss()

    def _report_to_discuss(self):
        """Post only records whose status/recommended_qty changed since last report."""
        interval_days = int(float(
            self.env['auto.replenishment.analysis']._get_cfg(
                'auto_replenishment.report_interval_days', '1')))
        interval = timedelta(days=max(interval_days, 1))
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)

        urgent_only = self.env['auto.replenishment.analysis']._get_cfg(
            'auto_replenishment.report_urgent_only', 'True') == 'True'
        status_domain = (('status', 'in', ['urgent', 'replenish'])) if urgent_only else ('status', '!=', 'normal')

        channel = self._find_or_create_channel()
        if not channel:
            return

        for company in self.env.companies.sudo():
            today_records = self.env['auto.replenishment.analysis'].sudo().search([
                ('company_id', '=', company.id),
                ('date', '=', today),
                status_domain,
            ])
            if not today_records:
                continue

            pending = []
            for rec in today_records:
                new_hash = self._report_hash(rec.read([
                    'status', 'recommended_qty', 'open_quotation_qty', 'growth_rate'])[0])
                if new_hash == rec.last_reported_hash:
                    continue
                rec_last = rec.last_reported
                if rec_last and (now - rec_last) < interval:
                    continue
                pending.append((rec, new_hash))

            if not pending:
                continue

            msg = self._build_message([p[0] for p in pending], company)
            if msg:
                channel.sudo().message_post(body=msg, message_type='notification')

            for rec, h in pending:
                rec.sudo().write({'last_reported_hash': h, 'last_reported': now})