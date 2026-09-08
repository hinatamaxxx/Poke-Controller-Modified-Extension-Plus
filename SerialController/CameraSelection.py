"""Keep a selected physical device independent of DirectShow enumeration order. MIT."""
import hashlib
from WindowsDevices import enumerate_cameras


class CameraSelection:
    def __init__(self, app):
        self.app = app
        self.path = app.settings.camera_path
        self.name = app.settings.camera_name
        self.rows = []
        self.generation = 0
        self.state = '未接続'
        self.needs_selection = not self.path and app.camera_id.get() >= 0
        app.camera_name_cb.configure(state='readonly', postcommand=self.refresh)
        # Numeric-only settings cannot identify a device after unplug/reorder.
        if self.needs_selection:
            self.state = 'カメラ名を選び直してください（旧設定は番号のみ）'
        self.refresh()
        app.root.after(200, self.poll)

    def refresh(self):
        self.rows = enumerate_cameras()
        labels = ['Disable']
        for device in self.rows:
            identity = device['path']
            suffix = hashlib.sha256(identity.encode()).hexdigest()[:6] if identity else 'IDなし'
            labels.append(f"{device['name']} [{suffix}]")
        selected = next((i + 1 for i, d in enumerate(self.rows) if self.path and d['path'] == self.path), None)
        if self.path and selected is None:
            labels.append(f'{self.name}（未接続）')
            selected = len(labels) - 1
        self.app.camera_name_cb['values'] = labels
        self.app.camera_name_cb.current(selected or 0)
        index = next((d['index'] for d in self.rows if self.path and d['path'] == self.path), -1)
        self.app.camera_id.set(index)

    def select(self):
        index = self.app.camera_name_cb.current()
        if index == 0:
            self.path, self.name = '', ''
        elif 1 <= index <= len(self.rows):
            device = self.rows[index - 1]
            if not device['path']:
                self.state = '機器を識別できないため接続できません'
                self.refresh()
                return
            self.path, self.name = device['path'], device['name']
        self.app.settings.camera_path = self.path
        self.needs_selection = False
        self.app.settings.camera_name = self.name
        self.connect()

    def connect(self):
        self.generation += 1
        generation = self.generation
        self.refresh()
        camera = self.app.camera
        camera.destroy()
        self.state = '未接続' if not self.path else '切り替え中…'
        def start():
            if generation != self.generation:
                return
            if camera.thread is not None and camera.thread.is_alive():
                self.app.root.after(100, start)
                return
            camera.error = ''
            if not self.path:
                self.state = 'カメラ名を選び直してください（旧設定は番号のみ）' if self.needs_selection else '無効'
                return
            if self.app.camera_id.get() < 0:
                self.state = f'未接続：{self.name}'
                return
            self.state = f'接続中：{self.name}'
            camera.openCamera(self.app.camera_id.get(), device_path=self.path)
        start()

    def poll(self):
        camera = getattr(self.app, 'camera', None)
        if camera is not None:
            if camera.error and self.path and self.state != '切り替え中…':
                self.state = '未接続：' + camera.error
            elif camera.isOpened() and getattr(camera, 'device_path', '') == self.path:
                self.state = '接続済み：' + self.name
        self.app.camera_status.configure(text=self.state)
        self.app.root.after(200, self.poll)
