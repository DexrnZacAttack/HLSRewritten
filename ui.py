# standard library imports
import ctypes
import html.parser
import inspect
import io
import json
import os
import stat
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
import zipfile
from urllib.parse import urlparse
import argparse
from packaging import version
import psutil
import datetime
import pytz
import logging

# third-party imports
import appdirs
import requests
import tkinter as tk
from dotenv import load_dotenv
from PIL import Image, ImageTk
from tkinter import ttk, filedialog, messagebox

# windows-specific imports
import winreg

# linux-specific imports
import tarfile

# created by pyoid for more information visit the github repository
# small portions of this code were developed with assistance from anthropic's claude 35 sonnet
# if you need support ping me on discord @pyoid

load_dotenv()

# class to redirect logging output to a custom writer
class LoggerWriter:
    def __init__(self, level):
        self.level = level

    def write(self, message):
        if message != '\n':
            self.level(message)

    def flush(self):
        pass

# html parser to strip tags from text
class MLStripper(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.text = []
    
    def handle_data(self, d):
        self.text.append(d)
    
    def get_data(self):
        return ''.join(self.text)

# removes html tags from a string
def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

# attempts to run a command with elevated privileges
def elevate(cmd):
    if platform.system() == 'Windows':
        try:
            return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, cmd, None, 1)
        except Exception as e:
            logging.info(f"Error in elevation: {str(e)}")
            return False
    elif platform.system() == 'Linux':
        try:
            return subprocess.run(['pkexec', sys.executable] + cmd.split(), check=True)
        except subprocess.CalledProcessError as e:
            logging.info(f"Error in elevation: {str(e)}")
            return False

# retrieves the current version of the application
def get_version():
        if getattr(sys, 'frozen', False):
            # running as compiled executable
            bundle_dir = sys._MEIPASS
        else:
            # running in a normal python environment
            bundle_dir = os.path.dirname(os.path.abspath(__file__))
        
        version_file = os.path.join(bundle_dir, 'version.json')
        
        try:
            with open(version_file, 'r') as f:
                version_data = json.load(f)
                return version_data.get('version', 'Unknown')
        except Exception as e:
            logging.info(f"Error reading version file: {e}")
            return 'Unknown'

