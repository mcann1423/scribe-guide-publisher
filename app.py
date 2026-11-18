"""Tk interface for the local guide publisher (Python 3.10+)."""
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from publisher import Publisher, DEFAULT_EXPORTS, DEFAULT_OUTPUT, guide_id

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Help Guide Publisher'); self.geometry('1000x650'); self.minsize(750,500)
        self.exports=tk.StringVar(value=str(DEFAULT_EXPORTS)); self.output=tk.StringVar(value=str(DEFAULT_OUTPUT)); self.status=tk.StringVar(value='Select an export to publish or update, or a published guide to unpublish.')
        top=ttk.Frame(self,padding=12); top.pack(fill='x')
        for label,var in [('Exports',self.exports),('Prepared website',self.output)]:
            row=ttk.Frame(top); row.pack(fill='x',pady=3); ttk.Label(row,text=label,width=18).pack(side='left'); ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True); ttk.Button(row,text='Browse…',command=lambda v=var:self.browse(v)).pack(side='left',padx=4)
        ttk.Button(top,text='Load / refresh',command=self.refresh).pack(anchor='w',pady=6)
        panels=ttk.Panedwindow(self,orient='horizontal'); panels.pack(fill='both',expand=True,padx=12)
        left=ttk.Labelframe(panels,text='HTML exports',padding=8); right=ttk.Labelframe(panels,text='Published locally',padding=8); panels.add(left,weight=1); panels.add(right,weight=1)
        self.available=tk.Listbox(left,exportselection=False); self.available.pack(fill='both',expand=True)
        ttk.Button(left,text='Publish / update selected',command=self.publish).pack(pady=8)
        self.published=tk.Listbox(right,exportselection=False); self.published.pack(fill='both',expand=True)
        ttk.Button(right,text='Unpublish selected',command=self.unpublish).pack(pady=8)
        buttons=ttk.Frame(self,padding=12); buttons.pack(fill='x'); ttk.Button(buttons,text='Server removal list',command=self.removals).pack(side='left'); ttk.Button(buttons,text='Open prepared folder',command=self.open_output).pack(side='left',padx=8); ttk.Label(buttons,textvariable=self.status,wraplength=760).pack(side='left',fill='x',expand=True)
        self.engine=None; self.available_files=[]; self.published_ids=[]; self.refresh()
    def browse(self,var):
        p=filedialog.askdirectory();
        if p: var.set(p)
    def refresh(self):
        try:
            self.engine=Publisher(self.exports.get(),self.output.get()); self.available_files=self.engine.exports_list(); self.available.delete(0,'end')
            for p in self.available_files:
                try: ident=guide_id(p.name); mark=' [published]' if ident in self.engine.state['guides'] and self.engine.state['guides'][ident]['source'].casefold()==p.name.casefold() else ''
                except ValueError: mark=' [invalid filename]'
                self.available.insert('end',p.name+mark)
            self.published_ids=sorted(self.engine.state['guides'],key=lambda i:self.engine.state['guides'][i]['title'].casefold()); self.published.delete(0,'end')
            for i in self.published_ids: self.published.insert('end',self.engine.state['guides'][i]['title']+' ('+i+'.html)')
            self.status.set(f'{len(self.available_files)} exports, {len(self.published_ids)} published locally.')
        except Exception as e: self.engine=None; messagebox.showerror('Cannot load publisher',str(e))
    def publish(self):
        if not self.engine or not self.available.curselection(): return
        p=self.available_files[self.available.curselection()[0]]
        if not messagebox.askyesno('Confirm public guide',f'Publish or update {p.name}?\n\nThe output is public when you deploy it. Have you reviewed its text and screenshots for sensitive information?'): return
        try:
            self.status.set('Downloading images and preparing guide…'); self.update_idletasks()
            warnings=self.engine.publish(p); self.refresh(); messagebox.showinfo('Published locally','Guide prepared. Deploy it through your usual staging process.'+ ('\n\nReview:\n'+'\n'.join(dict.fromkeys(warnings)) if warnings else ''))
        except Exception as e: messagebox.showerror('Could not publish',str(e)); self.refresh()
    def unpublish(self):
        if not self.engine or not self.published.curselection(): return
        ident=self.published_ids[self.published.curselection()[0]]
        if not messagebox.askyesno('Unpublish locally',f'Remove {ident}.html and its images from the prepared folder?\n\nThis will NOT remove the already-deployed copy from the server.'): return
        try: self.engine.unpublish(ident); self.refresh(); messagebox.showinfo('Unpublished locally','Check the server removal list. The live guide may remain accessible until you remove it from the server.')
        except Exception as e: messagebox.showerror('Could not unpublish',str(e)); self.refresh()
    def removals(self):
        if not self.engine:return
        w=tk.Toplevel(self); w.title('Potential server removals'); w.geometry('700x480'); ttk.Label(w,text='These paths may still exist on the server. Remove them manually or deploy a clean copy.').pack(padx=12,pady=12)
        text=tk.Text(w,wrap='word'); text.pack(fill='both',expand=True,padx=12); text.insert('1.0','\n'.join(self.engine.state['removals']) or 'No removal notices.'); text.configure(state='disabled')
        def clear():
            if messagebox.askyesno('Clear notices','Have you verified these paths are removed from the live web directory? This clears all notices.'): self.engine.state['removals']=[]; self.engine._save(); w.destroy()
        ttk.Button(w,text='Clear after verifying server',command=clear).pack(pady=12)
    def open_output(self):
        try:
            self.engine.output.mkdir(parents=True,exist_ok=True); os.startfile(self.engine.output)
        except Exception as e: messagebox.showerror('Cannot open folder',str(e))

if __name__=='__main__': App().mainloop()
