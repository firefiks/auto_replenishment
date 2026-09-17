{
    'name': 'Auto Replenishment',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Explainable replenishment recommendations based on sales quotations',
    'description': 'Analyse sales quotations and confirmed orders, compute transparent demand-based '
                   'replenishment recommendations, report actionable findings to a Discuss channel '
                   'and optionally create draft RFQs. Never creates purchases automatically by default.',
    'license': 'LGPL-3',
    'author': 'firefiks',
    'website': 'https://github.com/firefiks',
    'post_init_hook': 'post_init',
    'depends': [
        'sale',
        'stock',
        'purchase',
        'mail',
    ],
    'data': [
        'security/auto_replenishment_security.xml',
        'security/ir.model.access.csv',
        'data/auto_replenishment_cron.xml',
        'views/auto_replenishment_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'application': False,
    'installable': True,
    'auto_install': False,
}