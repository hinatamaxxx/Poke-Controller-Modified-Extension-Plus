"""Screen recording with the controller inputs sent meanwhile, so an assistant can study a game and write scripts. MIT.

A recording is a folder under Captures/recordings/<id>/: numbered JPEG frames, an mp4 for people, and
timeline.json with the frame times and every controller input meanwhile (manual, script or assistant).
"""
import json
import os
import threading
import time

MAX_SECONDS = 600
MAX_FPS = 10
FRAME_SIZE = (640, 360)


class Recorder:
    def __init__(self, core):
        self.core = core
        self.current = None
        self._lock = threading.Lock()
        self._original = {}

    @property
    def root(self):
        return os.path.join(os.getcwd(), 'Captures', 'recordings')

    def start(self, seconds=60, fps=5, label=''):
        import cv2
        seconds = min(max(float(seconds or 60), 1), MAX_SECONDS)
        fps = min(max(float(fps or 5), .5), MAX_FPS)
        with self._lock:
            if self.current and self.current['thread'].is_alive():
                raise ValueError('Already recording')
            if not self.core.camera_live():
                raise ValueError('No live camera frame')
            rec_id = time.strftime('%Y%m%d-%H%M%S')
            while os.path.exists(os.path.join(self.root, rec_id)):
                rec_id += 'a'
            folder = os.path.join(self.root, rec_id)
            os.makedirs(folder, exist_ok=True)
            info = {'id': rec_id, 'folder': folder, 'label': str(label or '')[:100], 'fps': fps, 'seconds': seconds,
                    'started': time.time(), 'frames': [], 'inputs': [], 'stop': threading.Event()}
            # OpenCV cannot open non-ASCII paths (a Japanese user name in Documents); the path relative to the
            # workspace is ASCII.
            writer = cv2.VideoWriter(os.path.join('Captures', 'recordings', rec_id, 'video.mp4'),
                                     cv2.VideoWriter_fourcc(*'mp4v'), fps, FRAME_SIZE)
            self._hook_sender(info)

            def run():
                try:
                    deadline = info['started'] + seconds
                    index = 0
                    while not info['stop'].is_set() and time.time() < deadline:
                        frame = self.core.camera.readFrame()
                        if frame is not None:
                            small = cv2.resize(frame, FRAME_SIZE)
                            name = f'{index:05d}.jpg'
                            ok, encoded = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            with open(os.path.join(folder, name), 'wb') as stream:
                                stream.write(encoded.tobytes())
                            writer.write(small)
                            info['frames'].append({'t': round(time.time() - info['started'], 3), 'file': name})
                            index += 1
                        info['stop'].wait(1 / fps)
                finally:
                    writer.release()
                    self._unhook_sender()
                    self._save(info)
            info['thread'] = threading.Thread(target=run, daemon=True)
            self.current = info
            info['thread'].start()
            return {'id': rec_id, 'seconds': seconds, 'fps': fps}

    def stop(self):
        info = self.current
        if not info:
            raise ValueError('Not recording')
        info['stop'].set()
        info['thread'].join(10)
        return self.summary(info)

    HOOKED = ('input', 'inputEnd', 'hold', 'holdEnd', 'neutral')
    PRESETS = ('UP', 'RIGHT', 'DOWN', 'LEFT', 'UP_RIGHT', 'DOWN_RIGHT', 'DOWN_LEFT', 'UP_LEFT')

    @classmethod
    def _describe(cls, btns):
        """(display names, Python expressions) for Button / Hat / Direction inputs."""
        items = btns if isinstance(btns, (list, tuple)) else [btns]
        names, code = [], []
        for b in items:
            if hasattr(b, 'stick'):  # Direction
                right = getattr(b.stick, 'name', '') == 'RIGHT'
                if b.showName in cls.PRESETS:
                    names.append(('RS_' if right else 'LS_') + b.showName)
                    code.append(f"Direction.{'R_' if right else ''}{b.showName}")
                else:
                    names.append(f"{'RS' if right else 'LS'}({b.x},{b.y})")
                    code.append(f"Direction(Stick.{'RIGHT' if right else 'LEFT'}, ({b.x}, {b.y}))")
            elif type(b).__name__ == 'Hat':
                names.append('Hat.' + b.name)
                code.append('Hat.' + b.name)
            elif type(b).__name__ == 'Touchscreen':
                names.append(f'Touch({b.x},{b.y})')
                code.append(f'Touchscreen({b.x}, {b.y})')
            else:
                # A combined flag (Button.A | Button.B) is written as its members.
                for part in (str(getattr(b, 'name', '') or '').split('|') or [str(b)]):
                    names.append(part)
                    code.append(f'Button.{part}')
        return names, code

    def _hook_sender(self, info):
        """Log every input while recording, by button name. Scripts make their own KeyPress objects,
        so the class methods are wrapped (manual input, scripts and the assistant all pass through them).
        Only the outermost call is logged (hold() calls input() inside)."""
        from Commands.Keys import KeyPress
        started = info['started']
        depth = threading.local()
        for name in self.HOOKED:
            original = KeyPress.__dict__[name]
            self._original[name] = original

            def wrapped(keys, *args, _original=original, _name=name, **kwargs):
                outer = not getattr(depth, 'n', 0)
                depth.n = getattr(depth, 'n', 0) + 1
                try:
                    result = _original(keys, *args, **kwargs)
                finally:
                    depth.n -= 1
                if outer and len(info['inputs']) < 20000:
                    try:
                        entry = {'t': round(time.time() - started, 3), 'action': _name}
                        if args and args[0] not in ([], None):
                            entry['buttons'], entry['code'] = self._describe(args[0])
                        elif _name == 'input':  # an analog stick position from the browser or tilt_stick
                            f = keys.format.format
                            entry['action'], entry['sticks'] = 'stick', {'L': [f['lx'], f['ly']], 'R': [f['rx'], f['ry']]}
                        elif _name == 'inputEnd':
                            return result
                        info['inputs'].append(entry)
                    except Exception:  # recording must never break the input itself
                        pass
                return result
            setattr(KeyPress, name, wrapped)

    def note(self, entry):
        """Add a non-input event (e.g. a template check) to the recording in progress."""
        info = self.current
        if info and info['thread'].is_alive() and len(info['inputs']) < 20000:
            info['inputs'].append({'t': round(time.time() - info['started'], 3), **entry})

    def _unhook_sender(self):
        from Commands.Keys import KeyPress
        for name, original in self._original.items():
            setattr(KeyPress, name, original)
        self._original = {}

    def _save(self, info):
        data = {k: info[k] for k in ('id', 'label', 'fps', 'started', 'frames', 'inputs')}
        data['duration'] = info['frames'][-1]['t'] if info['frames'] else 0
        with open(os.path.join(info['folder'], 'timeline.json'), 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)

    def summary(self, info):
        return {'id': info['id'], 'label': info['label'], 'recording': info['thread'].is_alive(),
                'frames': len(info['frames']), 'inputs': len(info['inputs']),
                'elapsed': round(time.time() - info['started'], 1) if info['thread'].is_alive() else
                (info['frames'][-1]['t'] if info['frames'] else 0), 'folder': info['folder']}

    def state(self):
        return self.summary(self.current) if self.current else None

    def list(self):
        if not os.path.isdir(self.root):
            return []
        result = []
        for rec_id in sorted(os.listdir(self.root), reverse=True)[:50]:
            path = os.path.join(self.root, rec_id, 'timeline.json')
            try:
                with open(path, encoding='utf-8') as stream:
                    data = json.load(stream)
                result.append({'id': rec_id, 'label': data.get('label', ''), 'duration': data.get('duration', 0),
                               'frames': len(data.get('frames', [])), 'inputs': len(data.get('inputs', []))})
            except (OSError, ValueError):
                continue
        return result

    def _timeline(self, rec_id):
        folder = os.path.realpath(os.path.join(self.root, str(rec_id)))
        if os.path.dirname(folder) != os.path.realpath(self.root):
            raise ValueError('Unknown recording')
        with open(os.path.join(folder, 'timeline.json'), encoding='utf-8') as stream:
            return folder, json.load(stream)

    def overview(self, rec_id, start=0.0, end=None, count=12):
        """A contact sheet: evenly spaced frames between start and end seconds, each labelled with its time and
        the inputs sent since the previous tile. Returns (jpeg bytes, text timeline)."""
        import cv2
        import numpy as np
        folder, data = self._timeline(rec_id)
        frames = [f for f in data['frames'] if f['t'] >= float(start) and (end is None or f['t'] <= float(end))]
        if not frames:
            raise ValueError('No frames in that range')
        count = min(max(int(count or 12), 1), 24)
        picked = [frames[int(round(i))] for i in np.linspace(0, len(frames) - 1, min(count, len(frames)))]
        columns = 4 if len(picked) > 4 else len(picked)
        tile_w, tile_h, caption = 320, 180, 34
        rows = (len(picked) + columns - 1) // columns
        sheet = np.full((rows * (tile_h + caption), columns * tile_w, 3), 24, dtype=np.uint8)
        lines, previous = [], float(start)

        def describe(entry):
            return self._line(entry)
        for i, frame in enumerate(picked):
            image = cv2.imdecode(np.fromfile(os.path.join(folder, frame['file']), np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                continue
            x, y = (i % columns) * tile_w, (i // columns) * (tile_h + caption)
            sheet[y:y + tile_h, x:x + tile_w] = cv2.resize(image, (tile_w, tile_h))
            sent = [describe(e) for e in data['inputs'] if previous < e['t'] <= frame['t']]
            label = f"{frame['t']:.1f}s" + (f"  {len(sent)} inputs" if sent else '')
            cv2.putText(sheet, label, (x + 6, y + tile_h + 22), cv2.FONT_HERSHEY_SIMPLEX, .55, (230, 230, 230), 1, cv2.LINE_AA)
            lines.append(f"[{frame['t']:.2f}s] frame {frame['file']}" + (f" | sent: {', '.join(sent[:20])}" if sent else ''))
            previous = frame['t']
        ok, encoded = cv2.imencode('.jpg', sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return encoded.tobytes(), '\n'.join(lines)

    def frame(self, rec_id, at):
        folder, data = self._timeline(rec_id)
        if not data['frames']:
            raise ValueError('Empty recording')
        best = min(data['frames'], key=lambda f: abs(f['t'] - float(at)))
        with open(os.path.join(folder, best['file']), 'rb') as stream:
            return stream.read(), best['t']

    def inputs(self, rec_id, start=0.0, end=None, limit=500):
        """Every input between start and end seconds, one line each, for writing a script from a recording."""
        _, data = self._timeline(rec_id)
        lines = []
        for entry in data['inputs']:
            if entry['t'] < float(start) or (end is not None and entry['t'] > float(end)):
                continue
            lines.append(f"{entry['t']:.3f}s {self._line(entry)}")
            if len(lines) >= int(limit):
                lines.append('…')
                break
        return '\n'.join(lines)

    @staticmethod
    def _line(entry):
        action = entry['action']
        if action == 'stick':
            return 'stick L{} R{}'.format(tuple(entry['sticks']['L']), tuple(entry['sticks']['R']))
        if action == 'check':
            return f"check {entry['template']} found={entry['found']} similarity={entry['similarity']}"
        return action + (' ' + '+'.join(entry['buttons']) if entry.get('buttons') else '')

    def draft_script(self, rec_id, name, loop=True, start=0.0, end=None, max_wait=3.0):
        """Turn the inputs of a recording (e.g. the assistant trying the steps by hand) into a Python script draft:
        presses with their measured durations, the waits between them (capped at max_wait, the measured time is kept
        as a comment), template checks, and optionally an endless loop with a counter."""
        _, data = self._timeline(rec_id)
        events = [e for e in data['inputs'] if e['t'] >= float(start) and (end is None or e['t'] <= float(end))
                  ]
        body, i, held = [], 0, []
        sticks = {'L': (128, 127), 'R': (128, 127)}  # centre, in Direction coordinates

        def gap(after, index):
            if index >= len(events):
                return .1
            return max(events[index]['t'] - after, 0)

        def capped(seconds):
            """The wait to write, and a comment with the measured time when it was shortened."""
            return min(seconds, max_wait), (f'  # 試したときは {seconds:.1f}秒' if seconds > max_wait else '')

        while i < len(events):
            e = events[i]
            action, code = e['action'], e.get('code', [])
            target = '[' + ', '.join(code) + ']' if len(code) > 1 else (code[0] if code else '')
            following = events[i + 1] if i + 1 < len(events) else None
            if action in ('hold', 'input') and following and following['action'] in ('holdEnd', 'inputEnd') \
                    and following.get('code') == code:
                duration = max(following['t'] - e['t'], .05)
                wait, comment = capped(gap(following['t'], i + 2))
                body.append(f'self.press({target}, duration={duration:.2f}, wait={wait:.2f}){comment}')
                i += 2
                continue
            if action in ('hold', 'input') and code:
                body.append(f'self.hold({target})')
                held += [c for c in code if c not in held]
            elif action in ('holdEnd', 'inputEnd') and code:
                body.append(f'self.holdEnd({target})')
                held = [c for c in held if c not in code]
            elif action == 'neutral':
                if held:
                    body.append(f"self.holdEnd([{', '.join(held)}])")
                    held = []
                else:
                    i += 1
                    continue
            elif action == 'stick':
                for side, stick in (('L', 'LEFT'), ('R', 'RIGHT')):
                    position = (e['sticks'][side][0], 255 - e['sticks'][side][1])
                    if position == sticks[side]:
                        continue
                    if sticks[side] != (128, 127):
                        body.append(f'self.holdEnd(Direction(Stick.{stick}, {sticks[side]}))')
                    if position != (128, 127):
                        body.append(f'self.hold(Direction(Stick.{stick}, {position}))')
                    sticks[side] = position
            elif action == 'check':
                body.append(f"if self.isContainTemplate({e['template']!r}, threshold={e.get('threshold', .85)}):"
                            f"  # 試したときは {'見つかった' if e['found'] else '見つからなかった'}（一致度 {e['similarity']}）")
                body.append(f"    print({e['template'] + ' が見つかりました'!r})")
            if action != 'check':
                seconds = gap(e['t'], i + 1)
                if seconds >= .05 and body:
                    wait, comment = capped(seconds)
                    body.append(f'self.wait({wait:.2f}){comment}')
            i += 1
        if held:
            body.append(f"self.holdEnd([{', '.join(held)}])")
        if not body:
            raise ValueError('The recording has no inputs in that range')
        indent = ' ' * (12 if loop else 8)
        lines = [
            '# このファイルは録画から作った下書きです。待ち時間は試したときの間隔なので、画面の確認（isContainTemplate）に',
            '# 置き換えると安定します。',
            'from Commands.PythonCommandBase import ImageProcPythonCommand',
            'from Commands.Keys import Button, Direction, Hat, Stick, Touchscreen',
            '',
            '',
            'class Draft(ImageProcPythonCommand):',
            f'    NAME = {name!r}',
            '',
            '    def __init__(self, cam, gui=None):',
            '        super().__init__(cam, gui)',
            '',
            '    def do(self):',
        ]
        if loop:
            lines += ['        count = 0', '        while True:', '            count += 1', "            print(f'{count}回目')"]
        lines += [indent + line for line in body]
        return '\n'.join(lines) + '\n'
