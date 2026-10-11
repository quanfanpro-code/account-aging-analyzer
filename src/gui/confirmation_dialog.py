"""计算前集中确认暂估科目归属与名称合并。"""
import customtkinter as ctk
from tkinter import messagebox
from src.gui.widgets import make_button
from src.core.current_accounts import CATEGORIES
from src.core.preflight import confirmed_aliases

class ConfirmationDialog(ctk.CTkToplevel):
    def __init__(self,master,pending,callback,cached=None):
        super().__init__(master)
        self.title('计算前确认');self.geometry('1000x720');self.minsize(850,600)
        self.pending=pending;self.callback=callback;self.completed=False
        cached=cached or {};self.temporary_vars={};self.name_vars={}
        ctk.CTkLabel(self,text='确认科目归属和往来单位名称后开始计算',font=ctk.CTkFont(size=19,weight='bold')).pack(anchor='w',padx=20,pady=(18,8))
        tabs=ctk.CTkTabview(self);tabs.pack(fill='both',expand=True,padx=16,pady=8)
        temporary=tabs.add('暂估科目归属');names=tabs.add('往来单位名称')
        ts=ctk.CTkScrollableFrame(temporary);ts.pack(fill='both',expand=True)
        if not pending.temporary:ctk.CTkLabel(ts,text='未检测到需要确认的暂估往来科目').pack(anchor='w')
        for item in pending.temporary:
            card=ctk.CTkFrame(ts);card.pack(fill='x',pady=5)
            ctk.CTkLabel(card,text=f'{item.code}  {item.name}    建议归入：{item.suggested}',font=ctk.CTkFont(size=13,weight='bold')).pack(anchor='w',padx=12,pady=(8,2))
            ctk.CTkLabel(card,text=item.evidence,wraplength=880,justify='left',font=ctk.CTkFont(size=11)).pack(anchor='w',padx=12)
            old=cached.get('temporary',{}).get(item.code,'未确认')
            var=ctk.StringVar(value='本次不纳入' if old is None else old)
            ctk.CTkOptionMenu(card,variable=var,values=['未确认',*CATEGORIES,'本次不纳入'],width=200).pack(anchor='w',padx=12,pady=8)
            self.temporary_vars[item.code]=var
        top=ctk.CTkFrame(names,fg_color='transparent');top.pack(fill='x')
        ctk.CTkLabel(top,text='名称相似只作为候选，是否同一单位由您确认').pack(side='left')
        make_button(top,'剩余项全部分别计算',level='secondary',command=self.keep_remaining).pack(side='right')
        ns=ctk.CTkScrollableFrame(names);ns.pack(fill='both',expand=True,pady=8)
        if not pending.names:ctk.CTkLabel(ns,text='未检测到疑似重复的往来单位名称').pack(anchor='w')
        for number,item in enumerate(pending.names,1):
            card=ctk.CTkFrame(ns);card.pack(fill='x',pady=5)
            ctk.CTkLabel(card,text=f'{number}. {item.key[0]}\n    {item.key[1]}',wraplength=870,justify='left',font=ctk.CTkFont(size=13,weight='bold')).pack(anchor='w',padx=12,pady=(8,2))
            ctk.CTkLabel(card,text=item.reason+'\n'+item.evidence,wraplength=870,justify='left',font=ctk.CTkFont(size=11)).pack(anchor='w',padx=12)
            controls=ctk.CTkFrame(card,fg_color='transparent');controls.pack(fill='x',padx=12,pady=8)
            old=cached.get('names',{}).get(item.key,'未确认')
            choice=ctk.StringVar(value='分别计算' if old is None else '未确认' if old=='未确认' else '合并计算')
            canonical=ctk.StringVar(value=item.key[0] if old in (None,'未确认') else old)
            ctk.CTkOptionMenu(controls,variable=choice,values=['未确认','合并计算','分别计算'],width=150).pack(side='left')
            ctk.CTkLabel(controls,text='统一名称：').pack(side='left',padx=(12,2))
            ctk.CTkComboBox(controls,variable=canonical,values=list(item.key),width=500).pack(side='left',fill='x',expand=True)
            self.name_vars[item.key]=(choice,canonical)
        bottom=ctk.CTkFrame(self,fg_color='transparent');bottom.pack(fill='x',padx=20,pady=(4,16))
        make_button(bottom,'取消',level='weak',command=self.cancel).pack(side='left')
        make_button(bottom,'确认并开始计算',level='primary',command=self.confirm).pack(side='right')
        self.protocol('WM_DELETE_WINDOW',self.cancel)
        self.after(100,self.grab_set)

    def keep_remaining(self):
        for choice,_ in self.name_vars.values():
            if choice.get()=='未确认':choice.set('分别计算')

    def collect(self):
        temporary={};names={}
        for code,var in self.temporary_vars.items():
            value=var.get()
            if value=='未确认':raise ValueError(f'请确认暂估科目 {code} 的归属')
            temporary[code]=None if value=='本次不纳入' else value
        for key,(choice,canonical) in self.name_vars.items():
            if choice.get()=='未确认':raise ValueError('请确认每组名称，或选择剩余项全部分别计算')
            names[key]=canonical.get().strip() if choice.get()=='合并计算' else None
        confirmed_aliases(self.pending.names,names)
        return {'temporary':temporary,'names':names}

    def confirm(self):
        try:decisions=self.collect()
        except ValueError as error:messagebox.showwarning('尚未完成确认',str(error),parent=self);return
        self.completed=True;self.callback(decisions);self.destroy()

    def cancel(self):
        if not self.completed:self.completed=True;self.callback(None)
        self.destroy()
