"""Tk interface for the local guide publisher (Python 3.10+)."""
import os
from pathlib import Path
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from publisher import Publisher, DEFAULT_EXPORTS, DEFAULT_OUTPUT, guide_id
from updater import check_for_update, download_installer
from version import __version__

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('Help Guide Publisher '+__version__); self.geometry('1000x650'); self.minsize(750,500)
        self.exports=tk.StringVar(value=str(DEFAULT_EXPORTS)); self.output=tk.StringVar(value=str(DEFAULT_OUTPUT)); self.status=tk.StringVar(value='Select an export to publish or update, or a published guide to unpublish.')
        top=ttk.Frame(self,padding=12); top.pack(fill='x')
        for label,var in [('Exports',self.exports),('Prepared website',self.output)]:
            row=ttk.Frame(top); row.pack(fill='x',pady=3); ttk.Label(row,text=label,width=18).pack(side='left'); ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True); ttk.Button(row,text='Browse…',command=lambda v=var:self.browse(v)).pack(side='left',padx=4)
        controls=ttk.Frame(top); controls.pack(anchor='w',pady=6)
        ttk.Button(controls,text='Load / refresh',command=self.refresh).pack(side='left')
        ttk.Button(controls,text='Paste HTML and publish…',command=self.paste_html).pack(side='left',padx=8)
        panels=ttk.Panedwindow(self,orient='horizontal'); panels.pack(fill='both',expand=True,padx=12)
        left=ttk.Labelframe(panels,text='HTML exports',padding=8); right=ttk.Labelframe(panels,text='Published locally',padding=8); panels.add(left,weight=1); panels.add(right,weight=1)
        self.available=tk.Listbox(left,exportselection=False); self.available.pack(fill='both',expand=True)
        ttk.Button(left,text='Publish / update selected',command=self.publish).pack(pady=8)
        self.published=tk.Listbox(right,exportselection=False); self.published.pack(fill='both',expand=True)
        ttk.Button(right,text='Unpublish selected',command=self.unpublish).pack(pady=8)
        buttons=ttk.Frame(self,padding=12); buttons.pack(fill='x'); ttk.Button(buttons,text='Server removal list',command=self.removals).pack(side='left'); ttk.Button(buttons,text='Open prepared folder',command=self.open_output).pack(side='left',padx=8); self.update_button=ttk.Button(buttons,text='Check for updates',command=self.check_updates); self.update_button.pack(side='left'); ttk.Label(buttons,textvariable=self.status,wraplength=620).pack(side='left',fill='x',expand=True)
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
    def paste_html(self):
        if not self.engine:
            return
        dialog=tk.Toplevel(self); dialog.title('Paste HTML and publish'); dialog.geometry('860x640'); dialog.minsize(600,440); dialog.transient(self); dialog.grab_set()
        frame=ttk.Frame(dialog,padding=12); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Export filename (this becomes the stable public guide URL):').pack(anchor='w')
        filename=tk.StringVar(value='new-guide.html')
        entry=ttk.Entry(frame,textvariable=filename); entry.pack(fill='x',pady=(2,10)); entry.focus_set(); entry.select_range(0,'end')
        ttk.Label(frame,text='Paste exported HTML:').pack(anchor='w')
        text=tk.Text(frame,wrap='none',undo=True); text.pack(fill='both',expand=True,pady=(2,10))
        def publish_pasted():
            name=filename.get().strip()
            try:
                existing=self.engine.exports / name
                if existing.exists() and not messagebox.askyesno('Replace export?',f'{name} already exists. Replace its original export and publish the updated guide?',parent=dialog):
                    return
                if not messagebox.askyesno('Confirm public guide',f'Create {name}, then publish it locally?\n\nThe output is public when deployed. Have you reviewed its text and screenshots for sensitive information?',parent=dialog):
                    return
                self.status.set('Saving pasted export, downloading images, and preparing guide…'); self.update_idletasks()
                source=self.engine.save_pasted_export(name,text.get('1.0','end-1c'))
                warnings=self.engine.publish(source); dialog.destroy(); self.refresh()
                messagebox.showinfo('Published locally','Original export saved and guide prepared. Deploy it through your usual staging process.'+ ('\n\nReview:\n'+'\n'.join(dict.fromkeys(warnings)) if warnings else ''))
            except Exception as e:
                messagebox.showerror('Could not publish pasted HTML',str(e),parent=dialog); self.refresh()
        buttons=ttk.Frame(frame); buttons.pack(fill='x')
        ttk.Button(buttons,text='Publish pasted HTML',command=publish_pasted).pack(side='right')
        ttk.Button(buttons,text='Cancel',command=dialog.destroy).pack(side='right',padx=8)
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
    def check_updates(self):
        self.update_button.configure(state='disabled'); self.status.set('Checking GitHub Releases for updates…')
        def worker():
            try: result=check_for_update(); self.after(0,lambda:self._update_checked(result,None))
            except Exception as e: self.after(0,lambda:self._update_checked(None,e))
        threading.Thread(target=worker,daemon=True).start()
    def _update_checked(self,release,error):
        self.update_button.configure(state='normal')
        if error:
            self.status.set('Could not check for updates.'); messagebox.showerror('Update check failed',str(error)); return
        if not release:
            self.status.set('You are running the latest version ('+__version__+').'); messagebox.showinfo('No update available','You are running the latest version ('+__version__+').'); return
        if messagebox.askyesno('Update available','Version '+release.version+' is available. Download it and start the installer now?\n\nThe app will close so Windows can install the update.'):
            self.update_button.configure(state='disabled'); self.status.set('Downloading update from GitHub Releases…')
            def worker():
                try: installer=download_installer(release); self.after(0,lambda:self._update_downloaded(installer,None))
                except Exception as e: self.after(0,lambda:self._update_downloaded(None,e))
            threading.Thread(target=worker,daemon=True).start()
        else: self.status.set('Update available: '+release.version+'.')
    def _update_downloaded(self,installer,error):
        self.update_button.configure(state='normal')
        if error:
            self.status.set('Update download failed.'); messagebox.showerror('Update download failed',str(error)); return
        try:
            subprocess.Popen([str(installer)],close_fds=True); self.status.set('Starting installer…'); self.after(700,self.destroy)
        except Exception as e:
            self.status.set('Could not start installer.'); messagebox.showerror('Could not start installer',str(e))

if __name__=='__main__': App().mainloop()
