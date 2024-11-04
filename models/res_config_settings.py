from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    show_fiscal_fields = fields.Boolean(related="company_id.show_fiscal_fields", readonly=False)
    fiscal_currency_id = fields.Many2one(related='company_id.fiscal_currency_id', readonly=False)
    invoice_print_method = fields.Selection(related='company_id.invoice_print_method', readonly=False, required=True)