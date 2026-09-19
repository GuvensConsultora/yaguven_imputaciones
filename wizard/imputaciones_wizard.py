# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError


class ImputacionesWizard(models.TransientModel):
    """Arma el detalle que se le manda al proveedor o al cliente: qué canceló cada
    comprobante, y qué pagos quedaron a cuenta.

    El mismo dato se puede leer de las dos puntas, y cuál sirve depende de la pregunta:

    - **Por factura**: «esta factura, ¿con qué se pagó?». Es la del que revisa la deuda.
    - **Por recibo**: «este pago, ¿qué facturas cubrió?». Es la que hace el proveedor
      cuando reclama, porque él identifica el pago por el cheque que recibió y no sabe
      contra qué se aplicó.

    Las dos salen de `yaguven.imputacion`, así que no pueden discutir entre sí: es la
    misma fila agrupada por un lado o por el otro.
    """

    _name = 'yaguven.imputaciones.wizard'
    _description = 'Detalle de imputaciones por contacto'

    partner_id = fields.Many2one('res.partner', string='Contacto', required=True)
    tipo = fields.Selection(
        [('proveedor', 'Proveedor'), ('cliente', 'Cliente')],
        string='Cuenta', required=True, default='proveedor',
    )
    vista = fields.Selection(
        [('comprobante', 'Por factura: con qué se canceló cada una'),
         ('pago', 'Por recibo: qué facturas cubrió cada pago')],
        string='Cómo se ordena', required=True, default='comprobante',
    )
    date_from = fields.Date(string='Desde')
    date_to = fields.Date(string='Hasta')
    solo_pendientes = fields.Boolean(
        string='Sólo lo que tiene saldo', default=False,
        help='Por factura: deja afuera las que ya quedaron canceladas por completo.\n'
             'Por recibo: deja sólo los pagos que todavía tienen importe sin aplicar.',
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

    def _tipo_cuenta(self):
        self.ensure_one()
        return 'liability_payable' if self.tipo == 'proveedor' else 'asset_receivable'

    def _ids_partner(self):
        """Todos los contactos de la misma cuenta corriente: casa central y sus hijos.

        Las facturas y los pagos pueden estar cargados en cualquiera de ellos y el
        proveedor los ve como una sola cuenta.
        """
        self.ensure_one()
        comercial = self.partner_id.commercial_partner_id or self.partner_id
        return set(self.env['res.partner'].search([('id', 'child_of', comercial.id)]).ids)

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
        # Los que no tienen ninguna imputación van en su lugar cronológico, no en un
        # apartado: para el que lee la cuenta son un movimiento más.
        salida = list(docs.values()) + self.sin_imputar()
        salida.sort(key=lambda d: (d['fecha'] or date.min, d['move'].name or ''))
        if self.solo_pendientes:
            redondeo = self.company_id.currency_id.rounding
            salida = [d for d in salida
                      if self.company_id.currency_id.compare_amounts(d['saldo'], 0) != 0
                      or redondeo is None]
        return salida

    def sin_imputar(self):
        """Comprobantes del contacto que TODAVÍA no tienen ninguna imputación.

        Sin esto el documento muestra sólo lo que ya se cruzó, y deja afuera justo lo que
        el proveedor viene a reclamar: lo que se le debe. En PROINFER eran 3 facturas por
        $6.654.463,37 sobre 97 movimientos — el conteo cerraba y la deuda no aparecía.

        Se dejan afuera los pagos, porque los que quedaron sin aplicar ya salen en
        `a_cuenta()`: contarlos dos veces haría que el total del documento mienta.
        """
        self.ensure_one()
        comercial = self.partner_id.commercial_partner_id or self.partner_id
        dom = [('partner_id', 'child_of', comercial.id),
               ('account_id.account_type', '=', self._tipo_cuenta()),
               ('parent_state', '=', 'posted'),
               ('payment_id', '=', False),
               ('company_id', '=', self.company_id.id)]
        if self.date_from:
            dom.append(('date', '>=', self.date_from))
        if self.date_to:
            dom.append(('date', '<=', self.date_to))
        docs = {}
        for l in self.env['account.move.line'].search(dom, order='date, id'):
            if l.matched_debit_ids or l.matched_credit_ids:
                continue
            m = l.move_id
            docs.setdefault(m.id, {
                'move': m,
                'fecha': l.date,
                'total': m.amount_total,
                'saldo': m.amount_residual,
                'cancelaciones': [],
                'imputado': 0.0,
            })
        return list(docs.values())

    def detalle_por_pago(self):
        """El mismo detalle dado vuelta: cada recibo con las facturas que cubrió.

        Recorre las mismas imputaciones que `detalle()` pero agrupa por el comprobante
        que cancela, así que los importes de las dos vistas son el mismo número leído
        de distinta manera.
        """
        self.ensure_one()
        ids_partner = self._ids_partner()
        filas = self.env['yaguven.imputacion'].search(
            self._dominio(), order='canc_date, canc_move_id, doc_date')
        pagos = {}
        for f in filas:
            p = pagos.get(f.canc_move_id.id)
            if p is None:
                p = self._cabecera_pago(f.canc_move_id, f.payment_id, ids_partner)
                pagos[f.canc_move_id.id] = p
            p['aplicaciones'].append(f)
            p['imputado'] += f.amount

        # Un pago que quedó ENTERO a cuenta no tiene ninguna imputación, así que no
        # aparece recorriendo las imputaciones. Es justamente el que el proveedor no
        # encuentra —cobró la plata y no la ve contra ninguna factura—, así que se
        # agrega acá para que el detalle lo muestre con su importe sin aplicar.
        for linea in self.a_cuenta():
            if linea.move_id.id not in pagos:
                pagos[linea.move_id.id] = self._cabecera_pago(
                    linea.move_id, linea.payment_id, ids_partner)

        salida = sorted(pagos.values(),
                        key=lambda p: (p['fecha'] or date.min, p['move'].name or ''))
        if self.solo_pendientes:
            moneda = self.company_id.currency_id
            salida = [p for p in salida if not moneda.is_zero(p['sin_aplicar'])]
        return salida

    def _cabecera_pago(self, move, payment, ids_partner):
        """Cuánto movió ese comprobante en la cuenta corriente, y cuánto quedó sin aplicar.

        El importe NO sale de `amount_total`: cuando el pago lleva retención, ese total
        incluye la base imponible y no coincide con lo que el pago descarga de la cuenta
        corriente. Se mide sobre las líneas del asiento en la cuenta a cobrar / a pagar,
        que son exactamente las que se imputan — así `importe = imputado + sin aplicar`
        cierra solo, y esa igualdad es la que hace verificable el PDF.

        Se filtra además por contacto: un pago puede cancelar comprobantes de más de un
        proveedor, y en ese caso sólo corresponde mostrar la parte de este.
        """
        self.ensure_one()
        tipo_cuenta = self._tipo_cuenta()
        moneda = self.company_id.currency_id
        lineas = move.line_ids.filtered(
            lambda l: l.account_id.account_type == tipo_cuenta
            and l.partner_id.id in ids_partner)
        # El residuo de centavo se limpia con el redondeo de la moneda y no con un
        # umbral fijo: un «a cuenta 0,01» en el PDF le hace buscar al proveedor una
        # diferencia que no existe.
        sin_aplicar = sum(abs(l.amount_residual) for l in lineas)
        if moneda.is_zero(sin_aplicar):
            sin_aplicar = 0.0
        return {
            'move': move,
            'fecha': move.date,
            'payment': payment,
            'cheque': ', '.join(
                self.env['yaguven.imputacion']._numeros_de_cheque(payment)),
            'diario': move.journal_id,
            'diario_nombre': move.journal_id.display_name or '',
            'importe': sum(abs(l.balance) for l in lineas),
            'sin_aplicar': sin_aplicar,
            'aplicaciones': [],
            'imputado': 0.0,
        }

    def referencias(self, filas):
        """Los diarios que aparecen en ESTE documento, con un comprobante de ejemplo.

        Los códigos de comprobante —`SI-P1`, `PCSHCQ`, `PECHQ3`, `Aj+/-`— no le dicen
        nada a quien no configuró los diarios, y el proveedor que recibe el PDF menos
        todavía. El significado NO se escribe a mano en una tabla fija: se lee del
        diario de cada comprobante, que es el que le puso el nombre. Si mañana el
        cliente renombra un diario o crea otro, la leyenda lo sigue sola.

        Se listan sólo los que aparecen en el documento, y con un comprobante real de
        ejemplo en vez de un prefijo recortado: el lector hace el match con lo que tiene
        a la vista, sin que nadie tenga que adivinar dónde corta el código.
        """
        self.ensure_one()
        vistos = {}

        def anotar(move):
            diario = move.journal_id
            if diario and diario.id not in vistos:
                vistos[diario.id] = {'diario': diario.display_name, 'ejemplo': move.name}

        for f in filas:
            anotar(f['move'])
            if self.vista == 'pago':
                for a in f['aplicaciones']:
                    anotar(a.doc_move_id)
            else:
                for c in f['cancelaciones']:
                    anotar(c.canc_move_id)
        return sorted(vistos.values(), key=lambda d: d['diario'])

    def a_cuenta(self):
        """Pagos del contacto con saldo sin aplicar todavía.

        Son los que generan la pregunta del proveedor: el importe está en su cuenta pero
        no figura contra ninguna factura.
        """
        self.ensure_one()
        comercial = self.partner_id.commercial_partner_id or self.partner_id
        dom = [('partner_id', 'child_of', comercial.id),
               ('account_id.account_type', '=', self._tipo_cuenta()),
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
        hay = self.detalle_por_pago() if self.vista == 'pago' else self.detalle()
        if not hay and not self.a_cuenta():
            raise UserError(
                'No hay imputaciones para %s en ese período.\n\n'
                'Puede ser que los comprobantes estén sin conciliar todavía, o que el '
                'período elegido no los incluya.' % self.partner_id.display_name)
        return self.env.ref(
            'yaguven_imputaciones.action_report_imputaciones').report_action(self)

    def ver_en_pantalla(self):
        self.ensure_one()
        agrupar = 'search_default_g_canc' if self.vista == 'pago' else 'search_default_g_doc'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Imputaciones de %s' % self.partner_id.display_name,
            'res_model': 'yaguven.imputacion',
            'view_mode': 'list',
            'domain': self._dominio(),
            'context': {agrupar: 1},
        }


def _plata(valor):
    """1234567.89 → «1.234.567,89». Formato argentino."""
    return f'{valor or 0:,.2f}'.replace(',', '@').replace('.', ',').replace('@', '.')


def _fecha(valor):
    return valor.strftime('%d/%m/%Y') if valor else ''


class ReportImputaciones(models.AbstractModel):
    _name = 'report.yaguven_imputaciones.report_imputaciones'
    _description = 'Detalle de imputaciones'

    @api.model
    def _get_report_values(self, docids, data=None):
        """OJO ODOO 19: `formatLang` y `format_date` NO están en el contexto de un
        informe QWeb propio — el render revienta con un 500 sin traceback en la página
        de error. Los helpers de formato se pasan acá, explícitamente."""
        wizards = self.env['yaguven.imputaciones.wizard'].browse(docids)
        # El detalle se calcula UNA vez por asistente: la leyenda de diarios sale de
        # esas mismas filas, no de una segunda pasada por la base.
        filas = {w.id: (w.detalle_por_pago() if w.vista == 'pago' else w.detalle())
                 for w in wizards}
        # El total se suma acá y no en la plantilla: QWeb evalúa con `safe_eval` y una
        # expresión generadora adentro es justo lo que revienta sin traceback útil.
        impagos = {w.id: w.sin_imputar() for w in wizards if w.vista == 'pago'}
        return {
            'doc_ids': docids,
            'doc_model': 'yaguven.imputaciones.wizard',
            'docs': wizards,
            'detalle': {w.id: filas[w.id] for w in wizards if w.vista == 'comprobante'},
            'por_pago': {w.id: filas[w.id] for w in wizards if w.vista == 'pago'},
            'referencias': {w.id: w.referencias(filas[w.id]) for w in wizards},
            # Por recibo los comprobantes impagos no son un recibo, así que no pueden ir
            # en el cuerpo: van en su propia sección al final.
            'sin_imputar': {w.id: impagos[w.id] for w in wizards if w.vista == 'pago'},
            'sin_imputar_total': {w.id: sum(abs(d['saldo']) for d in impagos[w.id])
                                  for w in wizards if w.vista == 'pago'},
            'a_cuenta': {w.id: w.a_cuenta() for w in wizards},
            'plata': _plata,
            'fecha': _fecha,
        }
