# -*- coding: utf-8 -*-
from odoo import _, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_yaguven_imputaciones(self):
        """Abre las imputaciones del contacto desde su ficha.

        El filtro va por `child_of` sobre el contacto comercial: las facturas y los
        pagos pueden estar cargados en la casa central o en una dirección de entrega,
        y el proveedor los ve como una sola cuenta corriente.
        """
        self.ensure_one()
        comercial = self.commercial_partner_id or self
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imputaciones de %s', comercial.display_name),
            'res_model': 'yaguven.imputacion',
            'view_mode': 'list',
            'domain': [('partner_id', 'child_of', comercial.id)],
            'context': {'search_default_g_doc': 1},
        }
