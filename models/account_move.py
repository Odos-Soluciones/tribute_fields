from odoo import models, fields, api, _
from odoo.exceptions import UserError
from collections import defaultdict
import re

CUSTOMER_DOCUMENTS = ["out_invoice", "out_refund"]
VENDOR_DOCUMENTS = ["in_invoice", "in_refund"]


class AccountMove(models.Model):
    _inherit = "account.move"

    # show_fiscal_fields = fields.Boolean(related="company_id.show_fiscal_fields")
    control_number = fields.Char("Control Number", copy=False)
    fiscal_check = fields.Boolean(
        "Is Fiscal",
        default=False,
        copy=False,
        compute="_compute_fiscal_check",
        readonly=False,
        store=True
    )
    fiscal_correlative = fields.Char("Fiscal Correlative", copy=False)
    invoice_print_method = fields.Selection(
        related="company_id.invoice_print_method")
    ticket_ref = fields.Char("Ticket reference", readonly=True)
    fp_serial_num = fields.Char("Serial number FP", readonly=True)
    num_report_z = fields.Char("Numero de reporte Z", readonly=True)
    is_debit_note = fields.Boolean(compute="_compute_type_of_document")
    is_credit_note = fields.Boolean(compute="_compute_type_of_document")

    def _compute_type_of_document(self):
        for invoice in self:
            invoice.is_debit_note = bool(
                invoice.reversed_entry_id and
                invoice.move_type in ["out_invoice", "in_invoice"]
            )

            invoice.is_credit_note = bool(
                invoice.reversed_entry_id and
                invoice.move_type in ["out_refund", "in_refund"]
            )

    @api.depends("fp_serial_num")
    def _compute_fiscal_check(self):
        for invoice in self:
            invoice.fiscal_check = bool(invoice.fp_serial_num)

    @api.onchange("fiscal_check")
    def onchange_fiscal_check(self):

        def get_max_sequence(sequence_list):
            max_num = -1
            max_sequence = None
            for sequence in sequence_list:
                numbers = "".join(re.findall(r"\d+", sequence or ""))
                if numbers and int(numbers) > max_num:
                    max_num = int(numbers)
                    max_sequence = sequence
            return max_sequence

        def get_next_sequence(sequence):
            flag = True
            sequence_elements = re.split(r"(\d+)", sequence or "")
            sequence_elements.reverse()
            sequence_numbers = len([
                *filter(lambda e: e.isdigit(), sequence_elements)
            ])
            new_sequence = []
            for element in sequence_elements:
                if flag and element.isdigit():
                    sequence_numbers -= 1
                    element_len = len(element)
                    element = str(int(element) + 1).zfill(element_len)
                    flag = False
                    if element_len != len(element) and sequence_numbers:
                        element = "".zfill(element_len)
                        flag = True
                new_sequence.append(element)
            new_sequence.reverse()
            return "".join(new_sequence)

        if self.fiscal_check and not self.fp_serial_num:
            if self.move_type in CUSTOMER_DOCUMENTS:
                moves = self.env["account.move"].search([
                    ("fiscal_check", "=", True),
                    ("move_type", "=", self.move_type),
                    ("company_id", "=", self.company_id.id),
                    ("journal_id", "=", self.journal_id.id),
                ])

                max_control_number = get_max_sequence(
                    moves.mapped("control_number"))
                max_fiscal_correlative = get_max_sequence(
                    moves.mapped("fiscal_correlative"))
                self.control_number = get_next_sequence(max_control_number)
                self.fiscal_correlative = get_next_sequence(
                    max_fiscal_correlative)
        else:
            self.control_number = None
            self.fiscal_correlative = None

    def get_payments_for_fiscal_machine(self):
        invoice_list = list()
        for invoice in self:

            def _get_rate_to_fiscal_currency(from_currency):
                return self.env["res.currency"]._get_conversion_rate(
                    from_currency=from_currency,
                    to_currency=invoice.company_id.fiscal_currency_id or self.env.ref(
                        "base.VEF"),
                    company=invoice.company_id,
                    date=fields.Date.today()
                )

            rml = invoice._get_all_reconciled_invoice_partials()
            invoice_item = {
                "id": invoice.id,
                "name": invoice.name,
                "currency": {
                    "name": invoice.currency_id.name
                    if invoice.currency_id
                    else invoice.company_id.currency_id.name,
                    "rate": _get_rate_to_fiscal_currency(invoice.currency_id),
                },
                "payments": []
            }

            # Tomamos los metodos de pago de Facturación
            for ml in rml:
                if ml["aml"].journal_id.type in ["bank", "cash"]:
                    invoice_item["payments"].append({
                        "journal_id": ml["aml"].journal_id.id,
                        "payment_method": ml["aml"].journal_id.name,
                        "amount": abs(ml["amount"]),
                        "currency": {
                            "name": ml["currency"].name,
                            "rate": _get_rate_to_fiscal_currency(ml["currency"])
                        }
                    })

            # Tomamos los pagos provenientes del PoS
            if hasattr(invoice, "pos_order_ids"):
                invoice_item["payments"] += [{
                    "journal_id": pos_payment.payment_method_id.journal_id.id,
                    "payment_method": pos_payment.payment_method_id.journal_id.name,
                    "amount": abs(pos_payment.amount),
                    "currency": {
                        "name": pos_payment.currency_id.name,
                        "rate": _get_rate_to_fiscal_currency(pos_payment.currency_id)
                    }
                } for pos_payment in invoice.mapped("pos_order_ids.payment_ids")]

            invoice_list.append(invoice_item)
        return invoice_list

    def get_origin_invoice_fiscal_data(self):
        res = []
        for invoice in self:
            assert invoice.reversed_entry_id.fp_serial_num, "The %s invoice does not have the field 'FP_Serial_num'" % invoice.reversed_entry_id.name
            assert invoice.reversed_entry_id.ticket_ref, "The %s invoice does not have the 'ticket_ref' field" % invoice.reversed_entry_id.name

            res.append({
                "ticket_ref": invoice.reversed_entry_id.ticket_ref,
                "fp_serial_num": invoice.reversed_entry_id.fp_serial_num,
                "invoice_date": invoice.reversed_entry_id.invoice_date,
            })
        return res

    @api.constrains("fiscal_correlative", "control_number")
    def _constrains_fiscal_fields(self):
        if len(self) == 1:
            try:
                if self.fiscal_check:
                    if self.move_type in CUSTOMER_DOCUMENTS:
                        moves = self.env["account.move"].search([
                            ("id", "!=", self.id),
                            ("move_type", "=", self.move_type),
                            ("fiscal_check", "=", self.fiscal_check),
                            "|",
                            ("control_number", "!=", False),
                            ("fiscal_correlative", "!=", False),
                            "|",
                            ("control_number", "=", self.control_number),
                            ("fiscal_correlative", "=", self.fiscal_correlative),
                        ])

                        assert not moves, _(
                            "The fiscal correlative and the control number must be unique, check the following documents: %s" % moves.mapped(
                                "name")
                        )
                else:
                    assert not (self.control_number or self.fiscal_correlative), _(
                        "The 'Control Number' and 'Fiscal Correlative' fields are only for fiscal invoices"
                    )
            except Exception as e:

                raise UserError(str(e))