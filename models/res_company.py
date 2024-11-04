from odoo import fields, api, models

PRINT_METHODS = [
    ("free_form", "Free Form"),
    ("fiscal_machine", "Fiscal Machine"),
    ("both", "Both")
]

class ResCompany(models.Model):
    _inherit = 'res.company'

    ruc = fields.Char('RUC')
    taxpayer_license = fields.Char('LAE')
    municipality = fields.Char('Municipality')
    show_fiscal_fields = fields.Boolean('Show Fiscal Fields', default=True)
    invoice_print_method = fields.Selection(PRINT_METHODS, "Print Method", required=True, default="free_form")
    fiscal_currency_id = fields.Many2one("res.currency", "Fiscal Currency")