# main class for the hook line sinker user interface
class HookLineSinkerUI:
    def __init__(self, root):
        self.root = root
        self.app_data_dir = appdirs.user_data_dir("Hook_Line_Sinker", "PyoidTM")
        self.setup_logging()
        self.gui_queue = queue.Queue()
        self.gdweave_queue = queue.Queue()
        
        version = get_version()

        self.root.title(f"Hook, Line, & Sinker v{version} - WEBFISHING Mod Manager")
        self.root.geometry("800x600")

        icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
        if os.path.exists(icon_path):
            if platform.system() == 'Windows':
                self.root.iconbitmap(icon_path)
            elif platform.system() == 'Linux':
                img = tk.PhotoImage(file=icon_path)
                self.root.tk.call('wm', 'iconphoto', self.root._w, img)
        else:
            logging.info("Warning: icon.ico not found")
            
        self.app_data_dir = appdirs.user_data_dir("Hook_Line_Sinker", "PyoidTM")
        self.mods_dir = os.path.join(self.app_data_dir, "mods")
        self.mod_cache_file = os.path.join(self.app_data_dir, "mod_cache.json")
        os.makedirs(self.mods_dir, exist_ok=True)

        self.available_mods = []
        self.installed_mods = []
        self.mod_packs = {
            "Vanilla+": ["WebfishingPlus", "SprintToggle", "QuickGamble", "BorderlessFix", "SaveCanvas"],
            "Quality of Life": ["WebfishingPlus", "SprintToggle", "QuickGamble", "BorderlessFix", "SaveCanvas", "EventAlert", "Automasher"],
            "Accessibility": ["Automasher", "EventAlert", "SprintToggle", "LegibleChat", "BionicFisher"],
            "Fishing Enthusiast": ["Fishing+", "BionicFisher", "Lure", "MidiStrummer"],
            "Visual Enhancements": ["BorderlessFix", "SaveCanvas", "WebfishingRichPresence"]
        }

        self.mod_categories = {
            "Automasher": "Accessibility",
            "BionicFisher": "Accessibility",
            "LegibleChat": "Accessibility",
            "BorderlessFix": "Improvements",
            "SaveCanvas": "Improvements",
            "EventAlert": "Quality of Life",
            "Fishing+": "Quality of Life",
            "NeoQOLPack": "Quality of Life",
            "Nyoom!!!": "Quality of Life",
            "PropTweaks": "Quality of Life",
            "QuickGamble": "Quality of Life",
            "SprintToggle": "Quality of Life",
            "WebfishingPlus": "Quality of Life",
            "Lure": "Customization",
            "MidiStrummer": "Customization",
            "RAYTRAC3R's Cosmetics": "Customization",
            "VoiceTrainedSpecies": "Customization",
            "WebfishingRichPresence": "Customization"
        }
        
        self.load_settings()
        self.load_mod_cache()

        # initialize attributes
        self.auto_update = tk.BooleanVar(value=self.settings.get('auto_update', True))
        self.notifications = tk.BooleanVar(value=self.settings.get('notifications', False))
        self.theme = tk.StringVar(value=self.settings.get('theme', 'System'))
        self.game_path_entry = tk.StringVar(value=self.settings.get('game_path', ''))

        logging.info(f"Initial game path: {self.game_path_entry.get()}")

        # create status bar
        self.create_status_bar()

        # initialize notebook
        self.notebook = None

        self.create_main_ui()

        # check for updates on startup and show discord prompt
        self.check_for_fresh_update()
        self.check_for_program_updates()
        self.show_discord_prompt()
        self.check_admin_rights()

        # check if this is a fresh update
        parser = argparse.ArgumentParser()
        parser.add_argument('--fresh-update', action='store_true')
        args = parser.parse_args()

        if args.fresh_update:
            self.show_update_complete()

        # start update checking thread
        self.update_thread = threading.Thread(target=self.periodic_update_check, daemon=True)
        self.update_thread.start()

    # sets up logging to write to latestlog.txt
    def setup_logging(self):
        log_file = os.path.join(self.app_data_dir, 'latestlog.txt')
        
        # ensure the directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # clear the old log file or create a new one if it doesn't exist
        open(log_file, 'w').close()
        
        # set up logging
        logging.basicConfig(
            filename=log_file,
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # redirect stdout and stderr to the log file
        sys.stdout = LoggerWriter(logging.info)
        sys.stderr = LoggerWriter(logging.error)

    # opens the latest log file in a new window
    def open_latest_log(self):
        log_path = os.path.join(self.app_data_dir, 'latestlog.txt')
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                log_content = f.read()
            
            # create a new top-level window
            log_window = tk.Toplevel(self.root)
            log_window.title("Latest Log")
            log_window.geometry("800x600")
            
            # set the window icon
            icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
            if os.path.exists(icon_path):
                log_window.iconbitmap(icon_path)

            # add a text widget to display the log content
            log_text = tk.Text(log_window, wrap=tk.NONE)
            log_text.pack(expand=True, fill='both')

            # add scrollbars
            y_scrollbar = ttk.Scrollbar(log_window, orient='vertical', command=log_text.yview)
            y_scrollbar.pack(side='right', fill='y')
            x_scrollbar = ttk.Scrollbar(log_window, orient='horizontal', command=log_text.xview)
            x_scrollbar.pack(side='bottom', fill='x')

            log_text.config(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)

            # insert the log content
            log_text.insert(tk.END, log_content)
            log_text.config(state='disabled')  # make the text read-only
        else:
            messagebox.showerror("Error", "Latest log file not found.")

    # checks if the program has admin rights
    def has_admin_rights(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except AttributeError:
            return False  # assume not an admin on non-windows platforms (needs changing)

    # checks for admin rights and shows an error if not present
    def check_admin_rights(self):
        if not self.has_admin_rights():
            messagebox.showerror("Admin Rights Required", "Please run Hook, Line, & Sinker as administrator to modify game files.")
            return False
        return True
    
    # checks if the game is currently running
    def is_game_running(self):
        game_exe = 'webfishing.exe' if sys.platform.startswith('win') else 'webfishing.x86_64'
        for process in psutil.process_iter(['name']):
            if process.info['name'] == game_exe:
                return True
        return False

    # checks if the game is not running and shows an error if it is
    def check_game_not_running(self):
        if self.is_game_running():
            messagebox.showerror("Game Running", "Please close WEBFISHING before performing this action.")
            return False
        return True

    # checks for a fresh update and shows a message if one is found
    def check_for_fresh_update(self):
        current_version = version.parse(get_version())
        last_update_version = self.settings.get('last_update_version')
        
        if last_update_version:
            last_update_version = version.parse(last_update_version)
            if current_version > last_update_version:
                messagebox.showinfo("Update Complete", f"Hook, Line, & Sinker has been updated to version {current_version}.")
                self.settings['last_update_version'] = str(current_version)
                self.save_settings()
                
    # sends an error report to discord
    def send_to_discord(self, message, function_name=None):
        webhook_url = "https://hooklinesinker.lol/webhook"

        try:
            dotnet_installed = self.check_dotnet(silent=True)

            if function_name is None:
                # get the name of the calling function
                function_name = inspect.currentframe().f_back.f_code.co_name

            data = {
                "embeds": [{
                    "title": f"Error Report - Hook, Line, & Sinker - {function_name}",
                    "description": message,
                    "color": 16711680,  # red color
                    "fields": [
                        {"name": "HLS Version", "value": get_version(), "inline": True},
                        {"name": "GDWeave Version", "value": self.settings.get('gdweave_version', 'Unknown'), "inline": True},
                        {"name": "User Settings", "value": f"Auto Update: {self.settings.get('auto_update', 'N/A')}\nNotifications: {self.settings.get('notifications', 'N/A')}\nTheme: {self.settings.get('theme', 'N/A')}", "inline": False},
                        {"name": "Game Path", "value": self.settings.get('game_path', 'N/A'), "inline": False},
                        {"name": "Installed Mods", "value": ', '.join([mod['title'] for mod in self.installed_mods]) if self.installed_mods else 'None', "inline": False},
                        {"name": "System Info", "value": f"OS: {platform.system()} {platform.release()}\nPython: {platform.python_version()}\n.NET Installed: {'Yes' if dotnet_installed else 'No'}", "inline": False}
                    ]
                }]
            }
            response = requests.post(webhook_url, json=data)
            response.raise_for_status()
            logging.info("Error report sent to Discord successfully")
        except Exception as e:
            logging.info(f"Failed to send error report to Discord: {str(e)}")

    # toggles gdweave on or off
    def toggle_gdweave(self):
        if not self.check_game_not_running():
            return

        if not self.settings.get('game_path'):
            messagebox.showerror("Error", "Game path not set. Please set the game path first.")
            return

        game_path = self.settings['game_path']
        gdweave_game_path = os.path.join(game_path, 'GDWeave')
        winmm_game_path = os.path.join(game_path, 'winmm.dll')
        
        gdweave_backup_path = os.path.join(self.app_data_dir, 'GDWeave_Backup')
        winmm_backup_path = os.path.join(self.app_data_dir, 'winmm_backup.dll')

        if os.path.exists(gdweave_game_path) or os.path.exists(winmm_game_path):
            # gdweave is currently in the game folder let's move it to backup
            try:
                if os.path.exists(gdweave_game_path):
                    shutil.move(gdweave_game_path, gdweave_backup_path)
                if os.path.exists(winmm_game_path):
                    shutil.move(winmm_game_path, winmm_backup_path)
                messagebox.showinfo("Success", "GDWeave has been disabled and backed up.")
                self.set_status("GDWeave disabled and backed up")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to disable GDWeave: {str(e)}")
                self.send_to_discord(f"Error disabling GDWeave in Hook, Line, & Sinker:\n{str(e)}")
                return
        else:
            # gdweave is not in the game folder let's restore it from backup
            try:
                if os.path.exists(gdweave_backup_path):
                    shutil.move(gdweave_backup_path, gdweave_game_path)
                if os.path.exists(winmm_backup_path):
                    shutil.move(winmm_backup_path, winmm_game_path)
                messagebox.showinfo("Success", "GDWeave has been enabled and restored.")
                self.set_status("GDWeave enabled and restored")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to enable GDWeave: {str(e)}")
                self.send_to_discord(f"Error enabling GDWeave in Hook, Line, & Sinker:\n{str(e)}")
                return

        self.update_toggle_gdweave_button()
        self.update_setup_status()

    # uninstalls gdweave
    def uninstall_gdweave(self):
        if not self.settings.get('game_path'):
            messagebox.showerror("Error", "Game path not set. Please set the game path first.")
            return

        gdweave_path = os.path.join(self.settings['game_path'], 'GDWeave')
        winmm_path = os.path.join(self.settings['game_path'], 'winmm.dll')
        
        if not os.path.exists(gdweave_path) and not os.path.exists(winmm_path):
            messagebox.showinfo("Info", "GDWeave is not installed.")
            return

        if messagebox.askyesno("Confirm Uninstall", "Are you sure you want to uninstall GDWeave? This will remove the GDWeave folder, all mods within it, and the winmm.dll file from your game directory."):
            try:
                # attempt to remove gdweave folder and winmmdll without elevation
                shutil.rmtree(gdweave_path, ignore_errors=True)
                if os.path.exists(winmm_path):
                    os.remove(winmm_path)

                # check if files still exist
                remaining_files = []
                if os.path.exists(gdweave_path):
                    remaining_files.append("GDWeave folder")
                if os.path.exists(winmm_path):
                    remaining_files.append("winmm.dll")
                
                if remaining_files:
                    # some files couldn't be deleted, possibly due to permissions or open programs
                    warning_message = f"Some files could not be deleted: {', '.join(remaining_files)}. This may be due to insufficient permissions or open programs. Please close all related programs and try again."
                    messagebox.showwarning("Partial Uninstall", warning_message)
                    self.set_status("GDWeave partially uninstalled")
                    self.send_to_discord(f"Partial GDWeave uninstall in Hook, Line, & Sinker:\n{warning_message}")
                else:
                    # uninstall successful, update settings and ui
                    self.settings['gdweave_version'] = None
                    self.save_settings()
                    self.set_status("GDWeave uninstalled successfully")
                    messagebox.showinfo("Success", "GDWeave has been uninstalled successfully.")
                
                # refresh ui elements
                self.update_setup_status()
                self.update_toggle_gdweave_button()
                logging.info("GDWeave uninstallation process completed.")

            except Exception as e:
                # handle any unexpected errors during uninstallation
                error_message = f"Failed to uninstall GDWeave: {str(e)}"
                self.set_status(error_message)
                messagebox.showerror("Error", error_message)
                self.send_to_discord(f"Error uninstalling GDWeave in Hook, Line, & Sinker:\n{error_message}")

    def create_main_ui(self):
        # create and set up the main user interface
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both')

        # create various tabs for different functionalities
        self.create_mod_manager_tab()
        self.create_mod_packs_tab()
        self.create_game_manager_tab()
        self.create_hls_setup_tab()
        self.create_settings_tab()
        
        # initialize mod-related functions
        self.copy_existing_gdweave_mods()
        self.load_available_mods()
        self.refresh_mod_lists()

    def create_mod_manager_tab(self):
        # create the mod manager tab for managing game modifications
        mod_manager_frame = ttk.Frame(self.notebook)
        self.notebook.add(mod_manager_frame, text="Mod Manager")

        # configure grid layout
        mod_manager_frame.grid_columnconfigure(0, weight=1)
        mod_manager_frame.grid_columnconfigure(1, weight=0)
        mod_manager_frame.grid_columnconfigure(2, weight=1)
        mod_manager_frame.grid_rowconfigure(0, weight=3)
        mod_manager_frame.grid_rowconfigure(1, weight=1)

        # create left panel for available mods
        available_frame = ttk.LabelFrame(mod_manager_frame, text="Available Mods")
        available_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # create search functionality for available mods
        self.available_search = ttk.Entry(available_frame)
        self.available_search.grid(row=0, column=0, pady=2, padx=2, sticky="ew")
        self.available_search.insert(0, "Search available mods...")
        self.available_search.bind("<FocusIn>", lambda e: self.clear_placeholder(e, "Search available mods..."))
        self.available_search.bind("<FocusOut>", lambda e: self.restore_placeholder(e, "Search available mods..."))
        self.available_search.bind("<KeyRelease>", self.search_available_mods)

        # create listbox for available mods
        self.available_listbox = tk.Listbox(available_frame, width=30, height=15, selectmode=tk.EXTENDED)
        self.available_listbox.grid(row=1, column=0, pady=2, padx=2, sticky="nsew")
        self.available_listbox.bind('<<ListboxSelect>>', self.update_mod_details)
        self.available_listbox.bind('<Button-3>', self.show_context_menu)

        available_frame.grid_columnconfigure(0, weight=1)
        available_frame.grid_rowconfigure(1, weight=1)

        # create middle panel for action buttons
        action_frame = ttk.Frame(mod_manager_frame)
        action_frame.grid(row=0, column=1, padx=5, pady=5, sticky="ns")

        action_frame.grid_rowconfigure(0, weight=1)
        action_frame.grid_rowconfigure(5, weight=1)

        # create game control section
        game_control_frame = ttk.LabelFrame(action_frame, text="Game Control")
        game_control_frame.grid(row=1, column=0, pady=5, padx=5, sticky="ew")
        game_control_frame.grid_columnconfigure(0, weight=1)
        self.game_button = ttk.Button(game_control_frame, text="Start Game", command=self.toggle_game)
        self.game_button.grid(row=0, column=0, pady=2, padx=2, sticky="ew")

        # create mod management section
        mod_management_frame = ttk.LabelFrame(action_frame, text="Mod Management")
        mod_management_frame.grid(row=2, column=0, pady=5, padx=5, sticky="ew")
        mod_management_frame.grid_columnconfigure(0, weight=1)
        mod_management_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(mod_management_frame, text="Install", command=self.install_mod).grid(row=0, column=0, pady=2, padx=2, sticky="ew")
        ttk.Button(mod_management_frame, text="Uninstall", command=self.uninstall_mod).grid(row=0, column=1, pady=2, padx=2, sticky="ew")
        ttk.Button(mod_management_frame, text="Enable", command=self.enable_mod).grid(row=1, column=0, pady=2, padx=2, sticky="ew")
        ttk.Button(mod_management_frame, text="Disable", command=self.disable_mod).grid(row=1, column=1, pady=2, padx=2, sticky="ew")

        # create mod configuration section
        mod_config_frame = ttk.LabelFrame(action_frame, text="Mod Configuration")
        mod_config_frame.grid(row=3, column=0, pady=5, padx=5, sticky="ew")
        mod_config_frame.grid_columnconfigure(0, weight=1)
        ttk.Button(mod_config_frame, text="Edit Config", command=self.edit_mod_config).grid(row=0, column=0, pady=2, padx=2, sticky="ew")

        # create 3rd party mods section
        third_party_frame = ttk.LabelFrame(action_frame, text="3rd Party Mods")
        third_party_frame.grid(row=4, column=0, pady=5, padx=5, sticky="ew")
        third_party_frame.grid_columnconfigure(0, weight=1)
        third_party_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(third_party_frame, text="Import ZIP", command=self.import_zip_mod).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(third_party_frame, text="Refresh Mods", command=self.refresh_all_mods).grid(row=0, column=1, padx=2, pady=2, sticky="ew")

        # create help section
        help_frame = ttk.LabelFrame(action_frame, text="Need Help?")
        help_frame.grid(row=5, column=0, pady=5, padx=5, sticky="ew")
        help_frame.grid_columnconfigure(0, weight=1)
        help_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(help_frame, text="Join Discord", command=lambda: webbrowser.open("https://discord.gg/HzhCPxeCKY")).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(help_frame, text="Visit Website", command=lambda: webbrowser.open("https://hooklinesinker.lol")).grid(row=0, column=1, padx=2, pady=2, sticky="ew")

        # create right panel for installed mods
        installed_frame = ttk.LabelFrame(mod_manager_frame, text="Installed Mods")
        installed_frame.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")

        # create search functionality for installed mods
        self.installed_search = ttk.Entry(installed_frame)
        self.installed_search.grid(row=0, column=0, pady=2, padx=2, sticky="ew")
        self.installed_search.insert(0, "Search installed mods...")
        self.installed_search.bind("<FocusIn>", lambda e: self.clear_placeholder(e, "Search installed mods..."))
        self.installed_search.bind("<FocusOut>", lambda e: self.restore_placeholder(e, "Search installed mods..."))
        self.installed_search.bind("<KeyRelease>", self.search_installed_mods)

        # create listbox for installed mods
        self.installed_listbox = tk.Listbox(installed_frame, width=30, height=15, selectmode=tk.EXTENDED)
        self.installed_listbox.grid(row=1, column=0, pady=2, padx=2, sticky="nsew")
        self.installed_listbox.bind('<<ListboxSelect>>', self.update_mod_details)
        self.installed_listbox.bind('<Button-3>', self.show_context_menu)

        installed_frame.grid_columnconfigure(0, weight=1)
        installed_frame.grid_rowconfigure(1, weight=1)

        # create bottom panel for mod details
        details_frame = ttk.LabelFrame(mod_manager_frame, text="Mod Details")
        details_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

        self.mod_image = ttk.Label(details_frame)
        self.mod_image.grid(row=0, column=0, padx=5, pady=5, sticky="nw")

        self.mod_details = tk.Text(details_frame, wrap=tk.WORD, height=8, state='disabled')
        self.mod_details.grid(row=0, column=1, pady=2, padx=2, sticky="nsew")

        details_frame.grid_columnconfigure(1, weight=1)
        details_frame.grid_rowconfigure(0, weight=1)

    def toggle_game(self):
        # toggle game start/stop functionality
        if not self.check_setup():
            messagebox.showinfo("Setup Required", "Please follow all the steps for installation in the HLS Setup tab.")
            self.notebook.select(3)  # switch to hls setup tab
            return

        game_exe = os.path.join(self.settings['game_path'], 'webfishing.exe')
        if not os.path.exists(game_exe):
            messagebox.showerror("Error", "Game executable not found. Please check your game path.")
            return

        if self.game_button['text'] == "Start Game":
            try:
                # attempt to start the game
                subprocess.Popen(game_exe)
                self.game_button['text'] = "Stop Game"
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start the game: {str(e)}")
        else:
            try:
                # attempt to stop the game
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'] == 'webfishing.exe':
                        proc.terminate()
                        proc.wait(timeout=5)
                self.game_button['text'] = "Start Game"
            except Exception as e:
                messagebox.showerror("Error", f"Failed to stop the game: {str(e)}")
        
    def create_mod_packs_tab(self):
        # create the mod packs tab for managing curated collections of mods
        mod_packs_frame = ttk.Frame(self.notebook)
        self.notebook.add(mod_packs_frame, text="Mod Packs")

        mod_packs_frame.grid_columnconfigure(0, weight=1)
        mod_packs_frame.grid_rowconfigure(2, weight=1)  # increased to accommodate the subtitle

        # create title and subtitle
        title_label = ttk.Label(mod_packs_frame, text="Mod Packs", font=("Helvetica", 16, "bold"))
        title_label.grid(row=0, column=0, pady=(20, 5), padx=20, sticky="w")

        subtitle_label = ttk.Label(mod_packs_frame, text="Quickly apply curated collections of mods", font=("Helvetica", 10, "italic"))
        subtitle_label.grid(row=1, column=0, pady=(0, 10), padx=20, sticky="w")

        # create frame for mod packs
        packs_frame = ttk.Frame(mod_packs_frame)
        packs_frame.grid(row=2, column=0, pady=10, padx=20, sticky="nsew")
        packs_frame.grid_columnconfigure(0, weight=1)

        # create buttons for each mod pack
        for i, (pack_name, mods) in enumerate(self.mod_packs.items()):
            pack_frame = ttk.Frame(packs_frame)
            pack_frame.grid(row=i, column=0, pady=5, padx=5, sticky="ew")
            pack_frame.grid_columnconfigure(1, weight=1)

            ttk.Label(pack_frame, text=pack_name, font=("Helvetica", 12, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 10))
            ttk.Label(pack_frame, text=", ".join(mods), wraplength=400).grid(row=0, column=1, sticky="w")
            ttk.Button(pack_frame, text="Apply", command=lambda p=pack_name: self.apply_mod_pack(p)).grid(row=0, column=2, padx=(10, 0))

        # add a note about mod pack behavior
        note_label = ttk.Label(mod_packs_frame, text="Note: Applying a mod pack will disable all current mods and enable only the mods in the selected pack.", wraplength=600, justify="left", font=("Helvetica", 10, "italic"))
        note_label.grid(row=3, column=0, pady=(20, 10), padx=20, sticky="w")

    def apply_mod_pack(self, pack_name):
        # apply a selected mod pack
        if not self.check_setup():
            return

        if not self.check_game_not_running():
            return

        if messagebox.askyesno("Apply Mod Pack", f"Are you sure you want to apply the '{pack_name}' mod pack? This will disable all current mods and enable only the mods in the pack."):
            self.set_status(f"Applying mod pack: {pack_name}")

            # disable all current mods
            for mod in self.installed_mods:
                mod['enabled'] = False
                self.save_mod_status(mod)
                self.remove_mod_from_game(mod)

            # enable mods in the pack
            pack_mods = self.mod_packs[pack_name]
            for mod_title in pack_mods:
                self.enable_mod_by_title(mod_title)

            self.refresh_mod_lists()
            self.set_status(f"Mod pack '{pack_name}' applied successfully!")

    def enable_mod_by_title(self, mod_title):
        # enable a mod by its title
        for mod in self.installed_mods:
            if mod['title'].lower() == mod_title.lower():
                mod['enabled'] = True
                self.save_mod_status(mod)
                self.copy_mod_to_game(mod)
                logging.info(f"Enabled mod: {mod['title']} (ID: {mod['id']}, Third Party: {mod.get('third_party', False)})")
                return

        # if the mod is not installed, try to install it
        for available_mod in self.available_mods:
            if available_mod['title'].lower() == mod_title.lower():
                self.download_and_install_mod(available_mod)
                return

        logging.info(f"Warning: Mod '{mod_title}' not found in installed or available mods.")

    def create_game_manager_tab(self):
        # create the game manager tab for managing save files
        game_manager_frame = ttk.Frame(self.notebook)
        self.notebook.add(game_manager_frame, text="Save Manager")

        game_manager_frame.grid_columnconfigure(0, weight=1)
        game_manager_frame.grid_rowconfigure(5, weight=1)  # increased to accommodate the subtitle

        # create title and subtitle
        title_label = ttk.Label(game_manager_frame, text="Save Manager", font=("Helvetica", 16, "bold"))
        title_label.grid(row=0, column=0, pady=(20, 5), padx=20, sticky="w")

        subtitle_label = ttk.Label(game_manager_frame, text="Backup and restore your game progress", font=("Helvetica", 10, "italic"))
        subtitle_label.grid(row=1, column=0, pady=(0, 10), padx=20, sticky="w")

        # display save file location
        save_path = os.path.join(os.getenv('APPDATA'), 'Godot', 'app_userdata', 'webfishing_2_newver', 'webfishing_migrated_data.save')
        save_label = ttk.Label(game_manager_frame, text="Save file location:")
        save_label.grid(row=2, column=0, pady=(0, 5), padx=20, sticky="w")
        
        save_path_entry = ttk.Entry(game_manager_frame, width=70)
        save_path_entry.insert(0, save_path)
        save_path_entry.config(state='readonly')
        save_path_entry.grid(row=3, column=0, pady=(0, 10), padx=20, sticky="w")

        # create backup frame
        backup_frame = ttk.LabelFrame(game_manager_frame, text="Backup Save")
        backup_frame.grid(row=4, column=0, pady=10, padx=20, sticky="ew")
        backup_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(backup_frame, text="Backup Name:").grid(row=0, column=0, pady=5, padx=5, sticky="w")
        self.backup_name_entry = ttk.Entry(backup_frame)
        self.backup_name_entry.grid(row=0, column=1, pady=5, padx=5, sticky="ew")
        ttk.Button(backup_frame, text="Create Backup", command=self.create_backup).grid(row=0, column=2, pady=5, padx=5)

        # create restore frame
        restore_frame = ttk.LabelFrame(game_manager_frame, text="Manage Saves")
        restore_frame.grid(row=5, column=0, pady=10, padx=20, sticky="nsew")
        restore_frame.grid_columnconfigure(0, weight=1)
        restore_frame.grid_rowconfigure(0, weight=1)

        # create treeview for backups
        self.backup_tree = ttk.Treeview(restore_frame, columns=('Name', 'Timestamp'), show='headings', height=10)
        self.backup_tree.heading('Name', text='Name')
        self.backup_tree.heading('Timestamp', text='Timestamp')
        self.backup_tree.column('Name', width=200)
        self.backup_tree.column('Timestamp', width=200)
        self.backup_tree.grid(row=0, column=0, pady=5, padx=5, sticky="nsew")
        
        # add scrollbar to treeview
        scrollbar = ttk.Scrollbar(restore_frame, orient="vertical", command=self.backup_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.backup_tree.configure(yscrollcommand=scrollbar.set)
        
        # create buttons frame
        buttons_frame = ttk.Frame(restore_frame)
        buttons_frame.grid(row=1, column=0, columnspan=2, pady=5, padx=5, sticky="ew")
        buttons_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ttk.Button(buttons_frame, text="Restore Selected", command=self.restore_backup).grid(row=0, column=0, padx=5, sticky="ew")
        ttk.Button(buttons_frame, text="Delete Selected", command=self.delete_backup).grid(row=0, column=1, padx=5, sticky="ew")
        ttk.Button(buttons_frame, text="Refresh List", command=self.refresh_backup_list).grid(row=0, column=2, padx=5, sticky="ew")

        # refresh backup list
        self.refresh_backup_list()

    def refresh_backup_list(self):
        # refresh the list of backups in the treeview
        for i in self.backup_tree.get_children():
            self.backup_tree.delete(i)
        
        backup_dir = os.path.join(self.app_data_dir, 'save_backups')
        if os.path.exists(backup_dir):
            backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.save')], reverse=True)
            for backup in backups:
                name_parts = backup.rsplit('_', 1)
                if len(name_parts) == 2:
                    name = name_parts[0].replace('_', ' ')
                    try:
                        timestamp = float(name_parts[1].replace('.save', ''))
                        formatted_time = datetime.datetime.fromtimestamp(timestamp).strftime("%I:%M%p %d/%m/%Y")
                        self.backup_tree.insert('', 'end', values=(name, formatted_time))
                    except ValueError:
                        self.backup_tree.insert('', 'end', values=(backup, 'Unknown'))
                else:
                    self.backup_tree.insert('', 'end', values=(backup, 'Unknown'))
        self.set_status("Backup list refreshed")

    def create_backup(self):
        # create a backup of the current save file
        backup_name = self.backup_name_entry.get().strip()
        if not backup_name:
            messagebox.showerror("Error", "Please enter a backup name.")
            self.set_status("Backup creation failed: No name provided")
            return

        # sanitize the backup name
        invalid_chars = r'<>:"/\|?*'
        sanitized_name = ''.join(c for c in backup_name if c not in invalid_chars)
        sanitized_name = sanitized_name[:255]  # limit to 255 characters

        if not sanitized_name:
            messagebox.showerror("Error", "The backup name contains only invalid characters. Please use a different name.")
            self.set_status("Backup creation failed: Invalid name")
            return

        timestamp = int(time.time())
        backup_filename = f"{sanitized_name.replace(' ', '_')}_{timestamp}.save"

        save_path = os.path.join(os.getenv('APPDATA'), 'Godot', 'app_userdata', 'webfishing_2_newver', 'webfishing_migrated_data.save')
        backup_dir = os.path.join(self.app_data_dir, 'save_backups')
        os.makedirs(backup_dir, exist_ok=True)

        backup_path = os.path.join(backup_dir, backup_filename)

        try:
            shutil.copy2(save_path, backup_path)
            messagebox.showinfo("Success", f"Backup created: {sanitized_name}")
            self.set_status(f"Backup created: {sanitized_name}")
            self.refresh_backup_list()
        except Exception as e:
            error_message = f"Failed to create backup: {str(e)}"
            messagebox.showerror("Error", error_message)
            self.set_status(error_message)
            self.send_to_discord(f"Error creating backup in Hook, Line, & Sinker:\n{error_message}")

    def restore_backup(self):
        # restore a selected backup
        selected = self.backup_tree.selection()
        if not selected:
            messagebox.showerror("Error", "Please select a backup to restore.")
            self.set_status("Backup restoration failed: No backup selected")
            return

        item = self.backup_tree.item(selected[0])
        backup_name = item['values'][0]
        
        backup_dir = os.path.join(self.app_data_dir, 'save_backups')
        matching_backups = [f for f in os.listdir(backup_dir) if f.startswith(backup_name.replace(' ', '_')) and f.endswith('.save')]
        
        if not matching_backups:
            error_message = f"Backup file for '{backup_name}' not found."
            messagebox.showerror("Error", error_message)
            self.set_status(error_message)
            return
        
        backup_filename = matching_backups[0]  # use the first matching backup if multiple exist
        backup_path = os.path.join(backup_dir, backup_filename)

        save_path = os.path.join(os.getenv('APPDATA'), 'Godot', 'app_userdata', 'webfishing_2_newver', 'webfishing_migrated_data.save')

        try:
            # restore the selected backup
            shutil.copy2(backup_path, save_path)
            messagebox.showinfo("Success", f"Backup restored: {backup_name}")
            self.set_status(f"Backup restored: {backup_name}")
            self.refresh_backup_list()
        except Exception as e:
            error_message = f"Failed to restore backup: {str(e)}"
            messagebox.showerror("Error", error_message)
            self.set_status(error_message)
            self.send_to_discord(f"Error restoring backup in Hook, Line, & Sinker:\n{error_message}")

    def delete_backup(self):
        selected = self.backup_tree.selection()
        if not selected:
            messagebox.showerror("Error", "Please select a backup to delete.")
            self.set_status("Backup deletion failed: No backup selected")
            return

        item = self.backup_tree.item(selected[0])
        backup_name = item['values'][0]
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the backup '{backup_name}'?"):
            backup_dir = os.path.join(self.app_data_dir, 'save_backups')
            matching_backups = [f for f in os.listdir(backup_dir) if f.startswith(backup_name.replace(' ', '_')) and f.endswith('.save')]
            
            if not matching_backups:
                error_message = f"Backup file for '{backup_name}' not found."
                messagebox.showerror("Error", error_message)
                self.set_status(error_message)
                return
            
            backup_filename = matching_backups[0]
            backup_path = os.path.join(backup_dir, backup_filename)
            
            try:
                os.remove(backup_path)
                messagebox.showinfo("Success", f"Backup deleted: {backup_name}")
                self.set_status(f"Backup deleted: {backup_name}")
                self.refresh_backup_list()
            except Exception as e:
                error_message = f"Failed to delete backup: {str(e)}"
                messagebox.showerror("Error", error_message)
                self.set_status(error_message)
                self.send_to_discord(f"Error deleting backup in Hook, Line, & Sinker:\n{error_message}")

    # creates the main setup tab for hook line & sinker
    def create_hls_setup_tab(self):
        setup_frame = ttk.Frame(self.notebook)
        self.notebook.add(setup_frame, text="HLS Setup")

        setup_frame.grid_columnconfigure(0, weight=1)
        setup_frame.grid_rowconfigure(8, weight=1)  # increased to accommodate new button

        # title
        title_label = ttk.Label(setup_frame, text="Game Setup Guide", font=("Helvetica", 16, "bold"))
        title_label.grid(row=0, column=0, pady=(20, 5), padx=20, sticky="w")

        # new label for instructions
        instruction_label = ttk.Label(setup_frame, text="You must complete all steps below to use Hook, Line, & Sinker", font=("Helvetica", 10, "italic"))
        instruction_label.grid(row=1, column=0, pady=(0, 10), padx=20, sticky="w")

        # step 1: set game path
        step1_frame = ttk.LabelFrame(setup_frame, text="Step 1: Set Game Installation Path")
        step1_frame.grid(row=2, column=0, pady=10, padx=20, sticky="ew")
        step1_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(step1_frame, text="Path:").grid(row=0, column=0, pady=5, padx=5, sticky="w")
        self.game_path_entry = ttk.Entry(step1_frame, width=40)
        self.game_path_entry.grid(row=0, column=1, pady=5, padx=5, sticky="ew")
        self.game_path_entry.insert(0, self.settings.get('game_path', ''))

        ttk.Button(step1_frame, text="Browse", command=self.browse_game_directory).grid(row=0, column=2, pady=5, padx=5)
        ttk.Button(step1_frame, text="Save Path", command=self.save_game_path).grid(row=0, column=3, pady=5, padx=5)

        self.step1_status = ttk.Label(step1_frame, text="Unverified", foreground="red", font=("Helvetica", 10, "bold"))
        self.step1_status.grid(row=1, column=0, columnspan=4, pady=5, padx=5, sticky="w")

        # step 2: verify installation
        step2_frame = ttk.LabelFrame(setup_frame, text="Step 2: Verify Game Installation")
        step2_frame.grid(row=3, column=0, pady=10, padx=20, sticky="ew")
        step2_frame.grid_columnconfigure(1, weight=1)

        ttk.Button(step2_frame, text="Verify Installation", command=self.verify_installation).grid(row=0, column=0, pady=5, padx=5)
        ttk.Label(step2_frame, text="Checks if the game files are present in the specified path.").grid(row=0, column=1, pady=5, padx=5, sticky="w")

        self.step2_status = ttk.Label(step2_frame, text="Unverified", foreground="red", font=("Helvetica", 10, "bold"))
        self.step2_status.grid(row=1, column=0, columnspan=2, pady=5, padx=5, sticky="w")

        # step 3: install net
        step3_frame = ttk.LabelFrame(setup_frame, text="Step 3: Install .NET")
        step3_frame.grid(row=4, column=0, pady=10, padx=20, sticky="ew")
        step3_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(step3_frame, text="Visit the .NET download page and install the .NET 8.0 SDK:").grid(row=0, column=0, pady=5, padx=5, sticky="w")
        
        dotnet_link = ttk.Label(step3_frame, text=".NET Download Page", foreground="blue", cursor="hand2")
        dotnet_link.grid(row=1, column=0, pady=5, padx=5, sticky="w")
        dotnet_link.bind("<Button-1>", lambda e: webbrowser.open("https://dotnet.microsoft.com/en-us/download"))

        ttk.Label(step3_frame, text="Click the 'Download .NET SDK x64' or 'Download .NET SDK x86' button as appropriate for your system.").grid(row=2, column=0, pady=5, padx=5, sticky="w")
        ttk.Label(step3_frame, text="Note: We cannot automatically verify this step. Please ensure you've completed it before proceeding.").grid(row=3, column=0, pady=5, padx=5, sticky="w")

        # step 4: install/update gdweave
        step4_frame = ttk.LabelFrame(setup_frame, text="Step 4: Install/Update GDWeave")
        step4_frame.grid(row=5, column=0, pady=10, padx=20, sticky="ew")
        step4_frame.grid_columnconfigure(1, weight=1)

        self.gdweave_button = ttk.Button(step4_frame, text="Install GDWeave", command=self.install_gdweave)
        self.gdweave_button.grid(row=0, column=0, pady=5, padx=5)
        self.gdweave_label = ttk.Label(step4_frame, text="Installs or updates GDWeave mod loader. Your mods should transfer over, backup just in case.")
        self.gdweave_label.grid(row=0, column=1, pady=5, padx=5, sticky="w")

        self.step4_status = ttk.Label(step4_frame, text="Uninstalled", foreground="red", font=("Helvetica", 10, "bold"))
        self.step4_status.grid(row=1, column=0, columnspan=2, pady=5, padx=5, sticky="w")

        # setup status
        self.setup_status = ttk.Label(setup_frame, text="", font=("Helvetica", 12))
        self.setup_status.grid(row=6, column=0, pady=(20, 10), padx=20, sticky="w")
        self.update_setup_status()

    # creates the settings tab for hook line & sinker
    def create_settings_tab(self):
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="Settings")

        settings_frame.grid_columnconfigure(0, weight=1)
        settings_frame.grid_rowconfigure(7, weight=1)

        # title
        title_label = ttk.Label(settings_frame, text="Application Settings", font=("Helvetica", 16, "bold"))
        title_label.grid(row=0, column=0, pady=(20, 5), padx=20, sticky="w")

        # subtitle
        subtitle_label = ttk.Label(settings_frame, text="Customize your Hook, Line, & Sinker experience", font=("Helvetica", 10, "italic"))
        subtitle_label.grid(row=1, column=0, pady=(0, 10), padx=20, sticky="w")

        # general settings
        general_frame = ttk.LabelFrame(settings_frame, text="General Settings")
        general_frame.grid(row=2, column=0, pady=10, padx=20, sticky="ew")
        general_frame.grid_columnconfigure(1, weight=1)

        self.auto_update = tk.BooleanVar(value=self.settings.get('auto_update', True))
        ttk.Checkbutton(general_frame, text="Auto-update mods", variable=self.auto_update, command=self.save_settings).grid(row=0, column=0, pady=5, padx=5, sticky="w")
        ttk.Label(general_frame, text="Automatically check for mod updates").grid(row=0, column=1, pady=5, padx=5, sticky="w")
        
        ttk.Button(general_frame, text="Check for Updates", command=self.check_for_updates).grid(row=1, column=0, pady=5, padx=5, sticky="w")
        ttk.Label(general_frame, text="Check for application and mod updates").grid(row=1, column=1, pady=5, padx=5, sticky="w")

        # hook line & sinker information
        info_frame = ttk.LabelFrame(settings_frame, text="Hook, Line, & Sinker Information")
        info_frame.grid(row=3, column=0, pady=10, padx=20, sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)

        # load current version
        current_version = get_version()

        self.current_version_label = ttk.Label(info_frame, text=f"Current Version: {current_version}")
        self.current_version_label.grid(row=0, column=0, pady=5, padx=5, sticky="w")

        self.latest_version_label = ttk.Label(info_frame, text="Latest Version: Checking...")
        self.latest_version_label.grid(row=1, column=0, pady=5, padx=5, sticky="w")

        # credits
        credits_frame = ttk.LabelFrame(settings_frame, text="Credits")
        credits_frame.grid(row=4, column=0, pady=10, padx=20, sticky="ew")
        credits_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(credits_frame, text="• Pyoid for making Hook, Line, & Sinker").grid(row=0, column=0, pady=2, padx=5, sticky="w")
        ttk.Label(credits_frame, text="• NotNite for making GDWeave").grid(row=1, column=0, pady=2, padx=5, sticky="w")
        ttk.Label(credits_frame, text="• All mod makers for their contributions").grid(row=2, column=0, pady=2, padx=5, sticky="w")
        ttk.Label(credits_frame, text="• You for using Hook, Line, & Sinker!").grid(row=3, column=0, pady=2, padx=5, sticky="w")

        # troubleshooting options
        troubleshoot_frame = ttk.LabelFrame(settings_frame, text="Troubleshooting")
        troubleshoot_frame.grid(row=5, column=0, pady=10, padx=20, sticky="ew")
        troubleshoot_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # first row - most important actions
        self.toggle_gdweave_button = ttk.Button(troubleshoot_frame, text="Toggle GDWeave", command=self.toggle_gdweave)
        self.toggle_gdweave_button.grid(row=0, column=0, pady=5, padx=5, sticky="ew")
        ttk.Button(troubleshoot_frame, text="Clear GDWeave Mods", command=self.clear_gdweave_mods).grid(row=0, column=1, pady=5, padx=5, sticky="ew")
        ttk.Button(troubleshoot_frame, text="Clear HLS Mods", command=self.clear_hls_mods).grid(row=0, column=2, pady=5, padx=5, sticky="ew")

        # second row - log and folder access
        ttk.Button(troubleshoot_frame, text="Open GDWeave Log", command=self.open_gdweave_log).grid(row=1, column=0, pady=5, padx=5, sticky="ew")
        ttk.Button(troubleshoot_frame, text="Open HLS Log", command=self.open_latest_log).grid(row=1, column=1, pady=5, padx=5, sticky="ew")
        ttk.Button(troubleshoot_frame, text="Open HLS Folder", command=self.open_hls_folder).grid(row=1, column=2, pady=5, padx=5, sticky="ew")

        # third row - additional options
        ttk.Button(troubleshoot_frame, text="Open GDWeave Folder", command=self.open_gdweave_folder).grid(row=2, column=0, pady=5, padx=5, sticky="ew")
        ttk.Button(troubleshoot_frame, text="Clear Temp Folder", command=self.delete_temp_files).grid(row=2, column=1, pady=5, padx=5, sticky="ew")

        # settings status
        self.settings_status = ttk.Label(settings_frame, text="", font=("Helvetica", 12))
        self.settings_status.grid(row=6, column=0, pady=(10, 20), padx=20, sticky="w")

        # start a thread to check the latest version
        threading.Thread(target=self.update_latest_version_label, daemon=True).start()
        self.root.after(100, self.process_gui_queue)

    # opens the help website in the default browser
    def open_help_website(self):
        webbrowser.open("https://hooklinesinker.lol/help")

    # copies existing gdweave mods to the hls mods directory
    def copy_existing_gdweave_mods(self):
        if not self.settings.get('game_path'):
            logging.info("Game path not set, skipping existing mod copy.")
            return

        gdweave_mods_path = os.path.join(self.settings['game_path'], 'GDWeave', 'Mods')
        if not os.path.exists(gdweave_mods_path):
            logging.info("GDWeave Mods folder not found, skipping existing mod copy.")
            return

        third_party_mods_dir = os.path.join(self.mods_dir, "3rd_party")
        os.makedirs(third_party_mods_dir, exist_ok=True)

        # get the list of known mod ids from our managed mods
        known_mod_ids = set()
        for mod_folder in os.listdir(self.mods_dir):
            mod_info_path = os.path.join(self.mods_dir, mod_folder, 'mod_info.json')
            if os.path.exists(mod_info_path):
                with open(mod_info_path, 'r') as f:
                    mod_info = json.load(f)
                    known_mod_ids.add(mod_info.get('id'))

        newly_installed_mods = []

        for mod_folder in os.listdir(gdweave_mods_path):
            src_mod_path = os.path.join(gdweave_mods_path, mod_folder)
            
            if not os.path.isdir(src_mod_path):
                logging.info(f"Skipped: {mod_folder} (not a directory)")
                continue

            manifest_path = os.path.join(src_mod_path, 'manifest.json')
            if not os.path.exists(manifest_path):
                logging.info(f"Skipped: {mod_folder} (no manifest.json found)")
                continue

            try:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
                
                mod_id = manifest.get('Id')
                mod_title = manifest.get('Name', mod_folder)
                mod_author = manifest.get('Author', 'Unknown')
                mod_description = manifest.get('Description', 'No description provided')
                mod_version = manifest.get('Version', 'Unknown')

                # check if this is a known mod
                if mod_id in known_mod_ids:
                    logging.info(f"Skipped known mod: {mod_title} (ID: {mod_id})")
                    continue

                # if we've reached here it's likely a third-party mod
                dst_mod_path = os.path.join(third_party_mods_dir, mod_id)
                if not os.path.exists(dst_mod_path):
                    shutil.copytree(src_mod_path, dst_mod_path)

                    # create mod_info.json
                    mod_info = {
                        'id': mod_id,
                        'title': mod_title,
                        'author': mod_author,
                        'description': mod_description,
                        'enabled': True,
                        'version': mod_version,
                        'third_party': True
                    }
                    with open(os.path.join(dst_mod_path, 'mod_info.json'), 'w') as f:
                        json.dump(mod_info, f, indent=2)

                    logging.info(f"Copied third-party mod: {mod_title} (ID: {mod_id})")
                    newly_installed_mods.append(mod_info)
                else:
                    logging.info(f"Skipped existing third-party mod: {mod_title} (ID: {mod_id})")

            except Exception as e:
                logging.info(f"Error processing mod {mod_folder}: {str(e)}")
                self.send_to_discord(f"Error in Hook, Line, & Sinker:\n{str(e)}")

        # add newly installed mods to the installed mods list
        self.installed_mods.extend(newly_installed_mods)

        self.refresh_mod_lists()

    # deletes temporary files and folders
    def delete_temp_files(self):
        temp_dir = os.path.join(os.getenv('APPDATA'), 'HookLineSinker', 'temp')
        if os.path.exists(temp_dir):
            try:
                # use os.walk to iterate through all directories and files
                for root, dirs, files in os.walk(temp_dir, topdown=False):
                    for name in files:
                        file_path = os.path.join(root, name)
                        os.chmod(file_path, stat.S_IWRITE)
                        os.remove(file_path)
                    for name in dirs:
                        dir_path = os.path.join(root, name)
                        os.chmod(dir_path, stat.S_IWRITE)
                        os.rmdir(dir_path)
                
                # remove the main directory
                os.chmod(temp_dir, stat.S_IWRITE)
                os.rmdir(temp_dir)
                
                logging.info(f"Successfully deleted temporary directory: {temp_dir}")
                self.set_status("Temporary files and folders deleted successfully.")
            except Exception as e:
                error_message = f"Failed to delete temporary files and folders: {str(e)}"
                logging.error(error_message)
                self.set_status(error_message)
                self.send_to_discord(f"Error in Hook, Line, & Sinker:\n{error_message}")
        else:
            logging.info(f"Temporary directory does not exist: {temp_dir}")
            self.set_status("No temporary files or folders to delete.")

    # verifies that net is installed and working correctly    
    def verify_dotnet(self):
        try:
            subprocess.run(["dotnet", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.set_status(".NET is installed and working correctly.")
        except Exception as e:
            error_message = "Please install the .NET 8.0 SDK. Visit https://dotnet.microsoft.com/download"
            self.set_status(error_message)
            messagebox.showerror("Installation Error", error_message)
            self.send_to_discord(f"Error in Hook, Line, & Sinker:\n{str(e)}")

    # downloads and runs the net installer
    def download_and_run_dotnet_installer(self):
        self.set_status("Downloading .NET installer...")
        messagebox.showinfo("Downloading .NET", "This will download the .NET 8.0 SDK installer. Please wait 10-20 seconds.")
        
        if not sys.platform.startswith('win'):
            messagebox.showerror("Unsupported OS", "Your operating system is not supported for automatic .NET installation.")
            return
        
        url = "https://download.visualstudio.microsoft.com/download/pr/6224f00f-08da-4e7f-85b1-00d42c2bb3d3/b775de636b91e023574a0bbc291f705a/dotnet-sdk-8.0.403-win-x64.exe"
        
        def download_and_install():
            try:
                # create temp directory in appdata
                temp_dir = os.path.join(os.getenv('APPDATA'), 'HookLineSinker', 'temp')
                os.makedirs(temp_dir, exist_ok=True)
                
                # download the installer
                with requests.get(url, stream=True) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get('content-length', 0))
                    
                    # create a temporary file to store the installer
                    temp_file_path = os.path.join(temp_dir, 'dotnet_installer.exe')
                    with open(temp_file_path, 'wb') as temp_file:
                        downloaded_size = 0
                        chunk_size = 8192
                        
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                temp_file.write(chunk)
                                downloaded_size += len(chunk)
                                self.root.update_idletasks()
                
                self.set_status("Download complete.")

                # run the installer without quiet mode on windows
                subprocess.Popen([temp_file_path, '/norestart'])
                self.set_status("Installer launched. Please follow the installation prompts.")
                messagebox.showinfo("Installation Started", "The .NET installer has been launched. Please follow the installation prompts. After installation, please restart Hook, Line, & Sinker.")

            except Exception as e:
                error_message = f"Failed to download or install .NET: {str(e)}"
                self.set_status(error_message)
                messagebox.showerror("Installation Error", error_message)
                self.send_to_discord(f"Error downloading .NET in Hook, Line, & Sinker:\n{error_message}")

            finally:
                # clean up the temporary file
                if 'temp_file_path' in locals():
                    try:
                        os.unlink(temp_file_path)
                    except Exception:
                        pass

        # start the download and installation process in a separate thread
        threading.Thread(target=download_and_install, daemon=True).start()

    # imports a zip mod file
    def import_zip_mod(self):
        zip_path = filedialog.askopenfilename(filetypes=[("ZIP files", "*.zip")])
        if not zip_path:
            logging.info("No ZIP file selected.")
            return

        logging.info(f"Selected ZIP file: {zip_path}")

        # create a dedicated temp folder if it doesn't exist
        temp_dir = os.path.join(self.app_data_dir, 'temp')
        os.makedirs(temp_dir, exist_ok=True)

        # create a unique subfolder for this import operation
        import_temp_dir = os.path.join(temp_dir, f"import_{int(time.time())}")
        os.makedirs(import_temp_dir)
        logging.info(f"Created import temp directory: {import_temp_dir}")

        # create an 'extractedzip' folder inside the import folder
        extracted_zip_dir = os.path.join(import_temp_dir, 'extractedzip')
        os.makedirs(extracted_zip_dir)
        logging.info(f"Created extractedzip directory: {extracted_zip_dir}")

        try:
            # extract the zip contents to the extractedzip directory
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                logging.info(f"ZIP file opened successfully: {zip_path}")
                zip_ref.extractall(extracted_zip_dir)
                logging.info(f"ZIP contents extracted to: {extracted_zip_dir}")
            
            # log the contents of the extracted directory
            logging.info(f"Contents of {extracted_zip_dir}:")
            for root, dirs, files in os.walk(extracted_zip_dir):
                for file in files:
                    logging.info(os.path.join(root, file))

            # find the manifest.json file
            manifest_path = self.find_manifest(extracted_zip_dir)
            
            if not manifest_path:
                error_msg = "manifest.json not found in the ZIP file. This may not be a valid mod package."
                logging.error(error_msg)
                messagebox.showerror("Error", error_msg)
                return

            logging.info(f"Found manifest.json at: {manifest_path}")

            # read the manifest to get the mod id and other information
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            mod_id = manifest.get('Id')
            if not mod_id:
                error_msg = "Id not found in manifest.json. This may not be a valid mod package."
                logging.error(error_msg)
                messagebox.showerror("Error", error_msg)
                return

            logging.info(f"Mod ID from manifest: {mod_id}")

            # check if a mod with this id already exists
            if self.mod_id_exists(mod_id):
                messagebox.showwarning("Mod Conflict", f"A mod with ID '{mod_id}' already exists. You must uninstall the existing mod before importing a new mod with the same ID.")
                return

            # prepare the final mod directory
            mod_dir = os.path.join(self.mods_dir, "3rd_party", mod_id)
            logging.info(f"Final mod directory: {mod_dir}")

            if os.path.exists(mod_dir):
                logging.info(f"Removing existing mod directory: {mod_dir}")
                shutil.rmtree(mod_dir)

            # move the mod files to the final directory
            manifest_parent = os.path.dirname(manifest_path)
            logging.info(f"Manifest parent directory: {manifest_parent}")
            logging.info(f"Extracted ZIP directory: {extracted_zip_dir}")

            if manifest_parent != extracted_zip_dir:
                # the mod is already in a subfolder just move it
                logging.info(f"Moving {manifest_parent} to {mod_dir}")
                shutil.move(manifest_parent, mod_dir)
            else:
                # the mod is not in a subfolder create one and move all files into it
                logging.info(f"Moving contents of {extracted_zip_dir} to {mod_dir}")
                shutil.move(extracted_zip_dir, mod_dir)

            logging.info(f"Contents of final mod directory {mod_dir}:")
            for root, dirs, files in os.walk(mod_dir):
                for file in files:
                    logging.info(os.path.join(root, file))

            # create mod_info.json
            mod_info = {
                'id': mod_id,
                'title': manifest.get('Name', mod_id),
                'author': manifest.get('Author', 'Unknown'),
                'description': manifest.get('Description', ''),
                'version': manifest.get('Version', 'Unknown'),
                'enabled': True,
                'third_party': True
            }

            mod_info_path = os.path.join(mod_dir, 'mod_info.json')
            with open(mod_info_path, 'w') as f:
                json.dump(mod_info, f, indent=2)
            logging.info(f"Created mod_info.json at {mod_info_path}")

            # log the entire mod_info dictionary
            logging.info(f"mod_info to be sent to copy_mod_to_game:")
            for key, value in mod_info.items():
                logging.info(f"  {key}: {value}")

            # log the contents of the mod directory before copying
            logging.info(f"Contents of mod directory before copying:")
            for root, dirs, files in os.walk(mod_dir):
                for file in files:
                    logging.info(os.path.join(root, file))

            self.set_status(f"3rd party mod '{mod_info['title']}' imported successfully!")
            self.refresh_mod_lists()

            # log that we're about to call copy_mod_to_game
            logging.info(f"Calling copy_mod_to_game with mod_info for '{mod_info['title']}'")
            self.copy_mod_to_game(mod_info)

            # log after copy_mod_to_game has been called
            logging.info(f"Returned from copy_mod_to_game for '{mod_info['title']}'")

            # check if the mod is still in the directory after copying
            logging.info(f"Contents of mod directory after copying:")
            for root, dirs, files in os.walk(mod_dir):
                for file in files:
                    logging.info(os.path.join(root, file))

        except Exception as e:
            error_message = f"Failed to import mod: {str(e)}"
            logging.error(error_message)
            logging.error(traceback.format_exc())  # This will log the full traceback
            self.set_status(error_message)
            self.send_to_discord(f"Error importing 3rd party mod in Hook, Line, & Sinker:\n{error_message}")

    # searches for manifest.json file in a given directory and its subdirectories
    def find_manifest(self, directory):
        for root, dirs, files in os.walk(directory):
            if 'manifest.json' in files:
                return os.path.join(root, 'manifest.json')
        return None
    
    # refreshes all mods by reloading available mods and updating the UI
    def refresh_all_mods(self):
        self.load_available_mods()
        self.refresh_mod_lists()
        self.set_status("All mods refreshed")
        
    # fetches the latest version of GDWeave from GitHub
    # uses a separate thread with a timeout to prevent hanging
    def get_gdweave_version(self):
        def fetch_version():
            try:
                api_url = "https://api.github.com/repos/NotNite/GDWeave/releases/latest"
                response = requests.get(api_url)
                response.raise_for_status()
                data = json.loads(response.text)
                return data['tag_name']
            except Exception as e:
                logging.info(f"Error fetching GDWeave version: {str(e)}")
                self.send_to_discord(f"Error getting GDWeave version in Hook, Line, & Sinker:\n{str(e)}")
                return "Unknown"

        result = None
        def run_fetch():
            nonlocal result
            result = fetch_version()

        thread = threading.Thread(target=run_fetch, daemon=True)
        thread.start()
        thread.join(timeout=10)  # wait for up to 10 seconds

        if thread.is_alive():
            logging.info("Timeout occurred while fetching GDWeave version")
            return "0"
        else:
            return result if result is not None else "Unknown"
        
    # installs selected mods from the available mods list
    # handles conflicts with existing mods and third-party mods
    def install_mod(self):
        if not self.check_setup():
            return
        if not self.check_game_not_running():
            return
        
        selected = self.available_listbox.curselection()
        if selected:
            for index in selected:
                mod_title = self.available_listbox.get(index)
                logging.info(f"Attempting to install mod: {mod_title}")
                if mod_title.startswith("Category:"):
                    logging.info("Skipping category")
                    continue  # skip category separators
                
                # clean the mod title by removing spaces, emojis, and [3rd] tag
                clean_title = mod_title.replace('✅', '').replace('❌', '').replace('[3rd]', '').strip()
                logging.info(f"Cleaned mod title: {clean_title}")
                
                mod = next((m for m in self.available_mods if m['title'].strip() == clean_title), None)
                if mod is None:
                    logging.error(f"No mod found with title: {clean_title}")
                    continue  # skip if mod not found

                self.set_status(f"Downloading mod: {mod['title']}")
                try:
                    # download and get the full mod info
                    downloaded_mod = self.download_and_install_mod(mod, install=False)
                    
                    if downloaded_mod is None:
                        self.set_status(f"Failed to download mod: {mod['title']}")
                        logging.error(f"Failed to download mod: {mod['title']}")
                        continue
                    
                    # check if a mod with this ID already exists
                    existing_mod = self.find_installed_mod_by_id(downloaded_mod['id'])
                    if existing_mod:
                        if existing_mod.get('third_party', False):
                            messagebox.showwarning("Mod Conflict", f"A third-party mod with ID '{downloaded_mod['id']}' already exists. You must uninstall the existing mod before installing a new mod with the same ID.")
                            self.set_status(f"Mod conflict: {downloaded_mod['title']}")
                            logging.info(f"Mod conflict: {downloaded_mod['title']}")
                            continue
                        else:
                            self.uninstall_mod_files(existing_mod)
                            logging.info(f"Uninstalled existing mod: {existing_mod['id']}")

                    # if we've reached here, we can safely install the mod
                    self.set_status(f"Installing mod: {downloaded_mod['title']}")
                    self.install_downloaded_mod(downloaded_mod)
                    
                except Exception as e:
                    error_message = f"Failed to install mod {mod['title']}: {str(e)}"
                    self.set_status(error_message)
                    logging.error(error_message)
                    self.send_to_discord(f"Error installing mod in Hook, Line, & Sinker:\n{error_message}")
            self.refresh_mod_lists()
        else:
            logging.info("No mod selected for installation")
            self.set_status("Please select a mod to install")

    # searches for an installed mod by its ID
    # checks both regular and third-party mods
    def find_installed_mod_by_id(self, mod_id):
        # check regular mods
        for mod in self.installed_mods:
            if mod['id'] == mod_id:
                return mod
        
            # check third-party mods
            third_party_dir = os.path.join(self.mods_dir, "3rd_party")
            if os.path.exists(third_party_dir):
                for mod_folder in os.listdir(third_party_dir):
                    mod_info_path = os.path.join(third_party_dir, mod_folder, 'mod_info.json')
                    if os.path.exists(mod_info_path):
                        with open(mod_info_path, 'r') as f:
                            mod_info = json.load(f)
                            if mod_info['id'] == mod_id:
                                return mod_info
            return None
        
        # check third-party mods
        third_party_dir = os.path.join(self.mods_dir, "3rd_party")
        if os.path.exists(third_party_dir):
            for mod_folder in os.listdir(third_party_dir):
                mod_info_path = os.path.join(third_party_dir, mod_folder, 'mod_info.json')
                if os.path.exists(mod_info_path):
                    with open(mod_info_path, 'r') as f:
                        mod_info = json.load(f)
                        if mod_info['id'] == mod_id:
                            return mod_info
        return None

    # installs or updates GDWeave mod loader
    # backs up existing mods and configs before installation
    def install_gdweave(self):
        if not self.settings.get('game_path'):
            self.set_status("Please set the game path first")
            return
        if not self.check_game_not_running():
            return

        gdweave_url = "https://github.com/NotNite/GDWeave/releases/latest/download/GDWeave.zip"
        game_path = self.settings['game_path']
        gdweave_path = os.path.join(game_path, 'GDWeave')

        try:
            # create a temporary directory for backup in appdata
            temp_dir = os.path.join(os.getenv('APPDATA'), 'HookLineSinker', 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            temp_backup_dir = os.path.join(temp_dir, f'gdweave_backup_{int(time.time())}')
            os.makedirs(temp_backup_dir, exist_ok=True)

            # backup existing mods and configs
            mods_path = os.path.join(gdweave_path, 'Mods')
            configs_path = os.path.join(gdweave_path, 'configs')
            
            if os.path.exists(mods_path):
                shutil.copytree(mods_path, os.path.join(temp_backup_dir, 'Mods'))
                logging.info("Backed up Mods folder")
            
            if os.path.exists(configs_path):
                shutil.copytree(configs_path, os.path.join(temp_backup_dir, 'configs'))
                logging.info("Backed up configs folder")

            # download and install GDWeave
            self.set_status("Downloading GDWeave...")
            response = requests.get(gdweave_url)
            response.raise_for_status()
            
            zip_path = os.path.join(temp_dir, "GDWeave.zip")
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            self.set_status("Installing GDWeave...")
            logging.info(f"Zip file downloaded to: {zip_path}")
            
            # extract the zip file
            extract_path = os.path.join(temp_dir, "GDWeave_extract")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            logging.info(f"Zip file extracted to: {extract_path}")
            
            # remove existing GDWeave folder if it exists
            if os.path.exists(gdweave_path):
                logging.info(f"Removing existing GDWeave folder: {gdweave_path}")
                shutil.rmtree(gdweave_path)
            
            # move the extracted GDWeave folder to the correct location
            extracted_gdweave_path = os.path.join(extract_path, 'GDWeave')
            logging.info(f"Moving {extracted_gdweave_path} to {gdweave_path}")
            shutil.move(extracted_gdweave_path, gdweave_path)
            
            # copy winmm.dll to the game directory on Windows
            if sys.platform.startswith('win'):
                winmm_src = os.path.join(extract_path, 'winmm.dll')
                winmm_dst = os.path.join(game_path, 'winmm.dll')
                logging.info(f"Copying {winmm_src} to {winmm_dst}")
                shutil.copy2(winmm_src, winmm_dst)
            
            # restore mods and configs from backup
            if os.path.exists(os.path.join(temp_backup_dir, 'Mods')):
                shutil.copytree(os.path.join(temp_backup_dir, 'Mods'), os.path.join(gdweave_path, 'Mods'), dirs_exist_ok=True)
                logging.info("Restored Mods folder")
            
            if os.path.exists(os.path.join(temp_backup_dir, 'configs')):
                shutil.copytree(os.path.join(temp_backup_dir, 'configs'), os.path.join(gdweave_path, 'configs'), dirs_exist_ok=True)
                logging.info("Restored configs folder")

            self.settings['gdweave_version'] = self.get_gdweave_version()
            self.save_settings()
            self.set_status(f"GDWeave {self.settings['gdweave_version']} installed/updated successfully")
            self.update_setup_status()
            self.update_toggle_gdweave_button()
            logging.info("GDWeave installed/updated successfully!")

        except Exception as e:
            error_message = f"Failed to install/update GDWeave: {str(e)}"
            self.set_status(error_message)
            logging.info(error_message)
            logging.info(f"Error details: {traceback.format_exc()}")
            self.send_to_discord(f"Error installing/updating GDWeave in Hook, Line, & Sinker:\n{error_message}")

        self.refresh_mod_lists()
    # updates the UI to reflect the current setup status
    def update_setup_status(self):
        # update step statuses
        self.update_step1_status()
        self.update_step2_status()
        self.update_step4_status()

        # update GDWeave button text
        if self.is_gdweave_installed():
            self.gdweave_button.config(text="Update GDWeave")
            self.gdweave_label.config(text="Updates GDWeave mod loader to the latest version. Will preserve your mods.")
        else:
            self.gdweave_button.config(text="Install GDWeave")
            self.gdweave_label.config(text="Installs GDWeave mod loader. Required for mod functionality.")


    # updates the text on the toggle GDWeave button
    def update_toggle_gdweave_button(self):
        if hasattr(self, 'toggle_gdweave_button'):
            new_label = self.get_initial_gdweave_label()
            self.toggle_gdweave_button.config(text=new_label)

    # determines the initial label for the GDWeave toggle button
    def get_initial_gdweave_label(self):
        if not self.settings.get('game_path'):
            return "Toggle GDWeave"
        
        gdweave_game_path = os.path.join(self.settings['game_path'], 'GDWeave')
        winmm_game_path = os.path.join(self.settings['game_path'], 'winmm.dll')
        
        if os.path.exists(gdweave_game_path) or os.path.exists(winmm_game_path):
            return "Disable GDWeave"
        else:
            return "Enable GDWeave"
            
    # checks if GDWeave is currently enabled
    def is_gdweave_enabled(self):
        if not self.settings.get('game_path'):
            return False
        game_path = self.settings['game_path']
        gdweave_game_path = os.path.join(game_path, 'GDWeave')
        if sys.platform.startswith('win'):
            return os.path.exists(gdweave_game_path) or os.path.exists(os.path.join(game_path, 'winmm.dll'))
        elif sys.platform.startswith('linux'):
            return os.path.exists(gdweave_game_path) or os.path.exists(os.path.join(game_path, 'run_game_with_gdweave.sh'))
        return False

    # updates the status of step 1 in the setup process
    def update_step1_status(self):
        if self.settings.get('game_path') and os.path.exists(self.settings['game_path']):
            self.step1_status.config(text="Verified", foreground="green")
        else:
            self.step1_status.config(text="Unverified", foreground="red")

    # updates the status of step 2 in the setup process
    def update_step2_status(self):
        if self.settings.get('game_path'):
            exe_path = os.path.join(self.settings['game_path'], 'webfishing.exe' if sys.platform.startswith('win') else 'webfishing.x86_64')
            if os.path.isfile(exe_path):
                self.step2_status.config(text="Verified", foreground="green")
            else:
                self.step2_status.config(text="Unverified", foreground="red")
        else:
            self.step2_status.config(text="Unverified", foreground="red")

    # updates the status of step 4 in the setup process
    def update_step4_status(self):
        try:
            if self.is_gdweave_installed():
                current_version = self.settings.get('gdweave_version', 'Unknown')
                latest_version = self.get_gdweave_version()
                if current_version == latest_version:
                    self.step4_status.config(text="Up to Date", foreground="green")
                else:
                    self.step4_status.config(text="Out of Date", foreground="orange")
            else:
                backup_path = os.path.join(self.app_data_dir, 'GDWeave_Backup')
                if os.path.exists(backup_path):
                    self.step4_status.config(text="Disabled (Backup Available)", foreground="orange")
                else:
                    self.step4_status.config(text="Uninstalled", foreground="red")
        except Exception as e:
            self.step4_status.config(text=f"Error: {str(e)}", foreground="red")

    # checks if the setup process is complete
    def is_setup_complete(self):
        return (
            self.settings.get('game_path') and
            os.path.exists(self.settings['game_path']) and
            self.check_dotnet(silent=True) and
            (self.is_gdweave_installed() or self.settings.get('gdweave_version'))
        )

    # checks if GDWeave is installed
    def is_gdweave_installed(self):
        if not self.settings.get('game_path'):
            return False
        gdweave_path = os.path.join(self.settings['game_path'], 'GDWeave')
        return os.path.exists(gdweave_path)
    
    # checks if .NET is installed on the system
    def check_dotnet(self, silent=False):
        try:
            subprocess.run(["dotnet", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if not silent:
                self.set_status(".NET is installed")
            return True
        except Exception as e:
            if not silent:
                self.set_status(f"Error: {str(e)}. .NET is not installed. Please install .NET 8.0 SDK from https://dotnet.microsoft.com/download")
                self.send_to_discord(f"Error checking .NET in Hook, Line, & Sinker:\n{str(e)}")
            return False

    # opens the .NET download page in the default web browser
    def open_dotnet_download(self):
       webbrowser.open("https://dotnet.microsoft.com/download")

    # creates the help tab in the UI
    def create_help_tab(self):
        help_frame = ttk.Frame(self.notebook)
        self.notebook.add(help_frame, text="Troubleshooting")

        help_frame.grid_columnconfigure(0, weight=1)
        help_frame.grid_rowconfigure(2, weight=1)

        # title
        title_label = ttk.Label(help_frame, text="Troubleshooting Guide", font=("Helvetica", 16, "bold"))
        title_label.grid(row=0, column=0, pady=(20, 5), padx=20, sticky="w")

        # new subtitle
        subtitle_label = ttk.Label(help_frame, text="If you're experiencing any problems, please try all these steps first", font=("Helvetica", 10, "italic"))
        subtitle_label.grid(row=1, column=0, pady=(0, 10), padx=20, sticky="w")

        # create a canvas with a scrollbar
        canvas = tk.Canvas(help_frame)
        scrollbar = ttk.Scrollbar(help_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=2, column=0, sticky="nsew", padx=20, pady=10)
        scrollbar.grid(row=2, column=1, sticky="ns")

        # enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        help_frame.grid_rowconfigure(2, weight=1)

        # help content
        help_items = [
            ("1. Install .NET 8.0 SDK Manually", "If you're having issues with .NET:\n- Visit the .NET Download Page\n- Download and install the .NET 8.0 SDK", "https://dotnet.microsoft.com/download"),
            ("2. Install GDWeave Manually", "If automatic GDWeave installation fails:\n- Go to GDWeave Releases\n- Download the latest GDWeave.zip\n- Extract it to your WEBFISHING game directory", "https://github.com/NotNite/GDWeave/releases"),
            ("3. Installing External Mods", "For mods not listed in our repository:\n- Use the 'Import ZIP Mod' feature in the Mod Manager tab\n- Select the .zip file of the mod you want to install\n- The mod will be automatically imported and installed", None),
            ("4. Run as Administrator (Windows)", "If you're having permission issues on Windows:\n- Right-click on Hook, Line, & Sinker executable\n- Select 'Run as administrator'", None),
            ("5. Verify Game Files", "If mods aren't working:\n- Verify your game files through Steam\n- Reinstall GDWeave", None),
            ("6. Check Antivirus Software", "Your antivirus might be blocking Hook, Line, & Sinker or mods:\n- Add an exception for the Hook, Line, & Sinker directory\n- Add an exception for your WEBFISHING game directory", None),
            ("7. Linux-Specific Issues", "If you're on Linux and having problems:\n- Ensure you have the necessary dependencies installed (e.g., mono-complete)\n- Check if you need to run the game with a specific command or script\n- Make sure you have the required permissions to access game files", None)
        ]

        for i, (title, content, link) in enumerate(help_items):
            item_frame = ttk.Frame(scrollable_frame)
            item_frame.grid(row=i, column=0, sticky="ew", padx=10, pady=5)
            item_frame.grid_columnconfigure(0, weight=1)

            ttk.Label(item_frame, text=title, font=("Helvetica", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(5, 2))
            ttk.Label(item_frame, text=content, wraplength=500, justify="left").grid(row=1, column=0, sticky="w", padx=20)
            
            if link:
                ttk.Button(item_frame, text="Open Link", command=lambda url=link: webbrowser.open(url)).grid(row=2, column=0, sticky="w", padx=20, pady=(5, 0))

        # need more help section
        more_help_frame = ttk.Frame(scrollable_frame)
        more_help_frame.grid(row=len(help_items), column=0, sticky="ew", padx=10, pady=20)
        more_help_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(more_help_frame, text="Need More Help?", font=("Helvetica", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(5, 2))
        ttk.Label(more_help_frame, text="Visit our website for more information and updates.", wraplength=500, justify="left").grid(row=1, column=0, sticky="w", padx=20)

        # contact information
        contact_info = "If you're still having issues, please contact me:\n- Discord: @pyoid\n- Reddit: u/pyoid_loves_cats"
        ttk.Label(more_help_frame, text=contact_info, wraplength=500, justify="left").grid(row=2, column=0, sticky="w", padx=20, pady=(10, 0))

        # website button
        website_button = ttk.Button(help_frame, text="Visit Our Website", command=lambda: webbrowser.open("https://hooklinesinker.lol/"))
        website_button.grid(row=3, column=0, pady=(0, 20), padx=20, sticky="w")

    # makes links in a label clickable
    def make_links_clickable(self, label):
        text = label.cget("text")
        links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', text)
        for link_text, url in links:
            text = text.replace(f'[{link_text}]({url})', link_text)
        label.config(text=text)
        
        def open_link(event):
            for link_text, url in links:
                if link_text in event.widget.cget("text"):
                    webbrowser.open(url)
                    break
        
        label.bind("<Button-1>", open_link)
        label.config(cursor="hand2", foreground="blue")

    # opens the Hook, Line, & Sinker folder
    def open_hls_folder(self):
        if sys.platform.startswith('win'):
            os.startfile(self.app_data_dir)
        elif sys.platform.startswith('linux'):
            subprocess.Popen(['xdg-open', self.app_data_dir])
        else:
            messagebox.showerror("Error", "Unsupported operating system")

    # opens the GDWeave folder
    def open_gdweave_folder(self):
        gdweave_path = os.path.join(self.settings['game_path'], 'GDWeave')
        if os.path.exists(gdweave_path):
            if sys.platform.startswith('win'):
                os.startfile(gdweave_path)
            elif sys.platform.startswith('linux'):
                subprocess.Popen(['xdg-open', gdweave_path])
            else:
                messagebox.showerror("Error", "Unsupported operating system")
        else:
            messagebox.showerror("Error", "GDWeave folder not found. Make sure GDWeave is installed.")

    # opens the GDWeave log file
    def open_gdweave_log(self):
        log_path = os.path.join(self.settings['game_path'], 'GDWeave', 'GDWeave.log')
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                log_content = f.read()
            
            log_window = tk.Toplevel(self.root)
            log_window.title("GDWeave Log")
            log_window.geometry("800x600")

            log_text = tk.Text(log_window, wrap=tk.WORD)
            log_text.pack(expand=True, fill='both')
            log_text.insert(tk.END, log_content)
            log_text.config(state='disabled')

            scrollbar = ttk.Scrollbar(log_text)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            log_text.config(yscrollcommand=scrollbar.set)
            scrollbar.config(command=log_text.yview)

            copy_button = ttk.Button(log_window, text="Copy to Clipboard", command=lambda: self.copy_to_clipboard(log_content))
            copy_button.pack(pady=10)
        else:
            messagebox.showerror("Error", "GDWeave log file not found. Make sure GDWeave is installed and has been run at least once.")

    # copies content to clipboard
    def copy_to_clipboard(self, content):
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        messagebox.showinfo("Success", "Log content copied to clipboard!")

    # removes all mods from the game's mods folder
    def clear_gdweave_mods(self):
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to remove all mods from the game's mods folder? This action cannot be undone."):
            gdweave_mods_path = os.path.join(self.settings['game_path'], 'GDWeave', 'Mods')
            if os.path.exists(gdweave_mods_path):
                try:
                    for item in os.listdir(gdweave_mods_path):
                        item_path = os.path.join(gdweave_mods_path, item)
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                    self.set_status("All mods have been removed from the game's mods folder.")
                except Exception as e:
                    self.set_status(f"Error clearing GDWeave mods: {str(e)}")
                    self.send_to_discord(f"Error clearing GDWeave mods in Hook, Line, & Sinker:\n{str(e)}")
            else:
                self.set_status("GDWeave mods folder not found.")

    # removes all mods managed by hook line & sinker
    def clear_hls_mods(self):
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to remove all mods managed by Hook, Line, & Sinker? This action cannot be undone."):
            try:
                # clear mods in appdata
                for item in os.listdir(self.mods_dir):
                    item_path = os.path.join(self.mods_dir, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                
                # clear mod cache
                self.mod_cache = {}
                self.save_mod_cache()
                
                # refresh mod lists
                self.refresh_mod_lists()
                
                self.set_status("All Hook, Line, & Sinker managed mods and cache have been cleared.")
            except Exception as e:
                self.set_status(f"Error clearing HLS mods: {str(e)}")
                self.send_to_discord(f"Error clearing HLS mods in Hook, Line, & Sinker:\n{str(e)}")

    # fetches the latest version from the server
    def update_latest_version_label(self):
        try:
            response = requests.get("https://hooklinesinker.lol/download/version.json")
            latest_version = response.json()['version']
            self.gui_queue.put(('latest_version', latest_version))
        except Exception as e:
            logging.info(f"Error fetching latest version: {str(e)}")
            self.gui_queue.put(('latest_version', 'Unknown'))
            self.send_to_discord(f"Error fetching latest version in Hook, Line, & Sinker:\n{str(e)}")

    # processes messages in the gui queue
    def process_gui_queue(self):
        try:
            while True:
                message = self.gui_queue.get_nowait()
                if message[0] == 'latest_version':
                    self.latest_version_label.config(text=f"Latest Version: {message[1]}")
        except queue.Empty:
            pass
        finally:
            # schedule the next queue check
            self.root.after(100, self.process_gui_queue)

    # checks for program updates and prompts user to update if available
    def check_for_program_updates(self, silent=False):
        try:
            response = requests.get("https://hooklinesinker.lol/download/version.json")
            version_data = response.json()
            remote_version = version_data['version']
            update_message = version_data.get('message', '')

            local_version = get_version()

            self.current_version_label.config(text=f"Current Version: {local_version}")
            self.latest_version_label.config(text=f"Latest Version: {remote_version}")

            if remote_version != local_version:
                if silent:
                    self.update_application(remote_version)
                    return True
                else:
                    message = f"A new version ({remote_version}) is available. You are currently on version {local_version}."
                    if update_message:
                        message += f"\n\n{update_message}"
                    message += "\n\nWould you like to update now?"
                    
                    if messagebox.askyesno("Update Available", message):
                        self.update_application(remote_version)
                        return True
            elif not silent:
                logging.info("up to date, leaving here just in case")
            return False
        except Exception as e:
            logging.info(f"Error checking for updates: {str(e)}")
            return False

    # downloads and installs the new version of the application
    def update_application(self, new_version):
        def download_and_install():
            try:
                # download the new version
                url = f"https://hooklinesinker.lol/download/{new_version}"
                response = requests.get(url, stream=True, allow_redirects=True)
                response.raise_for_status()

                # create a temporary directory in appdata
                temp_dir = os.path.join(os.getenv('APPDATA'), 'HookLineSinker', 'temp')
                os.makedirs(temp_dir, exist_ok=True)
                installer_path = os.path.join(temp_dir, f"HookLineSinker-Setup-{new_version}.exe")
                
                with open(installer_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                # run the installer
                if sys.platform.startswith('win'):
                    subprocess.Popen([installer_path])
                else:
                    self.root.after(0, lambda: messagebox.showinfo("Update Downloaded", 
                        f"The update has been downloaded to {installer_path}. Please install it manually."))
                    
                # save the new version to the config
                self.settings['last_update_version'] = new_version
                self.save_settings()

                # inform the user and close the current instance
                self.root.after(0, lambda: messagebox.showinfo("Update in Progress", "The update is being installed. Please restart the application to use the new version."))
                self.root.after(0, self.root.quit)

            except Exception as e:
                error_message = f"Failed to update: {str(e)}"
                self.root.after(0, lambda: messagebox.showerror("Update Failed", error_message))
                self.root.after(0, lambda: self.set_status(error_message))
                self.send_to_discord(f"Error updating Hook, Line, & Sinker:\n{error_message}")

        # start the download and installation process in a separate thread
        threading.Thread(target=download_and_install, daemon=True).start()

    # creates and configures the status bar
    def create_status_bar(self):
        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # updates the status bar with a new message
    def set_status(self, message):
        self.status_bar.config(text=message)
        self.root.update_idletasks()

    # clears placeholder text when entry widget is clicked
    def clear_placeholder(self, event, placeholder):
        if event.widget.get() == placeholder:
            event.widget.delete(0, tk.END)

    # restores placeholder text if entry widget is empty
    def restore_placeholder(self, event, placeholder):
        if event.widget.get() == "":
            event.widget.insert(0, placeholder)

    # filters available mods based on search term
    def search_available_mods(self, event):
        search_term = self.available_search.get().lower()
        self.available_listbox.delete(0, tk.END)
        
        visible_categories = set()
        for mod in self.available_mods:
            if search_term in mod['title'].lower():
                category = self.mod_categories.get(mod['title'], "Uncategorized")
                visible_categories.add(category)
        
        for category in sorted(visible_categories):
            self.available_listbox.insert(tk.END, f"-- Category: {category} --")
            self.available_listbox.itemconfig(tk.END, {'bg':'lightgray', 'fg':'black'})
            for mod in self.available_mods:
                if self.mod_categories.get(mod['title'], "Uncategorized") == category and search_term in mod['title'].lower():
                    self.available_listbox.insert(tk.END, mod['title'])

    # filters installed mods based on search term
    def search_installed_mods(self, event):
        search_term = self.installed_search.get().lower()
        self.installed_listbox.delete(0, tk.END)
        for mod in self.installed_mods:
            if search_term in mod['title'].lower():
                self.installed_listbox.insert(tk.END, mod['title'])
                self.update_mod_status_in_listbox(mod)

    # opens a window to edit the configuration of a selected mod
    def edit_mod_config(self):
        selected = self.installed_listbox.curselection()
        if not selected:
            messagebox.showinfo("No Mod Selected", "Please select a mod to edit its configuration.")
            return

        mod = self.installed_mods[selected[0]]
        config_path = os.path.join(self.settings['game_path'], 'GDWeave', 'configs', f"{mod['title']}.json")

        if not os.path.exists(config_path):
            messagebox.showinfo("No Config Found", f"{mod['title']} doesn't have a config. Either this mod doesn't require one, or you need to restart your game to generate the config.")
            return

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            if not config:  # if the config is empty treat it as if there's no file
                messagebox.showinfo("No Config Found", f"{mod['title']} doesn't have a config. Either this mod doesn't require one, or you need to restart your game to generate the config.")
                return
            
            self.open_config_editor(mod['title'], config, config_path)
        except json.JSONDecodeError:
            messagebox.showerror("Error", f"Failed to parse the configuration file for {mod['title']}.")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while trying to edit the configuration: {str(e)}")

    # opens a window to edit the configuration of a mod
    def open_config_editor(self, mod_name, config, config_path):
        if not config:  # if the config is empty treat it as if there's no file
            messagebox.showinfo("No Config Found", f"{mod_name} doesn't have a config. Either this mod doesn't require one, or you need to restart your game to generate the config.")
            return

        editor_window = tk.Toplevel(self.root)
        editor_window.title(f"Edit Config: {mod_name}")
        editor_window.geometry("400x400")

        icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
        if os.path.exists(icon_path):
            editor_window.iconbitmap(icon_path)

        frame = ttk.Frame(editor_window)
        frame.pack(expand=True, fill='both', padx=10, pady=10)

        canvas = tk.Canvas(frame)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        for i, (key, value) in enumerate(config.items()):
            ttk.Label(scrollable_frame, text=key).grid(row=i, column=0, sticky="w", padx=5, pady=2)
            
            if isinstance(value, bool):
                var = tk.BooleanVar(value=value)
                ttk.Checkbutton(scrollable_frame, variable=var, onvalue=True, offvalue=False).grid(row=i, column=1, sticky="w", padx=5, pady=2)
            elif isinstance(value, (int, float)):
                var = tk.StringVar(value=str(value))
                ttk.Entry(scrollable_frame, textvariable=var).grid(row=i, column=1, sticky="w", padx=5, pady=2)
            else:
                var = tk.StringVar(value=str(value))
                ttk.Entry(scrollable_frame, textvariable=var).grid(row=i, column=1, sticky="w", padx=5, pady=2)
            
            config[key] = var

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def save_config():
            try:
                new_config = {}
                for k, v in config.items():
                    value = v.get()
                    if isinstance(value, str):
                        # try to convert string to int or float if possible
                        try:
                            value = int(value)
                        except ValueError:
                            try:
                                value = float(value)
                            except ValueError:
                                pass  # keep it as a string if it's not a number
                    new_config[k] = value
                
                with open(config_path, 'w') as f:
                    json.dump(new_config, f, indent=2)
                messagebox.showinfo("Success", f"Configuration for {mod_name} has been updated.")
                editor_window.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save configuration: {str(e)}")

        ttk.Button(editor_window, text="Save", command=save_config).pack(pady=10)

    # shows context menu for mod actions
    def show_context_menu(self, event):
        listbox = event.widget
        index = listbox.nearest(event.y)
        
        menu = tk.Menu(self.root, tearoff=0)
        
        if index != -1:
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(index)
            listbox.activate(index)
            
            if listbox == self.available_listbox:
                menu.add_command(label="Install", command=self.install_mod)
            elif listbox == self.installed_listbox:
                menu.add_command(label="Uninstall", command=self.uninstall_mod)
                menu.add_command(label="Enable", command=self.enable_mod)
                menu.add_command(label="Disable", command=self.disable_mod)
                menu.add_command(label="Edit Config", command=self.edit_mod_config)

        menu.tk_popup(event.x_root, event.y_root)

    # enables selected mods
    def enable_mod(self):
        if not self.check_setup():
            return
        selected = self.installed_listbox.curselection()
        if selected:
            for index in selected:
                mod = self.installed_mods[index]
                mod['enabled'] = True
                self.update_mod_status_in_listbox(mod)
                self.save_mod_status(mod)
                self.copy_mod_to_game(mod)
                logging.info(f"Enabled mod: {mod['title']} (ID: {mod['id']}, Third Party: {mod.get('third_party', False)})")
            self.refresh_mod_lists()
            self.set_status(f"Enabled {len(selected)} mod(s)")
                
    # copies a third-party mod to the game directory
    def copy_third_party_mod_to_game(self, mod):
        src_path = os.path.join(self.mods_dir, "3rd_party", mod['id'])
        dst_path = os.path.join(self.settings['game_path'], 'GDWeave', 'Mods', mod['id'])
        shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
        self.set_status(f"Installed 3rd party mod: {mod['title']}")
        self.refresh_mod_lists()

    # uninstalls selected mods
    def uninstall_mod(self):
        if not self.check_game_not_running():
            return
        selected = self.installed_listbox.curselection()
        if selected:
            for index in selected:
                mod = self.installed_mods[index]
                self.set_status(f"Uninstalling mod: {mod['title']}")
                try:
                    self.uninstall_mod_files(mod)
                except Exception as e:
                    error_message = f"Failed to uninstall mod {mod['title']}: {str(e)}"
                    self.set_status(error_message)
                    self.send_to_discord(f"Error uninstalling mod in Hook, Line, & Sinker:\n{error_message}")
            self.refresh_mod_lists()

    # removes mod files from the system
    def uninstall_mod_files(self, mod):
        if mod.get('third_party', False):
            mod_path = os.path.join(self.mods_dir, "3rd_party", mod['id'])
        else:
            mod_path = os.path.join(self.mods_dir, mod['id'])
        
        if os.path.exists(mod_path):
            shutil.rmtree(mod_path)
        
        # remove from game directory if it exists
        game_mod_path = os.path.join(self.settings['game_path'], 'GDWeave', 'Mods', mod['id'])
        if os.path.exists(game_mod_path):
            shutil.rmtree(game_mod_path)
        
        self.set_status(f"Uninstalled mod: {mod['title']}")

    # enables selected mods
    def enable_mod(self):
        if not self.check_setup():
            return
        if not self.check_game_not_running():
            return
        selected = self.installed_listbox.curselection()
        if selected:
            enabled_count = 0
            for index in selected:
                mod = self.installed_mods[index]
                if not mod.get('enabled', True):
                    mod['enabled'] = True
                    self.update_mod_status_in_listbox(mod)
                    self.save_mod_status(mod)
                    self.copy_mod_to_game(mod)
                    enabled_count += 1
                    logging.info(f"Enabled mod: {mod['title']} (ID: {mod['id']}, Third Party: {mod.get('third_party', False)})")
            
            if enabled_count > 0:
                self.refresh_mod_lists()
                self.set_status(f"Enabled {enabled_count} mod(s)")
            else:
                self.set_status("No mods were enabled. Selected mods may already be enabled.")

    # disables selected mods
    def disable_mod(self):
        if not self.check_setup():
            return
        if not self.check_game_not_running():
            return
        selected = self.installed_listbox.curselection()
        if selected:
            for index in selected:
                mod = self.installed_mods[index]
                mod['enabled'] = False
                self.update_mod_status_in_listbox(mod)
                self.save_mod_status(mod)
                self.remove_mod_from_game(mod)
            self.refresh_mod_lists()
            self.set_status(f"Disabled {len(selected)} mod(s)")

    # creates a mod.json file for imported mods
    def create_mod_json(self, mod_folder, mod_name):
        mod_info = {
            'title': mod_name,
            'author': 'Unknown',
            'description': 'Imported mod',
            'enabled': True,
            'version': 'Unknown'
        }
        with open(os.path.join(mod_folder, 'mod.json'), 'w') as f:
            json.dump(mod_info, f)

    # checks if the game path is set and valid
    def check_setup(self):
        if not self.settings.get('game_path') or not os.path.exists(self.settings.get('game_path')):
            messagebox.showinfo("Setup Required", "Please follow all the steps for installation in the Game Manager tab.")
            self.notebook.select(3)  # switch to hls setup tab
            return False
        return True

    # updates the status of a mod in the installed mods listbox
    def update_mod_status_in_listbox(self, mod):
        index = self.installed_mods.index(mod)
        status = "✅" if mod.get('enabled', True) else "❌"
        third_party = "[3rd]" if mod.get('third_party', False) else ""
        self.installed_listbox.delete(index)
        self.installed_listbox.insert(index, f"{status} {third_party} {mod['title']}".strip())

    # shows a prompt to join the discord community
    def show_discord_prompt(self):
        if not self.settings.get('discord_prompt_shown', False):
            self.send_to_discord("Hook, Line, & Sinker received a new user!")
            response = messagebox.askyesno(
                "Join Our Discord Community",
                "Welcome to Hook, Line, & Sinker!\n\n"
                "We highly recommend joining our Discord community for:\n"
                "• Troubleshooting assistance (only place I can help!)\n"
                "• Latest updates and announcements\n"
                "• Mod discussions and sharing\n"
                "• Direct support from the developer\n\n"
                "Would you like to join our Discord now?",
                icon='info'
            )
            
            if response:
                webbrowser.open("https://discord.gg/HzhCPxeCKY")
            
            self.settings['discord_prompt_shown'] = True
            self.save_settings()

    # saves the status of a mod to its mod_info.json file
    def save_mod_status(self, mod):
        if mod.get('third_party', False):
            mod_folder = os.path.join(self.mods_dir, "3rd_party", mod['id'])
        else:
            mod_folder = os.path.join(self.mods_dir, mod['id'])
        
        mod_json_path = os.path.join(mod_folder, 'mod_info.json')
        
        if not os.path.exists(mod_folder):
            os.makedirs(mod_folder)
        
        try:
            with open(mod_json_path, 'w') as f:
                json.dump(mod, f, indent=2)
            logging.info(f"Saved mod status for {mod['title']} (ID: {mod['id']})")
        except Exception as e:
            error_message = f"Failed to save mod status for {mod['title']} (ID: {mod['id']}): {str(e)}"
            self.set_status(error_message)
            logging.info(error_message)
            self.send_to_discord(f"Error in Hook, Line, & Sinker:\n{error_message}")

        self.save_mod_cache()

    # loads the mod cache from file
    def load_mod_cache(self):
        try:
            if os.path.exists(self.mod_cache_file):
                with open(self.mod_cache_file, 'r') as f:
                    self.mod_cache = json.load(f)
            else:
                self.mod_cache = {}
        except Exception as e:
            error_message = f"Failed to load mod cache: {str(e)}"
            self.set_status(error_message)
            self.send_to_discord(f"Error loading mod cache in Hook, Line, & Sinker:\n{error_message}")
            self.mod_cache = {}  # set to empty dict in case of error

    # updates the mod details display when a mod is selected
    def update_mod_details(self, event):
        selected_listbox = event.widget
        selected = selected_listbox.curselection()
        if not selected:
            return

        index = selected[0]
        mod_title = selected_listbox.get(index)

        # clear previous details
        self.mod_details.config(state='normal')
        self.mod_details.delete('1.0', tk.END)

        # check if the selected item is a category
        if mod_title.startswith('-- '):
            category = mod_title.replace('--', '').strip()
            details = f"Category: {category}\n\n"
            details += f"This category groups together mods with similar functionality or purpose related to {category.lower()}."
            self.mod_details.insert(tk.END, details)
            self.mod_image.config(image='')
        else:
            try:
                # remove status emojis and leading/trailing spaces
                clean_title = mod_title.replace('✅', '').replace('❌', '').replace('[3rd]', '').strip()

                # find the mod in the appropriate list
                mod_list = self.available_mods if selected_listbox == self.available_listbox else self.installed_mods
                mod = next((m for m in mod_list if m['title'].strip() == clean_title), None)

                if mod is None:
                    raise ValueError(f"No mod found with title: {clean_title}")

                # update image
                image_path = os.path.join(self.mods_dir, mod['id'], 'icon.png')
                if os.path.exists(image_path):
                    img = Image.open(image_path)
                    img = img.resize((64, 64), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.mod_image.config(image=photo)
                    self.mod_image.image = photo
                else:
                    self.mod_image.config(image='')

                # prepare details text
                details = f"Title: {mod['title']}\n"
                details += f"Author: {mod.get('author', 'Unknown')}\n\n"
                
                if mod.get('third_party'):
                    details += f"Description: This is a third-party mod. We don't know much about {mod['title']} but we're sure it's great!\n\n"
                elif mod.get('description'):
                    description = strip_tags(mod['description']) or mod['description']
                    details += f"Description: {description}\n\n"
                
                if selected_listbox == self.installed_listbox:
                    details += f"Version: {mod.get('version', 'Unknown')}\n"
                    details += f"Status: {'Enabled' if mod.get('enabled', False) else 'Disabled'}\n"
                if mod.get('source'):
                    details += f"Source: {mod['source']}\n"

                # add the details to the text widget
                self.mod_details.insert(tk.END, details)

                # make source link clickable
                if mod.get('source'):
                    self.mod_details.tag_add("source_link", "end-2l", "end-1c")
                    self.mod_details.tag_config("source_link", foreground="blue", underline=1)
                    self.mod_details.tag_bind("source_link", "<Button-1>", lambda e: webbrowser.open(mod['source']))
                    self.mod_details.tag_bind("source_link", "<Enter>", lambda e: self.mod_details.config(cursor="hand2"))
                    self.mod_details.tag_bind("source_link", "<Leave>", lambda e: self.mod_details.config(cursor=""))

            except Exception as e:
                error_message = f"Error: Unable to find mod details for '{mod_title}'. Error: {str(e)}"
                self.mod_details.insert(tk.END, error_message)
                logging.error(f"Error in update_mod_details: {error_message}")

        self.mod_details.config(state='disabled')

    # loads and displays the mod image
    def load_mod_image(self, image_url):
        try:
            response = requests.get(image_url)
            image = Image.open(io.BytesIO(response.content))
            image.thumbnail((100, 100))  # resize image
            photo = ImageTk.PhotoImage(image)
            self.mod_image.config(image=photo)
            self.mod_image.image = photo  # keep a reference
        except Exception as e:
            logging.info(f"Failed to load image: {str(e)}")
            self.mod_image.config(image='')

    # verifies the game installation path
    def verify_installation(self):
        try:
            game_path = self.game_path_entry.get()
            exe_name = 'webfishing.exe' if platform.system() == 'Windows' else 'webfishing'
            exe_path = os.path.join(game_path, exe_name)
            if os.path.exists(game_path) and os.path.isfile(exe_path):
                self.set_status("Game installation verified successfully!")
            else:
                self.set_status(f"Invalid game installation path or {exe_name} not found!")
        except Exception as e:
            error_message = f"Error verifying game installation: {str(e)}"
            self.set_status(error_message)
            self.send_to_discord(f"Error verifying game installation in Hook, Line, & Sinker:\n{error_message}")

    # loads user settings from json file
    def load_settings(self):
        settings_path = os.path.join(self.app_data_dir, 'settings.json')
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                self.settings = json.load(f)
        else:
            self.settings = {}
        
        # set default value for discord prompt if it doesn't exist
        if 'discord_prompt_shown' not in self.settings:
            self.settings['discord_prompt_shown'] = False
        
        self.print_settings()

    # saves current user settings to json file
    def save_settings(self):
        self.settings.update({
            "auto_update": self.auto_update.get(),
            "notifications": self.notifications.get(),
            "theme": self.theme.get(),
            "game_path": self.game_path_entry.get()
        })
        settings_path = os.path.join(self.app_data_dir, 'settings.json')
        with open(settings_path, 'w') as f:
            json.dump(self.settings, f)
        self.set_status("Settings saved successfully!")
        logging.info("Settings saved:", self.settings)

    # fetches list of available mods from remote server
    def load_mods(self):
        try:
            response = requests.get("https://notnite.github.io/webfishing-mods/list.json")
            self.available_mods = response.json()
            self.refresh_mod_lists()
        except requests.RequestException as e:
            self.set_status(f"Failed to load mods: {str(e)}")

    # updates the ui lists of available and installed mods
    def refresh_mod_lists(self):
        if hasattr(self, 'available_listbox'):
            # preserve the current items in the listbox
            current_items = list(self.available_listbox.get(0, tk.END))
            
            # only update if the list is empty (first load) or if it doesn't contain categories
            if not current_items or not any(item.startswith('-- ') for item in current_items):
                self.load_available_mods()  # this will repopulate with categories
            # if categories exist we don't need to do anything here

        self.installed_mods = self.get_installed_mods()
        
        if hasattr(self, 'installed_listbox'):
            self.installed_listbox.delete(0, tk.END)
            for mod in self.installed_mods:
                status = "✅" if mod.get('enabled', True) else "❌"
                third_party = " [3rd]" if mod.get('third_party', False) else ""
                if third_party:
                    display_text = f"{status}{third_party} {mod['title']}"
                else:
                    display_text = f"{status} {mod['title']}"
                self.installed_listbox.insert(tk.END, display_text)

        # update the mod cache
        self.save_mod_cache()

    # removes non-existent mods from the cache
    def clean_mod_cache(self):
        updated_cache = {}
        for mod_id, mod_info in self.mod_cache.items():
            if self.mod_exists({'id': mod_id, 'third_party': mod_info.get('third_party', False)}):
                updated_cache[mod_id] = mod_info
        self.mod_cache = updated_cache
        self.save_mod_cache()

    # retrieves list of installed mods from the mods directory
    def get_installed_mods(self):
        installed_mods = []
        
        # check official mods
        for mod_folder in os.listdir(self.mods_dir):
            if mod_folder != "3rd_party":
                mod_info_path = os.path.join(self.mods_dir, mod_folder, 'mod_info.json')
                if os.path.exists(mod_info_path):
                    with open(mod_info_path, 'r') as f:
                        mod_info = json.load(f)
                        installed_mods.append(mod_info)

        # check third-party mods
        third_party_mods_dir = os.path.join(self.mods_dir, "3rd_party")
        if os.path.exists(third_party_mods_dir):
            for mod_folder in os.listdir(third_party_mods_dir):
                mod_info_path = os.path.join(third_party_mods_dir, mod_folder, 'mod_info.json')
                if os.path.exists(mod_info_path):
                    with open(mod_info_path, 'r') as f:
                        mod_info = json.load(f)
                        mod_info['third_party'] = True
                        installed_mods.append(mod_info)

        return installed_mods

    # downloads and installs a mod
    def download_and_install_mod(self, mod, install=True):
        try:
            def download_task():
                logging.info(f"Starting download for mod: {mod['title']}")
                response = requests.get(mod['download'], stream=True)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                logging.info(f"Total download size: {total_size} bytes")
                
                # define the path to download the zip file in the temp folder within appdata
                temp_dir = os.path.join(os.getenv('APPDATA'), 'HookLineSinker', 'temp')
                os.makedirs(temp_dir, exist_ok=True)
                zip_path = os.path.join(temp_dir, 'mod.zip')
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logging.info(f"Download completed. Saved to: {zip_path}")
                
                # extract the zip file into a temporary directory within the temp folder
                extract_dir = os.path.join(temp_dir, 'extract_' + str(int(time.time())))
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                logging.info(f"Extracted zip file to: {extract_dir}")
                
                # find the manifest.json file
                manifest_path = None
                for root, dirs, files in os.walk(extract_dir):
                    if 'manifest.json' in files:
                        manifest_path = os.path.join(root, 'manifest.json')
                        break
                
                if not manifest_path:
                    raise ValueError("manifest.json not found in the mod package")
                logging.info(f"Found manifest.json at: {manifest_path}")

                # read the manifest.json before moving the directory
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
                    mod_id = manifest.get('Id')
                    if not mod_id:
                        raise ValueError("Id not found in manifest.json")
                logging.info(f"Mod ID from manifest: {mod_id}")

                # determine the main mod directory
                mod_dir = os.path.dirname(manifest_path)
                logging.info(f"Main mod directory determined: {mod_dir}")

                # move the mod directory to self.mods_dir
                final_mod_dir = os.path.join(self.mods_dir, mod_id)
                if os.path.exists(final_mod_dir):
                    logging.info(f"Moving existing mod directory to temp: {final_mod_dir}")
                    old_mod_dir = os.path.join(temp_dir, f'old_{mod_id}_{int(time.time())}')
                    shutil.move(final_mod_dir, old_mod_dir)
                shutil.move(mod_dir, final_mod_dir)
                logging.info(f"Moved mod directory to: {final_mod_dir}")

                version_info = self.get_mod_version(mod)
                mod_info = {
                    'id': mod_id,
                    'title': mod['title'],
                    'author': mod.get('author', 'Unknown'),
                    'description': mod.get('description', ''),
                    'version': version_info['version'],
                    'published_at': version_info['published_at'],
                    'enabled': True,
                    'download_url': mod['download']
                }

                # save mod_info.json
                mod_info_path = os.path.join(final_mod_dir, 'mod_info.json')
                with open(mod_info_path, 'w') as f:
                    json.dump(mod_info, f, indent=2)
                logging.info(f"Saved mod_info.json to: {mod_info_path}")

                if install:
                    self.root.after(0, self.installation_complete, mod_info)
                else:
                    return mod_info

            if install:
                threading.Thread(target=download_task, daemon=True).start()
                return None
            else:
                return download_task()

        except Exception as e:
            logging.exception(f"Error during mod installation: {str(e)}")
            self.root.after(0, self.installation_failed, str(e))
            return None

    # called when mod installation is complete
    def installation_complete(self, mod_info):
        self.set_status(f"Mod {mod_info['title']} version {mod_info['version']} installed successfully!")
        self.refresh_mod_lists()
        self.copy_mod_to_game(mod_info)

    # installs a previously downloaded mod
    def install_downloaded_mod(self, mod_info):
        # move the downloaded mod to the mods directory
        mod_path = os.path.join(self.mods_dir, mod_info['id'])
        os.makedirs(mod_path, exist_ok=True)
        
        # save mod_info.json
        with open(os.path.join(mod_path, 'mod_info.json'), 'w') as f:
            json.dump(mod_info, f, indent=2)
        
        # copy mod files to game directory
        self.copy_mod_to_game(mod_info)
        
        # add to installed mods list
        self.installed_mods.append(mod_info)
        
        self.set_status(f"Installed mod: {mod_info['title']}")
        self.installation_complete(mod_info)

    # updates progress bar during mod download
    def update_progress(self, downloaded_size, total_size):
        self.root.update_idletasks()

    # verifies the contents of the app data mods directory
    def verify_appdata_mods(self):
        logging.info("Verifying contents of app data mods directory")
        for mod_id in os.listdir(self.mods_dir):
            mod_path = os.path.join(self.mods_dir, mod_id)
            if os.path.isdir(mod_path):
                logging.info(f"Mod directory: {mod_id}")
                for root, dirs, files in os.walk(mod_path):
                    for file in files:
                        logging.info(f"  - {os.path.join(os.path.relpath(root, mod_path), file)}")
                        
    # called when mod installation is complete
    def installation_complete(self, mod_info):
        self.set_status(f"Mod {mod_info['title']} version {mod_info['version']} installed successfully!")
        self.refresh_mod_lists()
        self.verify_appdata_mods() 
        self.copy_mod_to_game(mod_info)

    # called when mod installation fails
    def installation_failed(self, error_message):
        self.set_status(f"Failed to install mod: {error_message}")

    # retrieves the version information for a mod
    def get_mod_version(self, mod):
        try:
            url = mod['download']
            parsed_url = urlparse(url)
            
            if 'github.com' in parsed_url.netloc:
                # github url
                repo_owner, repo_name = parsed_url.path.split('/')[1:3]
                api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
            else:
                # assume gitea url
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                path_parts = parsed_url.path.split('/')
                repo_owner, repo_name = path_parts[1:3]
                api_url = f"{base_url}/api/v1/repos/{repo_owner}/{repo_name}/releases/latest"
            
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()
            
            # extract version from tag_name
            version = re.search(r'v?(\d+\.\d+\.\d+)', data['tag_name'])
            version = version.group(1) if version else data['tag_name']
            
            return {
                'version': version,
                'published_at': data['published_at']
            }
        except Exception as e:
            logging.info(f"Failed to get version: {str(e)}")
            return {
                'version': "Unknown",
                'published_at': None
            }
    # checks for updates to the program mods and gdweave
    def check_for_updates(self, silent=False):
        try:
            program_updated = self.check_for_program_updates(silent)
            # check for mod updates
            self.set_status("Checking for mod and GDWeave updates...")
            updates_available = False
            
            if not self.installed_mods:
                self.set_status("No mods installed. Skipping mod update check.")
            else:
                for installed_mod in self.installed_mods:
                    for available_mod in self.available_mods:
                        if installed_mod['title'].lower() == available_mod['title'].lower():
                            try:
                                if self.is_update_available(installed_mod, available_mod):
                                    updates_available = True
                                    new_version = self.get_mod_version(available_mod)['version']
                                    if silent or messagebox.askyesno("Update Available", f"Update available for {installed_mod['title']} (New version: {new_version}). Do you want to update?"):
                                        self.download_and_install_mod(available_mod)
                            except Exception as e:
                                error_message = f"Error checking update for mod {installed_mod['title']}: {str(e)}"
                                self.set_status(error_message)
                                self.send_to_discord(f"Error checking mod update in Hook, Line, & Sinker:\n{error_message}")
                            break
            
            # check for gdweave update
            gdweave_version = self.get_gdweave_version()
            if gdweave_version != self.settings.get('gdweave_version', 'Unknown'):
                updates_available = True
                if silent:
                    self.install_gdweave()
                elif messagebox.askyesno("Update Available", f"Update available for GDWeave. Do you want to update?"):
                    self.install_gdweave()
                else:
                    self.set_status("GDWeave update skipped by user.")
            
            if not silent and not program_updated and not updates_available:
                messagebox.showinfo("Up to Date", "Your program and all mods are up to date!")
            elif not updates_available:
                self.set_status("No mod or GDWeave updates available.")
        except Exception as e:
            error_message = f"Failed to check for updates: {str(e)}"
            self.set_status(error_message)
            self.send_to_discord(f"Error checking for updates in Hook, Line, & Sinker:\n{error_message}")

    # checks if an update is available for a mod
    def is_update_available(self, installed_mod, available_mod):
        installed_published_at = installed_mod.get('published_at')
        available_version_info = self.get_mod_version(available_mod)
        available_published_at = available_version_info['published_at']
        
        if installed_published_at and available_published_at:
            return installed_published_at < available_published_at
        else:
            # fallback to version string comparison if timestamps are not available
            installed_version = installed_mod.get('version', '0.0.0')
            available_version = available_version_info['version']
            
            # convert version strings to tuples for comparison
            def version_tuple(v):
                return tuple(map(int, (v.split("."))))
            
            try:
                return version_tuple(installed_version) < version_tuple(available_version)
            except ValueError:
                # if version comparison fails assume an update is not available
                logging.info(f"Warning: Unable to compare versions for {installed_mod['title']}. Assuming update is not available.")
                return False

    # saves the current state of installed mods to a cache file
    def save_mod_cache(self):
        try:
            mod_cache = {}
            for mod in self.installed_mods:
                mod_cache[mod['id']] = {
                    'title': mod['title'],
                    'version': mod.get('version', 'Unknown'),
                    'enabled': mod.get('enabled', True),
                    'third_party': mod.get('third_party', False)
                }
            with open(self.mod_cache_file, 'w') as f:
                json.dump(mod_cache, f, indent=2)
            logging.info(f"Mod cache saved. Total mods cached: {len(mod_cache)}")
        except Exception as e:
            error_message = f"Failed to save mod cache: {str(e)}"
            self.set_status(error_message)
            logging.info(error_message)
            self.send_to_discord(f"Error saving mod cache in Hook, Line, & Sinker:\n{error_message}")
            
    # copies a mod from the app data directory to the game directory
    def copy_mod_to_game(self, mod_info):
        mod_id = mod_info['id']
        is_third_party = mod_info.get('third_party', False)
        
        if is_third_party:
            source_dir = os.path.join(self.mods_dir, "3rd_party", mod_id)
        else:
            source_dir = os.path.join(self.mods_dir, mod_id)
        
        logging.info(f"copy_mod_to_game called for mod '{mod_info['title']}' (ID: {mod_id}, Third Party: {is_third_party})")
        logging.info(f"Source directory: {source_dir}")

        if not os.path.exists(source_dir):
            logging.error(f"Source directory for mod '{mod_info['title']}' (ID: {mod_id}) not found.")
            return

        logging.info(f"Contents of source directory {source_dir} before copying:")
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                logging.info(os.path.join(root, file))

        if not self.settings.get('game_path'):
            logging.error("Game path not set. Cannot copy mod to game.")
            return

        destination_dir = os.path.join(self.settings['game_path'], 'GDWeave', 'Mods', mod_id)
        logging.info(f"Destination directory: {destination_dir}")

        try:
            if os.path.exists(destination_dir):
                logging.info(f"Removing existing destination directory: {destination_dir}")
                shutil.rmtree(destination_dir)
            
            logging.info(f"Copying from {source_dir} to {destination_dir}")
            shutil.copytree(source_dir, destination_dir)
            
            logging.info(f"Contents of destination directory {destination_dir} after copying:")
            for root, dirs, files in os.walk(destination_dir):
                for file in files:
                    logging.info(os.path.join(root, file))
            
            logging.info(f"Mod '{mod_info['title']}' (ID: {mod_id}) copied successfully to game directory.")
        except Exception as e:
            logging.error(f"Error copying mod '{mod_info['title']}' (ID: {mod_id}) to game directory: {str(e)}")
            logging.error(traceback.format_exc())

    # removes a mod from the game directory
    def remove_mod_from_game(self, mod):
        gdweave_mods_path = os.path.join(self.settings['game_path'], 'GDWeave', 'Mods')
        mod_path_in_game = os.path.join(gdweave_mods_path, mod['id'])
        
        if os.path.exists(mod_path_in_game):
            logging.info(f"Removing mod from game: {mod_path_in_game}")
            shutil.rmtree(mod_path_in_game)
            logging.info(f"Successfully removed mod '{mod['title']}' (ID: {mod['id']}) from game directory.")
        else:
            logging.info(f"Mod '{mod['title']}' (ID: {mod['id']}) not found in game directory.")

    # periodically checks for updates in the background
    def periodic_update_check(self):
        while True:
            time.sleep(3600)  # check every hour
            if self.settings.get('auto_update', False):
                try:
                    self.check_for_updates(silent=True)
                except Exception as e:
                    logging.info(f"Error during mod updates check: {str(e)}")
                    self.set_status(f"Error checking for mod updates: {str(e)}")
                    self.send_to_discord(f"Error checking for mod updates in Hook, Line, & Sinker:\n{str(e)}")
                try:
                    self.check_for_program_updates(silent=False)
                except Exception as e:
                    logging.info(f"Error during program updates check: {str(e)}")
                    self.set_status(f"Error checking for program updates: {str(e)}")
                    self.send_to_discord(f"Error checking for program updates in Hook, Line, & Sinker:\n{str(e)}")

    # logs the current settings
    def print_settings(self):
        logging.info("Current settings:")
        for key, value in self.settings.items():
            logging.info(f"  {key}: {value}")

    # opens a file dialog to select the game directory
    def browse_game_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.game_path_entry.delete(0, tk.END)
            self.game_path_entry.insert(0, directory)
            self.save_game_path()

    # saves the selected game path to settings
    def save_game_path(self):
        new_path = self.game_path_entry.get()
        if os.path.exists(new_path):
            self.settings['game_path'] = new_path
            self.save_settings()
            self.set_status(f"Game path updated to: {new_path}")
            logging.info(f"Game path updated to: {new_path}")
            self.update_setup_status()
        else:
            self.set_status("Invalid game path. Please enter a valid directory.")
            logging.info("Invalid game path entered.")
    # loads and displays available mods categorized
    def load_available_mods(self):
        try:
            # start with an empty list
            self.available_mods = []

            # load official mods
            response = requests.get("https://notnite.github.io/webfishing-mods/list.json")
            official_mods = response.json()
            
            # ensure each official mod has an 'id' key
            for mod in official_mods:
                if 'id' not in mod:
                    mod['id'] = mod.get('title', '').replace(' ', '_').lower()
            
            # create a dictionary to hold mods by category
            categorized_mods = {"Uncategorized": []}

            # debug print mod categories
            print("Mod Categories:", self.mod_categories)

            for mod in official_mods:
                category = self.mod_categories.get(mod['title'], "Uncategorized")
                if category not in categorized_mods:
                    categorized_mods[category] = []
                categorized_mods[category].append(mod)

            # debug print categorized mods
            print("Categorized Mods:", categorized_mods)

            # clear the current list
            self.available_listbox.delete(0, tk.END)

            # add mods to the listbox grouped by category
            for category in sorted(categorized_mods.keys()):
                if category != "Uncategorized" and categorized_mods[category]:
                    self.available_listbox.insert(tk.END, f"-- {category} --")
                    self.available_listbox.itemconfig(tk.END, {'bg':'lightgray', 'fg':'black'})
                    print(f"Added category: {category}")  # debug print
                    for mod in sorted(categorized_mods[category], key=lambda x: x['title']):
                        self.available_listbox.insert(tk.END, f"  {mod['title']}")
                        self.available_mods.append(mod)
                        print(f"  Added mod: {mod['title']}")  # debug print

            # add uncategorized mods at the end
            if categorized_mods["Uncategorized"]:
                self.available_listbox.insert(tk.END, "-- Uncategorized --")
                self.available_listbox.itemconfig(tk.END, {'bg':'lightgray', 'fg':'black'})
                print("Added category: Uncategorized")  # debug print
                for mod in sorted(categorized_mods["Uncategorized"], key=lambda x: x['title']):
                    self.available_listbox.insert(tk.END, f"  {mod['title']}")
                    self.available_mods.append(mod)
                    print(f"  Added mod: {mod['title']}")  # debug print
            
            self.refresh_mod_lists()
        except requests.RequestException as e:
            self.set_status(f"Failed to load mods: {str(e)}")
            self.send_to_discord(f"Error loading mods in Hook, Line, & Sinker:\n{str(e)}")

        # debug print final available mods list
        print("Final Available Mods:", [mod['title'] for mod in self.available_mods])

    # checks if a mod id exists in the mods directory
    def mod_id_exists(self, mod_id):
        # check in the mods directory
        if os.path.exists(os.path.join(self.mods_dir, mod_id)):
            return True
        
        # check in the 3rd party mods directory
        if os.path.exists(os.path.join(self.mods_dir, "3rd_party", mod_id)):
            return True
        
        # check in the installed mods list
        for mod in self.installed_mods:
            if mod.get('id') == mod_id:
                return True
        
        return False

    # checks if a mod exists in the mods directory
    def mod_exists(self, mod):
        if mod.get('id') == 'separator':
            return True
        
        # if the mod doesn't have an 'id' we can't check if it exists
        if 'id' not in mod:
            return True  # assume it exists if we can't check
        
        if mod.get('third_party', False):
            mod_path = os.path.join(self.mods_dir, "3rd_party", mod['id'])
        else:
            mod_path = os.path.join(self.mods_dir, mod['id'])
        return os.path.exists(mod_path)

    # loads third-party mods from the mods directory
    def load_third_party_mods(self):
        third_party_mods_dir = os.path.join(self.mods_dir, "3rd_party")
        if not os.path.exists(third_party_mods_dir):
            return

        for mod_folder in os.listdir(third_party_mods_dir):
            mod_path = os.path.join(third_party_mods_dir, mod_folder)
            if os.path.isdir(mod_path):
                mod_info_path = os.path.join(mod_path, 'mod_info.json')
                if os.path.exists(mod_info_path):
                    with open(mod_info_path, 'r') as f:
                        mod_info = json.load(f)
                        mod_info['third_party'] = True
                        self.available_mods.append(mod_info)

if __name__ == "__main__":
    root = tk.Tk()
    app = HookLineSinkerUI(root)
    root.mainloop()