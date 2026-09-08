"""Settings and complete-release updates for the existing Tk app. MIT."""
from pathlib import Path
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from urllib.parse import quote
import requests
from product import NAME, VERSION, REPOSITORY_URL
from update_service import find_release, installed_libraries, release_page


class SettingsWindow:
    def __init__(self, app, root, preferences, mcp_enabled, toggle_mcp):
        self.app, self.root, self.preferences = app, Path(root), preferences
        self.mcp_enabled, self.toggle_mcp = mcp_enabled, toggle_mcp
        self.window = None
        self.busy = False
        self.release = None

    def show(self, tab='general'):
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self.tabs.select(self.pages.get(tab, self.pages['general']))
            return
        self.window = tk.Toplevel(self.app.root)
        self.window.title('設定 — ' + NAME)
        self.window.geometry('760x620')
        self.window.minsize(640, 520)
        self.window.protocol('WM_DELETE_WINDOW', self.window.withdraw)
        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill='both', expand=True, padx=12, pady=12)
        self.pages = {}
        for key, title in (('general', 'MCP'), ('updates', 'アプリの更新'), ('libraries', '同梱ライブラリ')):
            page = ttk.Frame(self.tabs, padding=16)
            self.tabs.add(page, text=title)
            self.pages[key] = page
        general = self.pages['general']
        ttk.Checkbutton(general, text='MCPを有効にする', variable=self.mcp_enabled, command=self.toggle_mcp).pack(anchor='w')
        ttk.Label(general, text='初期状態はOFFです。設定はプロファイルごとに保存します。\n接続先はこのPC内（127.0.0.1）のみで、接続トークンを使います。\nMCPクライアントから既存スクリプトの開始・停止などを操作できます。', wraplength=650).pack(anchor='w', pady=14)
        ttk.Button(general, text='接続方法を開く', command=lambda: os.startfile(self.root / 'MCP.md')).pack(anchor='w')
        update = self.pages['updates']
        ttk.Label(update, text=f'{NAME}\n現在のバージョン：{VERSION}', wraplength=650).pack(anchor='w')
        ttk.Label(update, text='更新は手動で行います。アプリを終了し、新しいZIPを別フォルダーへ展開してください。\nprofiles・独自スクリプト・画像などをコピーして起動します。アプリからファイルを書き換えることはありません。', wraplength=650).pack(anchor='w', pady=10)
        self.prereleases = tk.BooleanVar(value=self.preferences.values['prereleases'])
        ttk.Checkbutton(update, text='検証版（alpha / beta / rc）も確認する', variable=self.prereleases,
                        command=lambda: self.preferences.set('prereleases', self.prereleases.get())).pack(anchor='w')
        ttk.Label(update, text='非公開リポジトリ用GitHubトークン（任意・保存しません）').pack(anchor='w', pady=(12, 2))
        self.token = ttk.Entry(update, show='*')
        self.token.pack(fill='x')
        actions = ttk.Frame(update)
        actions.pack(fill='x', pady=12)
        self.check = ttk.Button(actions, text='更新を確認', command=self.check_update)
        self.check.pack(side='left')
        self.download = ttk.Button(actions, text='配布ページを開く', command=self.download_update, state='disabled')
        self.download.pack(side='left', padx=8)
        ttk.Button(actions, text='現在のアプリフォルダーを開く', command=lambda: os.startfile(self.root)).pack(side='left')
        self.status = tk.StringVar(value='更新確認はボタンを押したときに行います。')
        ttk.Label(update, textvariable=self.status, wraplength=650).pack(anchor='w')
        ttk.Button(update, text='GitHubのリリースを開く', command=lambda: webbrowser.open(REPOSITORY_URL + '/releases')).pack(anchor='w', pady=10)
        library = self.pages['libraries']
        ttk.Label(library, text='初期状態は全選択です。チェックを外すと個別更新できます。更新は再起動後に反映します。\nFFmpegはopencv-pythonと一緒に更新します。最新版でのスクリプト互換性は保証されません。', wraplength=650).pack(anchor='w')
        self.library_table = ttk.Treeview(library, columns=('check', 'name', 'version', 'latest'), show='headings', height=7)
        for key, title in (('check', '更新'), ('name', '部品'), ('version', '次回起動のバージョン'), ('latest', 'PyPIの最新版')):
            self.library_table.heading(key, text=title)
            self.library_table.column(key, width=45 if key == 'check' else 190)
        self.library_table.pack(fill='both', expand=True, pady=8)
        for item in installed_libraries(self.root):
            self.library_table.insert('', 'end', values=('☑', item['name'], item['version'], '未確認'))
        self.library_table.bind('<Button-1>', self.toggle_library)
        self.library_table.bind('<space>', self.toggle_library)
        actions = ttk.Frame(library)
        actions.pack(fill='x')
        ttk.Button(actions, text='全選択', command=lambda: self.select_libraries(True)).pack(side='left')
        ttk.Button(actions, text='全解除', command=lambda: self.select_libraries(False)).pack(side='left')
        self.library_check = ttk.Button(actions, text='更新確認', command=self.check_library)
        self.library_check.pack(side='left')
        self.library_update = ttk.Button(actions, text='チェックした部品を更新', command=self.update_libraries)
        self.library_update.pack(side='left')
        self.library_reset = ttk.Button(library, text='配布時のライブラリに戻す', command=self.reset_libraries)
        self.library_reset.pack(anchor='w')
        self.library_status = tk.StringVar(value='チェックを外した部品のバージョンは維持します。')
        ttk.Label(library, textvariable=self.library_status, wraplength=650).pack(anchor='w')
        import cv2
        ffmpeg = '\n'.join(line.strip() for line in cv2.getBuildInformation().splitlines() if any(key in line for key in ('FFMPEG:', 'avcodec:', 'avformat:', 'avutil:')))
        ttk.Label(library, text='FFmpeg（OpenCV付属）\n' + ffmpeg, wraplength=650).pack(anchor='w', pady=8)
        self.tabs.select(self.pages.get(tab, general))

    def run(self, work, done):
        if self.busy:
            return
        self.busy = True
        self.check.configure(state='disabled')
        self.download.configure(state='disabled')
        self.library_check.configure(state='disabled')
        self.library_update.configure(state='disabled')
        self.library_reset.configure(state='disabled')
        def finish(result, error):
            self.busy = False
            self.check.configure(state='normal')
            self.library_check.configure(state='normal')
            self.library_update.configure(state='normal')
            self.library_reset.configure(state='normal')
            if error:
                self.library_status.set('処理に失敗しました。現在の環境は維持されています。')
                self.status.set('処理に失敗しました。再試行できます。')
                messagebox.showerror('更新', error, parent=self.window)
            else:
                done(result)
            self.download.configure(state='normal' if self.release else 'disabled')
        def worker():
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, str(exc)
            if not self.app.dispatcher.closed:
                self.app.dispatcher.critical.put((finish, (result, error), {}))
        threading.Thread(target=worker, daemon=True).start()

    def check_update(self):
        token, prereleases = self.token.get(), self.prereleases.get()
        self.release = None
        self.status.set('GitHubで更新を確認しています…')
        def done(release):
            self.release = release
            self.status.set(f"更新があります：{release['tag_name']}" if release else '利用できる新しい配布版はありません。下書きリリースは対象外です。')
        self.run(lambda: find_release(token, prereleases), done)

    def download_update(self):
        if self.release:
            webbrowser.open(release_page(self.release))

    def check_library(self):
        selected = self.checked_libraries()
        if not selected:
            messagebox.showinfo('同梱ライブラリ', '一覧から部品を選択してください。', parent=self.window)
            return
        def work():
            result = {}
            for identifier, name in selected:
                with requests.get('https://pypi.org/pypi/' + quote(name, safe='') + '/json', timeout=(5, 15)) as response:
                    response.raise_for_status()
                    result[identifier] = response.json()['info']['version']
            return result
        def done(result):
            for identifier, latest in result.items():
                self.library_table.set(identifier, 'latest', latest)
            self.library_status.set('更新確認が完了しました。')
        self.library_status.set('チェックした部品の最新版を確認しています…')
        self.run(work, done)

    def checked_libraries(self):
        return [(i, self.library_table.set(i, 'name')) for i in self.library_table.get_children()
                if self.library_table.set(i, 'check') == '☑']

    def select_libraries(self, selected):
        if not self.busy:
            for i in self.library_table.get_children():
                self.library_table.set(i, 'check', '☑' if selected else '☐')

    def toggle_library(self, event):
        if self.busy:
            return
        identifier = self.library_table.focus() if event.keysym == 'space' else self.library_table.identify_row(event.y)
        if identifier and (event.keysym == 'space' or self.library_table.identify_column(event.x) == '#1'):
            current = self.library_table.set(identifier, 'check')
            self.library_table.set(identifier, 'check', '☐' if current == '☑' else '☑')
            return 'break'

    def update_libraries(self):
        from library_update import update_libraries
        selected = [name for _, name in self.checked_libraries()]
        if not selected:
            self.library_status.set('更新する部品にチェックを入れてください。')
            return
        self.library_status.set('別の環境へ更新を準備しています。数分かかる場合があります…')
        self.run(lambda: update_libraries(self.root, selected), self.libraries_done)

    def reset_libraries(self):
        from library_update import reset_libraries
        self.run(lambda: reset_libraries(self.root), self.libraries_done)

    def libraries_done(self, message):
        self.library_status.set(message)
        versions = {item['name']: item['version'] for item in installed_libraries(self.root)}
        for i in self.library_table.get_children():
            self.library_table.set(i, 'version', versions.get(self.library_table.set(i, 'name'), '—'))
