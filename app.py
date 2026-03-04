"""
app.py — Alternative: Simple Python GUI launcher
Can be used as an alternative to command line

Run with:
    python app.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import os
from pathlib import Path


class DataTaxonomyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎯 DataTaxonomy")
        self.root.geometry("600x400")
        
        # Title
        title = tk.Label(root, text="DataTaxonomy", font=("Arial", 20, "bold"))
        title.pack(pady=20)
        
        subtitle = tk.Label(root, text="File Classification & Asset Taxonomy", font=("Arial", 10))
        subtitle.pack()
        
        # Main buttons
        tk.Button(root, text="🚀 Full Pipeline\n(Process + Dashboard)", 
                 command=self.run_full, width=25, height=3, font=("Arial", 12)).pack(pady=10)
        
        tk.Button(root, text="📊 Process Data Only", 
                 command=self.run_process_only, width=25, height=2, font=("Arial", 12)).pack(pady=5)
        
        tk.Button(root, text="📈 Open Dashboard", 
                 command=self.run_dashboard, width=25, height=2, font=("Arial", 12)).pack(pady=5)
        
        tk.Button(root, text="⚙️  Edit Configuration", 
                 command=self.edit_config, width=25, height=2, font=("Arial", 12)).pack(pady=5)
        
        # Status
        self.status = tk.Label(root, text="Ready", font=("Arial", 10), fg="green")
        self.status.pack(side=tk.BOTTOM, pady=10)
    
    def run_full(self):
        self.status.config(text="⏳ Running full pipeline...", fg="blue")
        self.root.update()
        try:
            subprocess.run(["python", "main.py"], check=True)
            self.status.config(text="✅ Complete!", fg="green")
            messagebox.showinfo("Success", "Pipeline completed successfully!")
        except subprocess.CalledProcessError as e:
            self.status.config(text="❌ Error", fg="red")
            messagebox.showerror("Error", f"Pipeline failed: {e}")
    
    def run_process_only(self):
        self.status.config(text="⏳ Processing...", fg="blue")
        self.root.update()
        try:
            subprocess.run(["python", "main.py", "--no-dashboard"], check=True)
            self.status.config(text="✅ Complete!", fg="green")
            messagebox.showinfo("Success", "Data processing completed!")
        except subprocess.CalledProcessError as e:
            self.status.config(text="❌ Error", fg="red")
            messagebox.showerror("Error", f"Processing failed: {e}")
    
    def run_dashboard(self):
        self.status.config(text="⏳ Launching dashboard...", fg="blue")
        self.root.update()
        try:
            subprocess.Popen(["streamlit", "run", "dashboard.py"])
            self.status.config(text="✅ Dashboard launched", fg="green")
            messagebox.showinfo("Info", "Dashboard opened in your browser")
        except Exception as e:
            self.status.config(text="❌ Error", fg="red")
            messagebox.showerror("Error", f"Failed to launch dashboard: {e}")
    
    def edit_config(self):
        if not Path("config.yaml").exists():
            messagebox.showerror("Error", "config.yaml not found!")
            return
        try:
            if os.name == "nt":  # Windows
                os.startfile("config.yaml")
            elif os.name == "posix":  # macOS/Linux
                subprocess.Popen(["open", "config.yaml"])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open config: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = DataTaxonomyApp(root)
    root.mainloop()
