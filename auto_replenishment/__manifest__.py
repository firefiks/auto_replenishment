{
    'name': 'Auto Replenishment',
    'version': '19.0.1.2.0',
    'category': 'Inventory/Purchase',
    'summary': 'Explainable replenishment recommendations based on sales quotations',
    'description': 'Analyse sales quotations and confirmed orders, compute transparent demand-based '
                   'replenishment recommendations, report actionable findings to a Discuss channel '
                   'and optionally create draft RFQs. Never creates purchases automatically by default.',
    'license': 'LGPL-3',
    'author': 'firefiks',
    'website': 'https://github.com/firefiks',
    'support': 'icedfox@gmail.com',
    'price': 49,
    'currency': 'EUR',
    'images': [
        'static/description/images/main_screenshot.png',
        'static/description/images/discuss_screenshot.png',
        'static/description/images/analysis_list_screenshot.png',
        'static/description/images/settings_screenshot.png',
    ],
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