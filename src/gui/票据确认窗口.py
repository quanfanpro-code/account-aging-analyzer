"""票据类型或债权口径不明时，集中确认关联金额的计龄政策。"""
import customtkinter as ctk
from tkinter import messagebox
from src.gui.widgets import make_button


def collect_bill_decisions(items, choices, reasons):
    decisions=[]
    for item,choice,reason in zip(items,choices,reasons):
        if choice not in ('连续计龄','不连续计龄'):
            raise ValueError(f"请确认{item['单位']}、{item['金额']:,.2f}元的计龄口径")
        if not reason.strip():
            raise ValueError(f"请填写{item['单位']}本项口径的具体依据")
        decisions.append({**item,'连续计龄':choice=='连续计龄','依据':reason.strip()})
    if len(decisions)!=len(items):raise ValueError('票据决定数量与待确认事项不一致')
    return decisions


class BillConfirmationDialog(ctk.CTkToplevel):
    def __init__(self,master,items,callback):
        super().__init__(master)
        self.title('应收票据计龄口径确认');self.geometry('880x620')
        self.items=items;self.callback=callback;self.completed=False;self.rows=[]
        ctk.CTkLabel(self,text='下列票据尚缺类型或原债权处理依据，请确认后计算',
            font=ctk.CTkFont(size=17,weight='bold')).pack(anchor='w',padx=18,pady=14)
        area=ctk.CTkScrollableFrame(self);area.pack(fill='both',expand=True,padx=16)
        for item in items:
            card=ctk.CTkFrame(area);card.pack(fill='x',pady=5)
            ctk.CTkLabel(card,text=f"{item['单位']}　{item['金额']:,.2f}元　{item.get('日期','')}　{item.get('凭证号','')}",
                wraplength=780,justify='left',font=ctk.CTkFont(size=13,weight='bold')).pack(anchor='w',padx=12,pady=(10,4))
            ctk.CTkLabel(card,text='连续计龄保留原债权日期；不连续计龄从收票日重新计算。请选择有资料支持的口径。',
                wraplength=780,justify='left').pack(anchor='w',padx=12,pady=4)
            choice=ctk.StringVar(value='未确认')
            ctk.CTkOptionMenu(card,variable=choice,values=['未确认','连续计龄','不连续计龄']).pack(anchor='w',padx=12,pady=5)
            reason=ctk.CTkEntry(card,placeholder_text='填写票据类型、原债权处理口径及依据')
            reason.pack(fill='x',padx=12,pady=(3,12));self.rows.append((choice,reason))
        buttons=ctk.CTkFrame(self,fg_color='transparent');buttons.pack(fill='x',padx=18,pady=14)
        make_button(buttons,'取消本次计算',level='weak',command=self.cancel).pack(side='left')
        make_button(buttons,'确认并继续',level='primary',command=self.confirm).pack(side='right')
        self.protocol('WM_DELETE_WINDOW',self.cancel);self.after(100,self.grab_set)

    def confirm(self):
        try:
            result=collect_bill_decisions(self.items,[choice.get() for choice,_ in self.rows],
                [reason.get() for _,reason in self.rows])
        except ValueError as error:
            messagebox.showwarning('尚未完成确认',str(error),parent=self);return
        self.completed=True;self.callback(result);self.destroy()

    def cancel(self):
        if not self.completed:self.completed=True;self.callback(None)
        self.destroy()
