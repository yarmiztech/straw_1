from odoo import fields,models,api,_
from odoo.tests.common import Form
from datetime import datetime
from odoo.exceptions import UserError, ValidationError


class TypeOfExpenses(models.Model):
    _name = 'type.of.expenses'

    name = fields.Char(string='Type Of Expenses')

class StrawberryExpensesType(models.Model):
    _name = 'strawberry.expenses.type'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'utm.mixin']




    name = fields.Char("Name", index=True, default=lambda self: _('New'))
    journal_id = fields.Many2one('account.journal', string='Journal', ondelete='cascade',
                                 domain=[('type', 'in', ('bank', 'cash'))],
                                 help="This field is ignored in a bank statement reconciliation.")

    branch_id = fields.Many2one('company.branches', 'Branch Name')
    create_date = fields.Date(string='Create Date', default=fields.Date.context_today)

    user_id = fields.Many2one('res.users', 'Created By', required=True, default=lambda self: self.env.user)

    state = fields.Selection([('draft', 'Draft'), ('validate', 'Validate'), ('cancelled', 'Cancelled')], readonly=True,)
    straw_expense_lines = fields.One2many('straw.expenses.lines','straw_expense_id')
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company)
    attachment_ids = fields.Many2one('ir.attachment', string='Files')
    move_ids = fields.One2many('account.move','strawberry_expenses')
    move_count= fields.Integer(compute='compute_move_count')
    attachment_number = fields.Integer('Number of Attachments', compute='_compute_attachment_number')
    total_amount = fields.Integer('Paid Amount', compute='_compute_paid_amount')

    def _compute_paid_amount(self):
        for each in self:
            each.total_amount = sum(each.mapped('straw_expense_lines').mapped('amount'))

    def _compute_attachment_number(self):
        attachment_data = self.env['ir.attachment'].read_group(
            [('res_model', '=', 'strawberry.expenses.type'), ('res_id', 'in', self.ids)], ['res_id'], ['res_id'])
        attachment = dict((data['res_id'], data['res_id_count']) for data in attachment_data)
        for sale in self:
            sale.attachment_number = attachment.get(self.id, 0)

    def action_get_attachment_view(self):
        attachment_obj = self.env['ir.attachment'].search([('res_id', '=', self.ids)])
        attachment_ids = []
        for each in attachment_obj:
            attachment_ids.append(each.id)
        view_id = self.env.ref('base.view_attachment_form').id
        if attachment_ids:
            if len(attachment_ids) <= 1:
                value = {
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'ir.attachment',
                    'view_id': view_id,
                    'type': 'ir.actions.act_window',
                    'name': _('Receipt Ref'),
                    'res_id': attachment_ids and attachment_ids[0]
                }
            else:
                value = {
                    'domain': str([('id', 'in', attachment_ids)]),
                    'view_type': 'form',
                    'view_mode': 'kanban,form',
                    'res_model': 'ir.attachment',
                    'view_id': False,
                    'type': 'ir.actions.act_window',
                    'name': _('Receipt Ref'),
                    'res_id': attachment_ids
                }

            return value

    def attach_document(self, attachment_ids=None, view_type='tree'):
        print('TEST1TT1T1')
        if attachment_ids is None:
            attachment_ids = []
        attachments = self.env['ir.attachment'].browse(attachment_ids)
        if not attachments:
            raise UserError(_("No attachment was provided"))
        sales = self.env['strawberry.expenses.type']

        if any(attachment.res_id or attachment.res_model != 'sale.order' for attachment in attachments):
            raise UserError(_("Invalid attachments!"))

        product = self.env['product.product'].search([('name', '=', 'Expenses')])
        if not product:
            product = product.filtered(lambda p: p.default_code == "EXP_GEN") or product[0]
        else:
            raise UserError(_("You need to have at least one product that can be expensed in your database to proceed!"))

        for attachment in attachments:
            sale = self.env['strawberry.expenses.type'].create({
                'name': attachment.name.split('.')[0],
                'unit_amount': 0,
                'product_id': product.id
            })
            sale.message_post(body=_('Uploaded Attachment'))
            attachment.write({
                'res_model': 'strawberry.expenses.type',
                'res_id': sale.id,
            })

    def action_journal_invoices(self):
        return {
            'name': _('Journal Entries'),
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.move_ids.ids)],
        }

    def compute_move_count(self):
        for l in self:
            l.move_count = len(l.move_ids)


    def action_confirm(self):
        for line in self.straw_expense_lines:
            vals = {
                'journal_id': line.journal_id.id,
                'state': 'draft',
                'move_type': 'entry',
                'branch_id':self.branch_id.id,
                'ref': line.narration
            }
            pay_id_list = []
            move_id = self.env['account.move'].create(vals)
            label = line.narration
            temp = (0, 0, {
                'account_id': self.env['account.account'].sudo().search(
                    [('name', '=', 'Account Payable'),
                     ('company_id', '=', line.company_id.id)]).id,
                'name': label,
                'move_id': move_id.id,
                'date': datetime.today().date(),
                # 'partner_id': driver_id.id,
                'debit': line.amount,
                'branch_id': self.branch_id.id,
                'credit': 0,
            })
            pay_id_list.append(temp)

            # acc = self.env['account.account'].sudo().search(
            #     [('name', '=', 'Outstanding Payments'),
            #      ('company_id', '=', line.company_id.id)])
            acc =line.journal_id.payment_credit_account_id

            temp = (0, 0, {
                'account_id': acc.id,
                'name': label,
                'move_id': move_id.id,
                'date': datetime.today().date(),
                # 'partner_id': driver_id.id,
                'debit': 0,
                'branch_id':self.branch_id.id,
                'credit': line.amount,
            })
            pay_id_list.append(temp)
            move_id.strawberry_expenses = self.id
            move_id.line_ids = pay_id_list
            # move_id.branch_id = self.branch_id.id
            self.write({'state': 'validate'})
            for move in move_id:
                move.action_post()

    @api.onchange('company_id')
    def onchange_company_id(self):
        if self.company_id:
            self.journal_id = self.env['account.journal'].search(
            [('name', '=', 'Cash'), ('company_id', '=', self.company_id.id)]).id

    # @api.returns('mail.message', lambda value: value.id)
    # def message_post(self, **kwargs):
    #     if self.env.context.get('mark_so_as_sent'):
    #         self.filtered(lambda o: o.state == 'draft').with_context(tracking_disable=True).write({'state': 'sent'})
    #     return super(SaleOrder, self.with_context(mail_post_autofollow=True)).message_post(**kwargs)


    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            if 'company_id' in vals:
                vals['name'] = self.env['ir.sequence'].with_context(force_company=vals['company_id']).next_by_code(
                    'strawberry.expenses.type') or _('New')
            else:
                vals['name'] = self.env['ir.sequence'].next_by_code('strawberry.expenses.type') or _('New')

        return super(StrawberryExpensesType, self).create(vals)





class StrawberryExpensesLines(models.Model):
    _name = 'straw.expenses.lines'

    straw_expense_id = fields.Many2one('strawberry.expenses.type', 'Ref Name')
    type_of_expenses = fields.Many2one('type.of.expenses',string="Type Of Expenses")
    amount = fields.Float('Paid Amount')
    narration = fields.Char(string="Narration")
    journal_id = fields.Many2one('account.journal', string='Journal', ondelete='cascade',
                                 domain=[('type', 'in', ('bank', 'cash'))],
                                 help="This field is ignored in a bank statement reconciliation.")
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company)

    @api.onchange('company_id')
    def onchange_company_id(self):
        if self.company_id:
            self.journal_id = self.env['account.journal'].search(
                [('name', '=', 'Cash'), ('company_id', '=', self.company_id.id)]).id






class AccountInvoice(models.Model):
    _inherit = "account.move"

    strawberry_expenses =  fields.Many2one('strawberry.expenses.type')