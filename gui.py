import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from config import BASE_FOLDER, DATA_FOLDER

from database import (
    get_all_categories,
    get_category,
    save_category,
    remove_category,
    add_extension,
    remove_extension,
    add_keyword,
    remove_keyword,
    add_category_exclusion,
    remove_category_exclusion,
    get_subcategory,
    get_child_subcategories,
    get_subcategory_path,
    save_subcategory,
    remove_subcategory,
    get_game_exclusions,
    add_game_exclusion,
    remove_game_exclusion,
    clear_database,
)

from organizer import organize_files

from logger import (
    logger,
    add_gui_log_handler,
    load_existing_log,
    clear_log_file,
    remove_gui_log_handler,
)


# ============================================================
# LAST LOCATION
# ============================================================

LAST_LOCATION_FILE = DATA_FOLDER / "last_location.json"


def load_last_location():
    if not LAST_LOCATION_FILE.exists():
        return ""

    try:
        data = json.loads(LAST_LOCATION_FILE.read_text(encoding="utf-8"))
        location = data.get("location", "")

        if not isinstance(location, str) or not location:
            return ""

        if not os.path.isdir(location):
            return ""

        return location

    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return ""


def save_last_location(location):
    if not location:
        return

    try:
        DATA_FOLDER.mkdir(parents=True, exist_ok=True)
        LAST_LOCATION_FILE.write_text(
            json.dumps({"location": str(Path(location).resolve())}, indent=4),
            encoding="utf-8",
        )
    except OSError as error:
        logger.warning("Could not save last location: %s", error)


def clear_last_location():
    try:
        if LAST_LOCATION_FILE.exists():
            LAST_LOCATION_FILE.unlink()
    except OSError as error:
        logger.warning("Could not clear last location: %s", error)


# ============================================================
# MAIN APPLICATION
# ============================================================

class DownloadsOrganizerApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Downloads Organizer")
        self.root.geometry("1400x900")
        self.root.minsize(1150, 750)

        self.current_folder = None
        self.organizing = False

        self.selected_item_type = None
        self.selected_category_name = None
        self.selected_subcategory_id = None
        self.tree_metadata = {}

        self.folder_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.rule_title_var = tk.StringVar(value="Select an item")
        self.rule_path_var = tk.StringVar(
            value="Select a category, subcategory or Games."
        )
        self.category_name_var = tk.StringVar()
        self.subcategory_name_var = tk.StringVar()

        self.create_style()
        self.create_ui()
        self.restore_last_location()

        add_gui_log_handler(self.update_activity)
        self.load_activity()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # =========================================================
    # STYLE
    # =========================================================

    def create_style(self):
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg = "#f4f6fb"
        surface = "#ffffff"
        accent = "#3762e0"
        accent_dark = "#2748b0"
        text = "#1f2430"
        subtle = "#6b7280"
        border = "#d8dbe3"
        selected_fg = "#ffffff"

        self.colors = {
            "bg": bg,
            "surface": surface,
            "accent": accent,
            "accent_dark": accent_dark,
            "text": text,
            "subtle": subtle,
            "border": border,
        }

        base_font = ("Segoe UI", 10)

        self.root.configure(background=bg)

        style.configure(".", background=bg, foreground=text, font=base_font)
        style.configure("TFrame", background=bg)
        style.configure("TPanedwindow", background=bg)

        style.configure(
            "TLabelframe",
            background=bg,
            bordercolor=border,
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label",
            background=bg,
            foreground=text,
            font=("Segoe UI", 10, "bold"),
        )

        style.configure("TLabel", background=bg, foreground=text)
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), background=bg)
        style.configure("Heading.TLabel", font=("Segoe UI", 13, "bold"), background=bg)
        style.configure("Subtle.TLabel", foreground=subtle, background=bg)

        style.configure("TNotebook", background=bg, borderwidth=0, tabmargins=(8, 8, 8, 0))
        style.configure(
            "TNotebook.Tab",
            padding=(16, 9),
            font=("Segoe UI", 10, "bold"),
            background=bg,
            foreground=subtle,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", surface)],
            foreground=[("selected", accent)],
        )

        style.configure(
            "Treeview",
            rowheight=30,
            font=base_font,
            background=surface,
            fieldbackground=surface,
            foreground=text,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background=bg,
            foreground=text,
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", accent)],
            foreground=[("selected", selected_fg)],
        )

        style.configure("TButton", padding=(10, 6), background=surface, foreground=text)
        style.map(
            "TButton",
            background=[("active", "#e9edf7"), ("pressed", "#dce3f5")],
        )

        style.configure(
            "Action.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(14, 8),
            background=accent,
            foreground=selected_fg,
        )
        style.map(
            "Action.TButton",
            background=[("active", accent_dark), ("pressed", accent_dark)],
        )

        style.configure("TEntry", padding=6, fieldbackground=surface, foreground=text)
        style.configure(
            "TScrollbar",
            background=bg,
            troughcolor=bg,
            bordercolor=bg,
            arrowcolor=subtle,
        )

    def style_listbox(self, listbox):
        listbox.configure(
            background=self.colors["surface"],
            foreground=self.colors["text"],
            selectbackground=self.colors["accent"],
            selectforeground="#ffffff",
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["accent"],
        )

    def style_text(self, widget):
        widget.configure(
            background=self.colors["surface"],
            foreground=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["accent"],
            padx=8,
            pady=8,
        )

    # =========================================================
    # MOUSEWHEEL HELPER
    # =========================================================

    def bind_mousewheel(self, canvas):
        def on_wheel(event):
            if getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def bind_scroll(_event):
            canvas.bind_all("<MouseWheel>", on_wheel)
            canvas.bind_all("<Button-4>", on_wheel)
            canvas.bind_all("<Button-5>", on_wheel)

        def unbind_scroll(_event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", bind_scroll)
        canvas.bind("<Leave>", unbind_scroll)

    # =========================================================
    # MAIN UI
    # =========================================================

    def create_ui(self):
        self.create_header()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.organize_page = ttk.Frame(self.notebook)
        self.games_page = ttk.Frame(self.notebook)
        self.history_page = ttk.Frame(self.notebook)
        self.settings_page = ttk.Frame(self.notebook)
        self.categories_page = ttk.Frame(self.notebook)

        self.notebook.add(self.organize_page, text="Organize")
        self.notebook.add(self.games_page, text="Games")
        self.notebook.add(self.history_page, text="History")
        self.notebook.add(self.settings_page, text="Settings")
        self.notebook.add(self.categories_page, text="Categories")

        self.build_organize_page()
        self.build_games_page()
        self.build_history_page()
        self.build_settings_page()
        self.build_categories_page()

    def create_header(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=15, pady=12)

        ttk.Label(frame, text="Downloads Organizer", style="Title.TLabel").pack(side="left")
        ttk.Label(frame, textvariable=self.status_var, style="Subtle.TLabel").pack(side="right")

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=0)

    # =========================================================
    # LAST LOCATION
    # =========================================================

    def restore_last_location(self):
        location = load_last_location()

        if not location:
            return

        self.current_folder = location
        self.folder_var.set(location)
        self.status_var.set("Last location restored")

    def remember_current_location(self):
        location = self.folder_var.get().strip()

        if not location or not os.path.isdir(location):
            return

        self.current_folder = location
        save_last_location(location)

    def clear_saved_location(self):
        clear_last_location()
        self.current_folder = None
        self.folder_var.set("")
        self.status_var.set("Saved location cleared")

    # =========================================================
    # ORGANIZE PAGE
    # =========================================================

    def build_organize_page(self):
        page = ttk.Frame(self.organize_page)
        page.pack(fill="both", expand=True, padx=15, pady=15)

        ttk.Label(page, text="Organize Downloads", style="Heading.TLabel").pack(
            anchor="w", pady=(0, 10)
        )

        folder_frame = ttk.LabelFrame(page, text="Folder")
        folder_frame.pack(fill="x", pady=(0, 10))
        folder_frame.columnconfigure(0, weight=1)

        ttk.Entry(folder_frame, textvariable=self.folder_var).grid(
            row=0, column=0, sticky="ew", padx=10, pady=10
        )
        ttk.Button(folder_frame, text="Browse", command=self.select_folder).grid(
            row=0, column=1, padx=(0, 6), pady=10
        )
        ttk.Button(folder_frame, text="Clear Saved", command=self.clear_saved_location).grid(
            row=0, column=2, padx=(0, 10), pady=10
        )

        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=(0, 10))

        ttk.Button(
            actions, text="Organize", style="Action.TButton", command=self.start_organizing
        ).pack(side="left")
        ttk.Button(actions, text="Refresh Activity", command=self.load_activity).pack(
            side="left", padx=8
        )

        activity_frame = ttk.LabelFrame(page, text="Activity")
        activity_frame.pack(fill="both", expand=True)
        activity_frame.columnconfigure(0, weight=1)
        activity_frame.rowconfigure(0, weight=1)

        self.activity_text = tk.Text(
            activity_frame, wrap="word", font=("Consolas", 9), state="disabled"
        )
        self.style_text(self.activity_text)
        self.activity_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)

        scroll = ttk.Scrollbar(
            activity_frame, orient="vertical", command=self.activity_text.yview
        )
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.activity_text.configure(yscrollcommand=scroll.set)

    def select_folder(self):
        initial_dir = self.folder_var.get().strip() or str(Path.home())

        if not os.path.isdir(initial_dir):
            initial_dir = str(Path.home())

        folder = filedialog.askdirectory(
            title="Select folder to organize", initialdir=initial_dir
        )

        if not folder:
            return

        self.current_folder = folder
        self.folder_var.set(folder)
        save_last_location(folder)
        self.status_var.set("Folder selected")

    def start_organizing(self):
        if self.organizing:
            messagebox.showinfo("Organizer", "Organization is already running.")
            return

        folder = self.folder_var.get().strip()

        if not folder:
            messagebox.showwarning("Organizer", "Please select a folder first.")
            return

        if not os.path.isdir(folder):
            messagebox.showerror("Organizer", "The selected folder does not exist.")
            return

        self.remember_current_location()
        self.organizing = True
        self.status_var.set("Organizing...")

        threading.Thread(target=self.run_organizer, args=(folder,), daemon=True).start()

    def run_organizer(self, folder):
        try:
            organize_files(folder)
            self.root.after(0, lambda: self.status_var.set("Organization complete"))

        except Exception as error:
            logger.exception("Organization failed")
            self.root.after(
                0, lambda error=error: messagebox.showerror("Organizer Error", str(error))
            )
            self.root.after(0, lambda: self.status_var.set("Organization failed"))

        finally:
            self.organizing = False

    # =========================================================
    # GAMES
    # =========================================================

    def build_games_page(self):
        page = ttk.Frame(self.games_page)
        page.pack(fill="both", expand=True, padx=15, pady=15)

        ttk.Label(page, text="Games", style="Heading.TLabel").pack(anchor="w", pady=(0, 5))
        ttk.Label(
            page,
            text="Game exclusions are checked before IGDB detection.",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(0, 15))

        frame = ttk.LabelFrame(page, text="Game Exclusions")
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(frame)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.game_exclusion_list = tk.Listbox(list_frame, exportselection=False)
        self.style_listbox(self.game_exclusion_list)
        self.game_exclusion_list.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.game_exclusion_list.yview
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.game_exclusion_list.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        ttk.Button(buttons, text="Add Exclusion", command=self.add_game_exclusion_dialog).pack(
            side="left"
        )
        ttk.Button(
            buttons, text="Remove Selected", command=self.remove_selected_game_exclusion
        ).pack(side="left", padx=8)

        self.refresh_game_exclusions()

    def refresh_game_exclusions(self):
        self.game_exclusion_list.delete(0, tk.END)

        for exclusion in get_game_exclusions():
            self.game_exclusion_list.insert(tk.END, exclusion)

    def add_game_exclusion_dialog(self):
        value = self.prompt_text("Add Game Exclusion", "Enter a word or phrase:")

        if not value:
            return

        add_game_exclusion(value)
        self.refresh_game_exclusions()

        if self.selected_item_type == "games":
            self.show_games_rules()

    def remove_selected_game_exclusion(self):
        selection = self.game_exclusion_list.curselection()

        if not selection:
            return

        value = self.game_exclusion_list.get(selection[0])

        if not messagebox.askyesno("Remove Exclusion", f"Remove '{value}'?"):
            return

        remove_game_exclusion(value)
        self.refresh_game_exclusions()

        if self.selected_item_type == "games":
            self.show_games_rules()

    # =========================================================
    # HISTORY
    # =========================================================

    def build_history_page(self):
        page = ttk.Frame(self.history_page)
        page.pack(fill="both", expand=True, padx=15, pady=15)

        ttk.Label(page, text="History / Activity Log", style="Heading.TLabel").pack(
            anchor="w", pady=(0, 10)
        )

        buttons = ttk.Frame(page)
        buttons.pack(fill="x", pady=(0, 10))

        ttk.Button(buttons, text="Refresh", command=self.load_activity).pack(side="left")
        ttk.Button(buttons, text="Clear Display", command=self.clear_activity_preview).pack(
            side="left", padx=8
        )
        ttk.Button(
            buttons, text="Clear Log", style="Action.TButton", command=self.clear_activity_log
        ).pack(side="left")

        frame = ttk.Frame(page)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.history_text = tk.Text(
            frame, wrap="none", font=("Consolas", 9), state="disabled"
        )
        self.style_text(self.history_text)
        self.history_text.grid(row=0, column=0, sticky="nsew")

        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.history_text.yview)
        vertical.grid(row=0, column=1, sticky="ns")

        horizontal = ttk.Scrollbar(
            frame, orient="horizontal", command=self.history_text.xview
        )
        horizontal.grid(row=1, column=0, sticky="ew")

        self.history_text.configure(
            yscrollcommand=vertical.set, xscrollcommand=horizontal.set
        )

    def load_activity(self):
        try:
            text = load_existing_log()
        except Exception as error:
            text = f"[LOGGER] Could not load log: {error}\n"

        if hasattr(self, "activity_text"):
            self.set_text_widget(self.activity_text, text)

        if hasattr(self, "history_text"):
            self.set_text_widget(self.history_text, text)

    def update_activity(self, message):
        def update():
            if hasattr(self, "activity_text"):
                self.append_text_widget(self.activity_text, message)

            if hasattr(self, "history_text"):
                self.append_text_widget(self.history_text, message)

        try:
            self.root.after(0, update)
        except tk.TclError:
            pass

    def clear_activity_preview(self):
        self.set_text_widget(self.activity_text, "")
        self.set_text_widget(self.history_text, "")

    def clear_activity_log(self):
        if not messagebox.askyesno(
            "Clear Log",
            "Clear the organizer log?\n\nThis will delete all existing log entries from the log file.",
        ):
            return

        try:
            clear_log_file()
            self.clear_activity_preview()
            self.status_var.set("Log cleared")
        except Exception as error:
            messagebox.showerror("Log Error", str(error))

    # =========================================================
    # SETTINGS
    # =========================================================

    def build_settings_page(self):
        page = ttk.Frame(self.settings_page)
        page.pack(fill="both", expand=True, padx=15, pady=15)

        ttk.Label(page, text="Settings", style="Heading.TLabel").pack(
            anchor="w", pady=(0, 15)
        )

        location_frame = ttk.LabelFrame(page, text="Last Location")
        location_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(
            location_frame,
            text="The application remembers the last folder you selected.",
            style="Subtle.TLabel",
            wraplength=900,
        ).pack(anchor="w", padx=10, pady=10)

        ttk.Button(
            location_frame, text="Clear Saved Location", command=self.clear_saved_location
        ).pack(anchor="w", padx=10, pady=(0, 10))

        database_frame = ttk.LabelFrame(page, text="Database")
        database_frame.pack(fill="x")

        ttk.Label(
            database_frame,
            text="Resetting the database removes custom categories, subcategories, keywords and exclusions.",
            style="Subtle.TLabel",
            wraplength=900,
        ).pack(anchor="w", padx=10, pady=10)

        ttk.Button(database_frame, text="Reset Database", command=self.reset_database).pack(
            anchor="w", padx=10, pady=(0, 10)
        )

    def reset_database(self):
        if not messagebox.askyesno(
            "Reset Database",
            "Reset the database?\n\nAll custom categories and subcategories will be removed.",
        ):
            return

        clear_database()

        self.selected_item_type = None
        self.selected_category_name = None
        self.selected_subcategory_id = None

        self.refresh_category_tree()
        self.refresh_game_exclusions()
        self.clear_rule_editor()

        self.status_var.set("Database reset")

    # =========================================================
    # CATEGORIES PAGE
    # =========================================================

    def build_categories_page(self):
        page = ttk.Frame(self.categories_page)
        page.pack(fill="both", expand=True, padx=15, pady=15)

        ttk.Label(page, text="Categories", style="Heading.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        ttk.Label(
            page,
            text="Categories can contain unlimited levels of nested subcategories.",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        paned = ttk.PanedWindow(page, orient="horizontal")
        paned.pack(fill="both", expand=True)

        tree_pane = ttk.Frame(paned)
        rules_pane = ttk.Frame(paned)

        paned.add(tree_pane, weight=2)
        paned.add(rules_pane, weight=3)

        self.build_category_tree(tree_pane)
        self.build_rules_panel(rules_pane)

        self.refresh_category_tree()

    # =========================================================
    # CATEGORY TREE
    # =========================================================

    def build_category_tree(self, parent):
        frame = ttk.LabelFrame(parent, text="Category Structure")
        frame.pack(fill="both", expand=True, padx=(0, 8))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        tree_frame = ttk.Frame(frame)
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.category_tree = ttk.Treeview(
            tree_frame,
            columns=("type",),
            show="tree headings",
            height=18,
            selectmode="browse",
        )

        self.category_tree.heading("#0", text="Name")
        self.category_tree.heading("type", text="Type")
        self.category_tree.column("#0", width=320, minwidth=200)
        self.category_tree.column("type", width=110, minwidth=90, anchor="center")

        self.category_tree.tag_configure(
            "category", font=("Segoe UI", 10, "bold"), foreground=self.colors["text"]
        )
        self.category_tree.tag_configure(
            "subcategory", foreground=self.colors["text"]
        )
        self.category_tree.tag_configure(
            "games", font=("Segoe UI", 10, "italic"), foreground=self.colors["subtle"]
        )

        self.category_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.category_tree.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.category_tree.configure(yscrollcommand=scrollbar.set)

        self.category_tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        ttk.Button(buttons, text="New Category", command=self.create_category).pack(
            fill="x", pady=3
        )
        ttk.Button(buttons, text="Add Child", command=self.create_child).pack(
            fill="x", pady=3
        )
        ttk.Button(buttons, text="Delete Selected", command=self.delete_selected).pack(
            fill="x", pady=3
        )

    # =========================================================
    # CHILD LOOKUP
    # =========================================================

    def get_children_for_gui(self, parent_id, parent_type):
        try:
            return list(get_child_subcategories(parent_id, parent_type))

        except TypeError:
            try:
                children = get_child_subcategories(parent_id)
            except Exception:
                return []

            result = []

            for child in children:
                if str(child.get("parent_id", "")) != str(parent_id):
                    continue

                stored_type = child.get("parent_type")

                if stored_type:
                    if stored_type != parent_type:
                        continue
                elif parent_type != "category":
                    continue

                result.append(child)

            return result

    # =========================================================
    # REFRESH TREE
    # =========================================================

    def refresh_category_tree(self):
        if not hasattr(self, "category_tree"):
            return

        self.tree_metadata.clear()

        for item in self.category_tree.get_children():
            self.category_tree.delete(item)

        categories = get_all_categories()

        if isinstance(categories, dict):
            category_list = []

            for name in categories:
                category = get_category(name)

                if category:
                    category_list.append(category)

        else:
            category_list = list(categories)

        category_list.sort(key=lambda category: str(category.get("name", "")).lower())

        for category in category_list:
            category_name = category.get("name", "")

            if not category_name:
                continue

            tree_id = "category:" + str(category.doc_id)

            self.tree_metadata[tree_id] = {
                "type": "category",
                "category_name": category_name,
            }

            self.category_tree.insert(
                "",
                "end",
                iid=tree_id,
                text=category_name,
                values=("Category",),
                open=True,
                tags=("category",),
            )

            self.insert_subcategory_tree(
                tree_parent=tree_id,
                parent_id=category.doc_id,
                parent_type="category",
                ancestors=set(),
            )

        games_id = "games"
        self.tree_metadata[games_id] = {"type": "games"}

        self.category_tree.insert(
            "",
            "end",
            iid=games_id,
            text="Games",
            values=("Special",),
            tags=("games",),
        )

        self.restore_selection()

    def insert_subcategory_tree(self, tree_parent, parent_id, parent_type, ancestors):
        parent_key = str(parent_type) + ":" + str(parent_id)

        if parent_key in ancestors:
            return

        next_ancestors = set(ancestors)
        next_ancestors.add(parent_key)

        children = self.get_children_for_gui(parent_id, parent_type)
        children = sorted(children, key=lambda child: str(child.get("name", "")).lower())

        for child in children:
            child_id = child.doc_id
            tree_id = tree_parent + "/subcategory:" + str(child_id)

            if self.category_tree.exists(tree_id):
                continue

            self.tree_metadata[tree_id] = {
                "type": "subcategory",
                "subcategory_id": child_id,
            }

            self.category_tree.insert(
                tree_parent,
                "end",
                iid=tree_id,
                text="↳ " + child.get("name", "Unnamed"),
                values=("Subcategory",),
                open=True,
                tags=("subcategory",),
            )

            self.insert_subcategory_tree(
                tree_parent=tree_id,
                parent_id=child_id,
                parent_type="subcategory",
                ancestors=next_ancestors,
            )

    # =========================================================
    # TREE SELECTION
    # =========================================================

    def on_tree_select(self, _event=None):
        selection = self.category_tree.selection()

        if not selection:
            return

        tree_id = selection[0]
        metadata = self.tree_metadata.get(tree_id)

        if not metadata:
            return

        item_type = metadata.get("type")

        if item_type == "games":
            self.selected_item_type = "games"
            self.selected_category_name = None
            self.selected_subcategory_id = None
            self.show_games_rules()
            return

        if item_type == "category":
            category_name = metadata.get("category_name")

            self.selected_item_type = "category"
            self.selected_category_name = category_name
            self.selected_subcategory_id = None

            self.show_category_rules(category_name)
            return

        if item_type == "subcategory":
            subcategory_id = metadata.get("subcategory_id")
            subcategory = get_subcategory(subcategory_id)

            if subcategory is None:
                return

            self.selected_item_type = "subcategory"
            self.selected_subcategory_id = subcategory_id

            path = get_subcategory_path(subcategory)
            self.selected_category_name = (
                path[0] if path else subcategory.get("category")
            )

            self.show_subcategory_rules(subcategory)

    # =========================================================
    # RESTORE SELECTION
    # =========================================================

    def restore_selection(self):
        target = None

        if self.selected_item_type == "games":
            target = "games"

        elif self.selected_item_type == "category" and self.selected_category_name:
            category = get_category(self.selected_category_name)

            if category:
                target = "category:" + str(category.doc_id)

        elif (
            self.selected_item_type == "subcategory"
            and self.selected_subcategory_id is not None
        ):
            for tree_id, metadata in self.tree_metadata.items():
                if metadata.get("type") != "subcategory":
                    continue

                if metadata.get("subcategory_id") == self.selected_subcategory_id:
                    target = tree_id
                    break

        if target:
            self.select_tree_item(target)

    def select_tree_item(self, tree_id):
        if not self.category_tree.exists(tree_id):
            return

        parent = self.category_tree.parent(tree_id)

        while parent:
            self.category_tree.item(parent, open=True)
            parent = self.category_tree.parent(parent)

        self.category_tree.selection_set(tree_id)
        self.category_tree.focus(tree_id)
        self.category_tree.see(tree_id)

    def select_subcategory_by_id(self, subcategory_id):
        for tree_id, metadata in self.tree_metadata.items():
            if metadata.get("type") != "subcategory":
                continue

            if metadata.get("subcategory_id") == subcategory_id:
                self.select_tree_item(tree_id)
                return

    # =========================================================
    # RULE PANEL
    # =========================================================

    def build_rules_panel(self, parent):
        outer = ttk.LabelFrame(parent, text="Rules")
        outer.pack(fill="both", expand=True, padx=(8, 0))
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=15)

        ttk.Label(header, textvariable=self.rule_title_var, style="Heading.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            header, textvariable=self.rule_path_var, style="Subtle.TLabel", wraplength=750
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(outer)
        body.grid(row=1, column=0, sticky="nsew", padx=(15, 0), pady=(0, 15))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        canvas = tk.Canvas(
            body, highlightthickness=0, background=self.colors["bg"]
        )
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        self.rules_canvas = canvas
        self.rules_content = ttk.Frame(canvas)
        rules_window = canvas.create_window(0, 0, window=self.rules_content, anchor="nw")

        def on_content_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            canvas.itemconfigure(rules_window, width=event.width)

        self.rules_content.bind("<Configure>", on_content_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        self.bind_mousewheel(canvas)

        self.clear_rule_editor()

    def reset_rules_scroll(self):
        if not hasattr(self, "rules_canvas"):
            return

        self.rules_content.update_idletasks()
        self.rules_canvas.configure(scrollregion=self.rules_canvas.bbox("all"))
        self.rules_canvas.yview_moveto(0)

    # =========================================================
    # CATEGORY RULES
    # =========================================================

    def show_category_rules(self, category_name):
        category = get_category(category_name)

        if category is None:
            return

        self.clear_rules()

        self.rule_title_var.set(category_name)
        self.rule_path_var.set("Category")
        self.category_name_var.set(category_name)

        name_frame = ttk.LabelFrame(self.rules_content, text="Category Name")
        name_frame.pack(fill="x", pady=(0, 10))

        row = ttk.Frame(name_frame)
        row.pack(fill="x", padx=10, pady=10)
        row.columnconfigure(0, weight=1)

        ttk.Entry(row, textvariable=self.category_name_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(
            row,
            text="Save Name",
            command=lambda: self.rename_category(
                category_name, self.category_name_var.get()
            ),
        ).grid(row=0, column=1)

        self.build_rule_list(
            "Extensions",
            category.get("extensions", []),
            lambda value: self.add_category_extension(category_name, value),
            lambda value: self.remove_category_extension(category_name, value),
        )

        self.build_rule_list(
            "Keywords",
            category.get("keywords", []),
            lambda value: self.add_category_keyword(category_name, value),
            lambda value: self.remove_category_keyword(category_name, value),
        )

        self.build_rule_list(
            "Category Exclusions",
            category.get("exclusions", []),
            lambda value: self.add_category_exclusion(category_name, value),
            lambda value: self.remove_category_exclusion(category_name, value),
        )

        children_frame = ttk.LabelFrame(self.rules_content, text="Child Subcategories")
        children_frame.pack(fill="x", pady=(0, 10))

        children = self.get_children_for_gui(category.doc_id, "category")

        for child in children:
            ttk.Button(
                children_frame,
                text="↳ " + child.get("name", "Unnamed"),
                command=lambda cid=child.doc_id: self.select_subcategory_by_id(cid),
            ).pack(fill="x", padx=10, pady=3)

        ttk.Button(children_frame, text="Add Child", command=self.create_child).pack(
            anchor="w", padx=10, pady=10
        )

        self.reset_rules_scroll()

    # =========================================================
    # SUBCATEGORY RULES
    # =========================================================

    def show_subcategory_rules(self, subcategory):
        self.clear_rules()

        path = get_subcategory_path(subcategory)
        name = subcategory.get("name", "Subcategory")

        self.rule_title_var.set(name)
        self.rule_path_var.set(" → ".join(path))
        self.subcategory_name_var.set(name)

        name_frame = ttk.LabelFrame(self.rules_content, text="Subcategory Name")
        name_frame.pack(fill="x", pady=(0, 10))

        row = ttk.Frame(name_frame)
        row.pack(fill="x", padx=10, pady=10)
        row.columnconfigure(0, weight=1)

        ttk.Entry(row, textvariable=self.subcategory_name_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(
            row,
            text="Save Name",
            command=lambda: self.rename_subcategory(
                subcategory, self.subcategory_name_var.get()
            ),
        ).grid(row=0, column=1)

        self.build_rule_list(
            "Keywords",
            subcategory.get("keywords", []),
            lambda value: self.add_nested_keyword(subcategory, value),
            lambda value: self.remove_nested_keyword(subcategory, value),
        )

        self.build_rule_list(
            "Subcategory Exclusions",
            subcategory.get("exclusions", []),
            lambda value: self.add_nested_exclusion(subcategory, value),
            lambda value: self.remove_nested_exclusion(subcategory, value),
        )

        children_frame = ttk.LabelFrame(self.rules_content, text="Child Subcategories")
        children_frame.pack(fill="x", pady=(0, 10))

        children = self.get_children_for_gui(subcategory.doc_id, "subcategory")

        for child in children:
            ttk.Button(
                children_frame,
                text="↳ " + child.get("name", "Unnamed"),
                command=lambda cid=child.doc_id: self.select_subcategory_by_id(cid),
            ).pack(fill="x", padx=10, pady=3)

        ttk.Button(children_frame, text="Add Child", command=self.create_child).pack(
            anchor="w", padx=10, pady=10
        )

        destination_frame = ttk.LabelFrame(self.rules_content, text="Folder Destination")
        destination_frame.pack(fill="x", pady=(0, 10))

        destination = "\\".join(path)

        ttk.Label(
            destination_frame,
            text=destination
            + "\n\nExtensions are inherited from the top-level category.",
            style="Subtle.TLabel",
            wraplength=800,
            justify="left",
        ).pack(anchor="w", padx=10, pady=10)

        self.reset_rules_scroll()

    # =========================================================
    # GAMES RULES
    # =========================================================

    def show_games_rules(self):
        self.clear_rules()

        self.rule_title_var.set("Games")
        self.rule_path_var.set("Special entity — game exclusions only")

        frame = ttk.LabelFrame(self.rules_content, text="Game Exclusions")
        frame.pack(fill="x")

        ttk.Label(
            frame,
            text="These rules are applied before IGDB detection.",
            style="Subtle.TLabel",
        ).pack(anchor="w", padx=10, pady=10)

        for exclusion in get_game_exclusions():
            ttk.Label(frame, text="• " + exclusion).pack(anchor="w", padx=15, pady=2)

        self.reset_rules_scroll()

    # =========================================================
    # RULE LIST
    # =========================================================

    def build_rule_list(self, title, values, add_command, remove_command):
        frame = ttk.LabelFrame(self.rules_content, text=title)
        frame.pack(fill="x", pady=(0, 10))

        listbox = tk.Listbox(frame, height=6, exportselection=False)
        self.style_listbox(listbox)
        listbox.pack(fill="x", padx=10, pady=10)

        for value in values or []:
            listbox.insert(tk.END, value)

        row = ttk.Frame(frame)
        row.pack(fill="x", padx=10, pady=(0, 10))
        row.columnconfigure(0, weight=1)

        entry = ttk.Entry(row)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        def add_value():
            value = entry.get().strip()

            if not value:
                return

            entry.delete(0, tk.END)
            add_command(value)

        def remove_value():
            selection = listbox.curselection()

            if not selection:
                return

            remove_command(listbox.get(selection[0]))

        ttk.Button(row, text="Add", command=add_value).grid(row=0, column=1)
        ttk.Button(frame, text="Remove Selected", command=remove_value).pack(
            anchor="w", padx=10, pady=(0, 10)
        )

        entry.bind("<Return>", lambda _event: add_value())

    def clear_rules(self):
        for widget in self.rules_content.winfo_children():
            widget.destroy()

    def clear_rule_editor(self):
        if not hasattr(self, "rules_content"):
            return

        for widget in self.rules_content.winfo_children():
            widget.destroy()

        self.reset_rules_scroll()

    # =========================================================
    # CREATE CATEGORY
    # =========================================================

    def create_category(self):
        name = self.prompt_text("New Category", "Enter the category name:")

        if not name:
            return

        if get_category(name):
            messagebox.showwarning("Category Exists", "That category already exists.")
            return

        save_category(name=name, extensions=[], keywords=[], exclusions=[], protected=False)

        self.selected_item_type = "category"
        self.selected_category_name = name
        self.selected_subcategory_id = None

        self.refresh_category_tree()

    # =========================================================
    # CREATE CHILD
    # =========================================================

    def create_child(self):
        selection = self.category_tree.selection()

        if not selection:
            messagebox.showinfo("Add Child", "Select a category or subcategory first.")
            return

        metadata = self.tree_metadata.get(selection[0])

        if not metadata:
            return

        if metadata.get("type") == "games":
            messagebox.showinfo("Games", "Games cannot contain subcategories.")
            return

        name = self.prompt_text("New Subcategory", "Enter the child name:")

        if not name:
            return

        if metadata.get("type") == "category":
            category_name = metadata.get("category_name")
            category = get_category(category_name)

            if category is None:
                return

            children = self.get_children_for_gui(category.doc_id, "category")

            if self.child_exists(children, name):
                messagebox.showwarning("Already Exists", "That child already exists here.")
                return

            save_subcategory(
                category_name=category_name,
                name=name,
                parent_id=category.doc_id,
                parent_type="category",
            )

        else:
            parent_id = metadata.get("subcategory_id")
            parent = get_subcategory(parent_id)

            if parent is None:
                return

            children = self.get_children_for_gui(parent_id, "subcategory")

            if self.child_exists(children, name):
                messagebox.showwarning("Already Exists", "That child already exists here.")
                return

            save_subcategory(name=name, parent_id=parent_id, parent_type="subcategory")

        self.refresh_category_tree()

    def child_exists(self, children, name):
        name = name.strip().lower()

        for child in children:
            if child.get("name", "").strip().lower() == name:
                return True

        return False

    # =========================================================
    # DELETE
    # =========================================================

    def delete_selected(self):
        selection = self.category_tree.selection()

        if not selection:
            return

        metadata = self.tree_metadata.get(selection[0])

        if not metadata:
            return

        item_type = metadata.get("type")

        if item_type == "games":
            return

        if item_type == "category":
            category_name = metadata.get("category_name")
            category = get_category(category_name)

            if category is None:
                return

            if category.get("protected", False):
                messagebox.showwarning(
                    "Protected Category", "This default category cannot be deleted."
                )
                return

            if not messagebox.askyesno(
                "Delete Category",
                f"Delete '{category_name}'?\n\nAll nested subcategories will also be deleted.",
            ):
                return

            remove_category(category_name)

        elif item_type == "subcategory":
            subcategory_id = metadata.get("subcategory_id")
            subcategory = get_subcategory(subcategory_id)

            if subcategory is None:
                return

            name = subcategory.get("name", "Subcategory")

            if not messagebox.askyesno(
                "Delete Subcategory",
                f"Delete '{name}'?\n\nAll nested children will also be deleted.",
            ):
                return

            remove_subcategory(subcategory_id)

        self.selected_item_type = None
        self.selected_category_name = None
        self.selected_subcategory_id = None

        self.clear_rule_editor()
        self.refresh_category_tree()

    # =========================================================
    # CATEGORY RENAME
    # =========================================================

    def rename_category(self, old_name, new_name):
        new_name = new_name.strip()

        if not new_name or old_name == new_name:
            return

        category = get_category(old_name)

        if category is None:
            return

        if category.get("protected", False):
            messagebox.showwarning(
                "Protected Category", "Default categories cannot be renamed."
            )
            return

        if get_category(new_name) is not None:
            messagebox.showwarning("Category Exists", "That category already exists.")
            return

        save_category(
            name=new_name,
            extensions=category.get("extensions", []),
            keywords=category.get("keywords", []),
            exclusions=category.get("exclusions", []),
            protected=False,
            doc_id=category.doc_id,
        )

        self.selected_category_name = new_name
        self.refresh_category_tree()

    # =========================================================
    # SUBCATEGORY RENAME
    # =========================================================

    def rename_subcategory(self, subcategory, new_name):
        new_name = new_name.strip()

        if not new_name:
            return

        old_name = subcategory.get("name", "")

        if old_name == new_name:
            return

        parent_id = subcategory.get("parent_id")
        parent_type = subcategory.get("parent_type", "category")

        siblings = self.get_children_for_gui(parent_id, parent_type)

        for sibling in siblings:
            if sibling.doc_id == subcategory.doc_id:
                continue

            if sibling.get("name", "").strip().lower() == new_name.lower():
                messagebox.showwarning(
                    "Already Exists", "A subcategory with that name already exists."
                )
                return

        save_subcategory(
            name=new_name,
            parent_id=parent_id,
            parent_type=parent_type,
            keywords=subcategory.get("keywords", []),
            exclusions=subcategory.get("exclusions", []),
            doc_id=subcategory.doc_id,
        )

        self.selected_item_type = "subcategory"
        self.selected_subcategory_id = subcategory.doc_id

        self.refresh_category_tree()
        self.select_subcategory_by_id(subcategory.doc_id)

    # =========================================================
    # CATEGORY RULES
    # =========================================================

    def add_category_extension(self, category, value):
        add_extension(category, value)
        self.show_category_rules(category)

    def remove_category_extension(self, category, value):
        remove_extension(category, value)
        self.show_category_rules(category)

    def add_category_keyword(self, category, value):
        add_keyword(category, value)
        self.show_category_rules(category)

    def remove_category_keyword(self, category, value):
        remove_keyword(category, value)
        self.show_category_rules(category)

    def add_category_exclusion(self, category, value):
        add_category_exclusion(category, value)
        self.show_category_rules(category)

    def remove_category_exclusion(self, category, value):
        remove_category_exclusion(category, value)
        self.show_category_rules(category)

    # =========================================================
    # NESTED RULES
    # =========================================================

    def add_nested_keyword(self, subcategory, value):
        keywords = set(subcategory.get("keywords", []))
        keywords.add(value)

        save_subcategory(
            name=subcategory.get("name"),
            parent_id=subcategory.get("parent_id"),
            parent_type=subcategory.get("parent_type"),
            keywords=keywords,
            exclusions=subcategory.get("exclusions", []),
            doc_id=subcategory.doc_id,
        )

        refreshed = get_subcategory(subcategory.doc_id)

        if refreshed:
            self.show_subcategory_rules(refreshed)

    def remove_nested_keyword(self, subcategory, value):
        keywords = set(subcategory.get("keywords", []))
        keywords.discard(value)

        save_subcategory(
            name=subcategory.get("name"),
            parent_id=subcategory.get("parent_id"),
            parent_type=subcategory.get("parent_type"),
            keywords=keywords,
            exclusions=subcategory.get("exclusions", []),
            doc_id=subcategory.doc_id,
        )

        refreshed = get_subcategory(subcategory.doc_id)

        if refreshed:
            self.show_subcategory_rules(refreshed)

    def add_nested_exclusion(self, subcategory, value):
        exclusions = set(subcategory.get("exclusions", []))
        exclusions.add(value)

        save_subcategory(
            name=subcategory.get("name"),
            parent_id=subcategory.get("parent_id"),
            parent_type=subcategory.get("parent_type"),
            keywords=subcategory.get("keywords", []),
            exclusions=exclusions,
            doc_id=subcategory.doc_id,
        )

        refreshed = get_subcategory(subcategory.doc_id)

        if refreshed:
            self.show_subcategory_rules(refreshed)

    def remove_nested_exclusion(self, subcategory, value):
        exclusions = set(subcategory.get("exclusions", []))
        exclusions.discard(value)

        save_subcategory(
            name=subcategory.get("name"),
            parent_id=subcategory.get("parent_id"),
            parent_type=subcategory.get("parent_type"),
            keywords=subcategory.get("keywords", []),
            exclusions=exclusions,
            doc_id=subcategory.doc_id,
        )

        refreshed = get_subcategory(subcategory.doc_id)

        if refreshed:
            self.show_subcategory_rules(refreshed)

    # =========================================================
    # TEXT HELPERS
    # =========================================================

    def set_text_widget(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.see(tk.END)
        widget.configure(state="disabled")

    def append_text_widget(self, widget, text):
        widget.configure(state="normal")
        widget.insert(tk.END, text)
        widget.see(tk.END)
        widget.configure(state="disabled")

    # =========================================================
    # INPUT DIALOG
    # =========================================================

    def prompt_text(self, title, prompt):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(background=self.colors["bg"])
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        result = {"value": None}

        frame = ttk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        ttk.Label(frame, text=prompt, wraplength=650).pack(anchor="w", pady=(0, 10))

        entry = ttk.Entry(frame, width=70)
        entry.pack(fill="x", pady=(0, 10))
        entry.focus_set()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")

        def accept():
            value = entry.get().strip()

            if value:
                result["value"] = value

            dialog.destroy()

        def cancel():
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=cancel).pack(side="right")
        ttk.Button(buttons, text="OK", style="Action.TButton", command=accept).pack(
            side="right", padx=8
        )

        entry.bind("<Return>", lambda _event: accept())
        entry.bind("<Escape>", lambda _event: cancel())

        self.root.wait_window(dialog)

        return result["value"]

    # =========================================================
    # CLOSE
    # =========================================================

    def on_close(self):
        try:
            self.remember_current_location()
        except Exception:
            pass

        try:
            remove_gui_log_handler()
        except Exception:
            pass

        self.root.destroy()


def main():
    root = tk.Tk()
    DownloadsOrganizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()