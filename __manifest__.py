# -*- coding: utf-8 -*-
{
    "name": "Imputaciones de cuenta corriente (Yagüven)",
    "summary": "Qué pago canceló cada factura, y qué quedó a cuenta, por cliente y por proveedor.",
    "description": """
El dato de con qué pago se cancela cada factura ya existe en la contabilidad: es cada
imputación (partial reconcile) entre la factura y el comprobante que la cancela. Lo que
no se puede leer es la pantalla de apuntes, que muestra todos los movimientos del
contacto bajo un mismo emparejamiento.

Este módulo expone esas imputaciones una por una, en una lista de SÓLO LECTURA: no crea,
no modifica y no concilia nada. Cada fila es un par comprobante ↔ cancelación con su
importe imputado.

- Sirve igual para clientes y para proveedores: el lado que suma deuda lo determina el
  tipo de cuenta (a cobrar o a pagar), no el tipo de comprobante.
- Las notas de crédito y los ajustes se muestran como lo que son: comprobantes que
  cancelan, al mismo nivel que un pago. Dejarlos afuera haría que las cifras no cierren.
- Cuando el pago se hizo con cheque, se muestra el número de cheque: es el dato que
  reconoce el proveedor, no el número interno del pago.
""",
    "version": "19.0.1.1.3",
    "category": "Accounting",
    "author": "Yagüven C.G.",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "views/imputacion_views.xml",
        "views/res_partner_views.xml",
        "wizard/imputaciones_wizard_views.xml",
        "report/imputaciones_report.xml",
    ],
    "installable": True,
    "application": False,
}
