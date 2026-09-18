# -*- coding: utf-8 -*-
from odoo import api, fields, models


class YaguvenImputacion(models.Model):
    """Una fila por imputación (account.partial.reconcile) de cuenta corriente.

    Vista SQL de sólo lectura: no se escribe nada, no se concilia nada. El registro
    contable es el que ya existe; acá sólo se lo muestra de a un par por vez.

    Qué lado es el comprobante y qué lado la cancelación lo define el TIPO DE CUENTA,
    no el tipo de comprobante:

    - a cobrar (cliente): la factura está en el DEBE, lo que la cancela en el HABER.
    - a pagar (proveedor): la factura está en el HABER, lo que la cancela en el DEBE.

    Resolverlo por `move_type` sería un error: una nota de crédito de proveedor cancela
    como un pago, y un par factura ↔ NC tiene comprobante de los dos lados.
    """

    _name = 'yaguven.imputacion'
    _description = 'Imputación de cuenta corriente'
    _auto = False
    _order = 'partner_id, doc_date, doc_move_id, date'
    _rec_name = 'doc_move_id'

    tipo = fields.Selection(
        [('cliente', 'Cliente'), ('proveedor', 'Proveedor')],
        string='Tipo', readonly=True,
    )
    partner_id = fields.Many2one('res.partner', string='Contacto', readonly=True)
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        related='company_id.currency_id', readonly=True,
    )
    account_id = fields.Many2one('account.account', string='Cuenta', readonly=True)

    # ── El comprobante que generó la deuda o el crédito ───────────────────────
    doc_move_id = fields.Many2one('account.move', string='Comprobante', readonly=True)
    doc_date = fields.Date(string='Fecha comprobante', readonly=True)
    doc_total = fields.Monetary(
        string='Total comprobante',
        related='doc_move_id.amount_total', currency_field='currency_id', readonly=True,
    )
    doc_residual = fields.Monetary(
        string='Saldo del comprobante',
        related='doc_move_id.amount_residual', currency_field='currency_id', readonly=True,
    )
    doc_state = fields.Selection(
        related='doc_move_id.payment_state', string='Estado de pago', readonly=True,
    )

    # ── El comprobante que lo cancela: pago, nota de crédito o ajuste ─────────
    canc_move_id = fields.Many2one('account.move', string='Cancelado con', readonly=True)
    canc_date = fields.Date(string='Fecha de la cancelación', readonly=True)
    payment_id = fields.Many2one('account.payment', string='Pago', readonly=True)
    journal_id = fields.Many2one(
        related='canc_move_id.journal_id', string='Diario', readonly=True,
    )
    cheque = fields.Char(string='Cheque', compute='_compute_cheque', readonly=True)

    # ── La imputación propiamente dicha ───────────────────────────────────────
    date = fields.Date(string='Fecha de imputación', readonly=True)
    amount = fields.Monetary(
        string='Importe imputado', currency_field='currency_id', readonly=True,
    )

    @api.depends('payment_id')
    def _compute_cheque(self):
        """Número de cheque del pago, cuando lo hay.

        El proveedor identifica el pago por el cheque, no por el número interno. El
        módulo de cheques (l10n_latam_check de ADHOC) puede no estar instalado, así que
        los campos se consultan antes de usarlos en vez de declararse como dependencia:
        sin cheques la columna queda vacía y la pantalla funciona igual.
        """
        campos = self.env['account.payment']._fields
        nombres = [c for c in ('l10n_latam_move_check_ids', 'l10n_latam_new_check_ids')
                   if c in campos]
        for rec in self:
            numeros = []
            for nombre in nombres:
                for cheque in rec.payment_id[nombre] if rec.payment_id else []:
                    if cheque.name and cheque.name not in numeros:
                        numeros.append(cheque.name)
            rec.cheque = ', '.join(numeros)

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS yaguven_imputacion CASCADE")
        self.env.cr.execute("""
            CREATE VIEW yaguven_imputacion AS (
                SELECT
                    apr.id                AS id,
                    apr.company_id        AS company_id,
                    apr.max_date          AS date,
                    apr.amount            AS amount,
                    CASE WHEN aa.account_type = 'asset_receivable'
                         THEN 'cliente' ELSE 'proveedor' END          AS tipo,
                    CASE WHEN aa.account_type = 'asset_receivable'
                         THEN deb.partner_id ELSE cre.partner_id END  AS partner_id,
                    CASE WHEN aa.account_type = 'asset_receivable'
                         THEN deb.account_id ELSE cre.account_id END  AS account_id,
                    CASE WHEN aa.account_type = 'asset_receivable'
                         THEN deb.move_id ELSE cre.move_id END        AS doc_move_id,
                    CASE WHEN aa.account_type = 'asset_receivable'
                         THEN deb.date ELSE cre.date END              AS doc_date,
                    CASE WHEN aa.account_type = 'asset_receivable'
                         THEN cre.move_id ELSE deb.move_id END        AS canc_move_id,
                    CASE WHEN aa.account_type = 'asset_receivable'
                         THEN cre.date ELSE deb.date END              AS canc_date,
                    CASE WHEN aa.account_type = 'asset_receivable'
                         THEN cre.payment_id ELSE deb.payment_id END  AS payment_id
                FROM account_partial_reconcile apr
                JOIN account_move_line deb ON deb.id = apr.debit_move_id
                JOIN account_move_line cre ON cre.id = apr.credit_move_id
                JOIN account_account    aa ON aa.id = deb.account_id
                WHERE aa.account_type IN ('asset_receivable', 'liability_payable')
            )
        """)
