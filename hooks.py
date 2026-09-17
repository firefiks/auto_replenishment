# -*- coding: utf-8 -*-


def post_init(env):
    """Grant read access to every internal user (base.group_user).

    Done in a hook because `base.group_user` is a noupdate record and cannot be
    reliably extended from the module's XML data on upgrade.
    """
    env.ref('base.group_user').write({
        'implied_ids': [(4, env.ref('auto_replenishment.group_auto_replenishment_user').id)],
    })