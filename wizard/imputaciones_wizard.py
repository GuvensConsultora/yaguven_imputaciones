# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class ImputacionesWizard(models.TransientModel):
    """Arma el detalle que se le manda al proveedor o al cliente: qué canceló cada
    comprobante, y qué pagos quedaron a cuenta."""

    _name = 'yaguven.imputaciones.wizard'
    _description = 'Detalle de imputaciones por contacto'

    partner_id = fields.Many2one('res.partner', string='Contacto', required=True)
    tipo = fields.Selection(
        [('proveedor', 'Proveedor'), ('cliente', 'Cliente')],
        string='Cuenta', required=True, default='proveedor',
    )
    date_from = fields.Date(string='Desde')
    date_to = fields.Date(string='Hasta')
    solo_pendientes = fields.Boolean(
        string='Sólo comprobantes con saldo', default=False,
        help='Deja afuera los comprobantes que ya quedaron cancelados por completo.',
    )
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company,
    )

    # -------------------------------------------------------------------------
    # El detalle se arma sobre `yaguven.imputacion`, la misma vista que muestra la
    # pantalla: si las dos no coinciden, el PDF que recibe el proveedor discute con lo
    # que ve el operador.
    # -------------------------------------------------------------------------
    def _dominio(self):
        self.ensure_one()
        comercial = self.partner_id.commercial_partner_id or self.partner_id
        dom = [('partner_id', 'child_of', comercial.id),
               ('tipo', '=', self.tipo),
               ('company_id', '=', self.company_id.id)]
        if self.date_from:
            dom.append(('doc_date', '>=', self.date_from))
        if self.date_to:
            dom.append(('doc_date', '<=', self.date_to))
        return dom

    def detalle(self):
        """Comprobantes con sus cancelaciones, en orden de fecha."""
        self.ensure_one()
        filas = self.env['yaguven.imputacion'].search(
            self._dominio(), order='doc_date, doc_move_id, canc_date')
        docs = {}
        for f in filas:
            d = docs.setdefault(f.doc_move_id.id, {
                'move': f.doc_move_id,
                'fecha': f.doc_date,
                'total': f.doc_total,
                'saldo': f.doc_residual,
                'cancelaciones': [],
                'imputado': 0.0,
            })
            d['cancelaciones'].append(f)
            d['imputado'] += f.amount
        salida = list(docs.values())
        if self.solo_pendientes:
            redondeo = self.company_id.currency_id.rounding
            salida = [d for d in salida
                      if self.company_id.currency_id.compare_amounts(d['saldo'], 0) != 0
                      or redondeo is None]
        return salida

    def a_cuenta(self):
        """Pagos del contacto con saldo sin aplicar todavía.

        Son los que generan la pregunta del proveedor: el importe está en su cuenta pero
        no figura contra ninguna factura.
        """
        self.ensure_one()
        comercial = self.partner_id.commercial_partner_id or self.partner_id
        tipo_cuenta = ('liability_payable' if self.tipo == 'proveedor'
                       else 'asset_receivable')
        dom = [('partner_id', 'child_of', comercial.id),
               ('account_id.account_type', '=', tipo_cuenta),
               ('parent_state', '=', 'posted'),
               ('payment_id', '!=', False),
               ('amount_residual', '!=', 0),
               ('company_id', '=', self.company_id.id)]
        if self.date_from:
            dom.append(('date', '>=', self.date_from))
        if self.date_to:
            dom.append(('date', '<=', self.date_to))
        return self.env['account.move.line'].search(dom, order='date, id')

    def imprimir(self):
        self.ensure_one()
        if not self.detalle() and not self.a_cuenta():
            raise UserError(
                'No hay imputaciones para %s en ese período.\n\n'
                'Puede ser que los comprobantes estén sin conciliar todavía, o que el '
                'período elegido no los incluya.' % self.partner_id.display_name)
        return self.env.ref(
            'yaguven_imputaciones.action_report_imputaciones').report_action(self)

    def ver_en_pantalla(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Imputaciones de %s' % self.partner_id.display_name,
            'res_model': 'yaguven.imputacion',
            'view_mode': 'list',
            'domain': self._dominio(),
            'context': {'search_default_g_doc': 1},
        }


class ReportImputaciones(models.AbstractModel):
    _name = 'report.yaguven_imputaciones.report_imputaciones'
    _description = 'Detalle de imputaciones'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['yaguven.imputaciones.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'yaguven.imputaciones.wizard',
            'docs': wizards,
            'detalle': {w.id: w.detalle() for w in wizards},
            'a_cuenta': {w.id: w.a_cuenta() for w in wizards},
        }
