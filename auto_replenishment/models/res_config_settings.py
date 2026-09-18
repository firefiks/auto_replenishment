# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Period windows (days)
    ar_period_short = fields.Integer(
        'Short-Term Window (days)',
        config_parameter='auto_replenishment.period.short', default=7,
        help='Shortest demand window. 0 disables the short-term aggregation.')
    ar_period_medium = fields.Integer(
        'Medium-Term Window (days)',
        config_parameter='auto_replenishment.period.medium', default=30)
    ar_period_long = fields.Integer(
        'Long-Term Window (days)',
        config_parameter='auto_replenishment.period.long', default=90)
    ar_period_long_term = fields.Integer(
        'Longest-Term Window (days)',
        config_parameter='auto_replenishment.period.long_term', default=365)
    ar_trend_window = fields.Integer(
        'Trend Window (days)',
        config_parameter='auto_replenishment.trend_window_days', default=30,
        help='How many days back to compare for the DEMAND INCREASING / NEW DEMAND signal.')

    # Conversion & demand
    ar_fallback_conversion = fields.Float(
        'Fallback Conversion Rate (%)',
        config_parameter='auto_replenishment.fallback_conversion_rate', default=30.0,
        help='Percentage (0-100). Used when no conversion history is available.')
    ar_min_conversion_sample = fields.Integer(
        'Min Conversion Sample Size',
        config_parameter='auto_replenishment.min_conversion_sample', default=3,
        help='Minimum number of decided orders before the historical rate is accepted.')
    ar_growth_threshold = fields.Float(
        'Growth Threshold for DEMAND INCREASING (%)',
        config_parameter='auto_replenishment.growth_threshold', default=50.0,
        help='Current window quotation qty must exceed previous window by this '
             'percentage (0-100) to trigger the DEMAND INCREASING status.')
    ar_safety_stock = fields.Float(
        'Safety Stock (Product UoM)',
        config_parameter='auto_replenishment.safety_stock', default=0.0,
        help='Added to expected demand before comparing against stock.')

    # Channel filter
    ar_channel_filter = fields.Selection([
        ('all', 'All Sales'),
        ('webshop', 'Webshop Only'),
        ('manual', 'Manual Sales Only'),
        ('other', 'Other Channels Only'),
    ], string='Channel Filter', config_parameter='auto_replenishment.channel_filter', default='all',
        help='Scope the demand aggregation. "Other Channels" covers rental/repair.')
    ar_auto_create_rfq = fields.Boolean(
        'Auto-Create Draft RFQs',
        config_parameter='auto_replenishment.auto_create_rfq', default=False,
        help='If enabled the daily cron creates draft RFQs for every REPLENISH '
             'and URGENT product. OFF by default: use the manual "Create RFQ" button.')

    # Discuss / Reporting
    ar_discuss_enabled = fields.Boolean(
        'Discuss Integration',
        config_parameter='auto_replenishment.discuss_enabled', default=True,
        help='Disable to stop posting replenishment updates to the Discuss channel '
             '(analysis still runs; RFQ button still available).')
    ar_discuss_channel_name = fields.Char(
        'Discuss Channel Name',
        config_parameter='auto_replenishment.discuss_channel_name', default='AutoReplenishment')
    ar_report_interval_days = fields.Integer(
        'Report Minimum Interval (days)',
        config_parameter='auto_replenishment.report_interval_days', default=1,
        help='A product whose hash has not changed and whose last report was within '
             'this interval will not be re-posted to Discuss.')
    ar_report_urgent_only = fields.Boolean(
        'Report only URGENT items to Discuss',
        config_parameter='auto_replenishment.report_urgent_only', default=True,
        help='When enabled, only URGENT products are posted to the Discuss channel. '
             'When disabled, all actionable statuses are reported '
             '(REPLENISH, DEMAND INCREASING, WATCH and URGENT).')