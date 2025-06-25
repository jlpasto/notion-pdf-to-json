import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys
import platform

from main_app_logic import run_main_process

class NotionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Notion PDF to JSON Uploader")
        self.geometry("550x300")
        self.configure(padx=20, pady=20)

        self.create_widgets()

    def create_widgets(self):
        self.entries = {}

        labels = {
            "client_id": "Google Client ID:",
            "client_secret": "Google Client Secret:",
            #"notion_token": "Notion Token:",
            "database_id": "Notion Database ID:",
            "target_column": "Column Name of PDF in Notion:"
        }

        for i, (key, text) in enumerate(labels.items()):
            ttk.Label(self, text=text).grid(row=i, column=0, sticky="w", pady=5)
            entry = ttk.Entry(self, width=50)
            entry.grid(row=i, column=1, pady=5)
            self.entries[key] = entry

        self.run_button = ttk.Button(self, text="Run", command=self.run_main)
        self.run_button.grid(row=len(labels), column=0, columnspan=2, pady=20)

    def run_main(self):
        values = {k: v.get() for k, v in self.entries.items()}

        # Validate required fields
        missing = [key for key, val in values.items() if not val]
        if missing:
            messagebox.showerror("Error", f"Please fill in all required fields: {', '.join(missing)}")
            return

        # Close the GUI immediately, then run the main logic
        self.destroy()

        try:
            run_main_process(
                values["client_id"],
                values["client_secret"],
                values["database_id"],
                values["target_column"],
                #values["notion_token"],
            )
            #messagebox.showinfo("Success", "Process completed successfully!")
        except Exception as e:
            messagebox.showerror("Error", str(e))


def is_display_available():
    if platform.system() == "Windows":
        return True  # Windows has GUI
    return os.environ.get("DISPLAY") is not None


if __name__ == "__main__":
    if is_display_available():
        app = NotionApp()
        app.mainloop()
    else:
        print("Error: No GUI display found. This application requires a graphical environment.")
        print("Tip: If you're on a headless system, use a local machine or setup a virtual display (Xvfb).")
        sys.exit(1)
