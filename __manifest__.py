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

El mismo dato se puede leer de las dos puntas, y se ofrecen las dos porque contestan
preguntas distintas:

- **Por factura**: «esta factura, ¿con qué se pagó?». Es la del que revisa la deuda.
- **Por recibo**: «este pago, ¿qué facturas cubrió?». Es la que hace el proveedor cuando
  reclama, porque identifica el pago por el cheque que recibió y no sabe contra qué se
  aplicó.

En el detalle por recibo el importe del pago NO sale de `amount_total` —con retención ese
total incluye la base imponible—: se mide sobre las líneas del asiento en la cuenta a
cobrar / a pagar, así `importe = aplicado + a cuenta` cierra solo.
""",
    "version": "19.0.1.4.0",
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
