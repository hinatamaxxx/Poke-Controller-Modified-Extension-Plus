"""Working together with an AI assistant: status line, notes, activity log, button sequences and template checks. MIT."""
import collections
import json
import os
import threading
import time
import uuid

MAX_STEPS = 200
MAX_SEQUENCE_SECONDS = 600
MAX_NOTES = 200


class Assist:
    def __init__(self, core, profile_dir):
        self.core = core
        self.notes_path = os.path.join(profile_dir, 'notes.json')
        self.status = {'task': '', 'doing': '', 'progress': '', 'text': '', 'at': 0}
        self.activity = collections.deque(maxlen=100)
        self.notes = self._load_notes()
        self.sequence = None  # {'id', 'total', 'done', 'cancel': Event, 'thread'}

    # ---- status shown at the top of the browser UI ----
    def set_status(self, doing='', task='', progress=''):
        """task: the goal in game terms; doing: what is happening in the game right now; progress: e.g. "12/50"."""
        doing, task, progress = (str(v or '').strip() for v in (doing, task, progress))
        text = ' / '.join(part for part in (task, doing + (f'（{progress}）' if progress else '')) if part)
        self.status = {'task': task[:120], 'doing': doing[:200], 'progress': progress[:40], 'text': text[:300], 'at': time.time()}

    # ---- activity: what the assistant did, for the user to follow ----
    def record(self, source, text):
        self.activity.append({'at': time.time(), 'source': source, 'text': str(text)[:300]})

    # ---- notes kept per profile (notes.json beside settings.ini) ----
    def _load_notes(self):
        try:
            with open(self.notes_path, encoding='utf-8') as stream:
                data = json.load(stream)
            return [n for n in data if isinstance(n, dict) and 'text' in n][-MAX_NOTES:]
        except (OSError, ValueError):
            return []

    def _save_notes(self):
        from safe_settings import write_text
        write_text(self.notes_path, json.dumps(self.notes, ensure_ascii=False, indent=1))

    def add_note(self, text, author):
        text = str(text or '').strip()
        if not text:
            raise ValueError('Note is empty')
        note = {'id': uuid.uuid4().hex[:8], 'at': time.time(), 'author': author, 'text': text[:2000]}
        self.notes = (self.notes + [note])[-MAX_NOTES:]
        self._save_notes()
        return note

    def delete_note(self, note_id):
        before = len(self.notes)
        self.notes = [n for n in self.notes if n.get('id') != note_id]
        if len(self.notes) == before:
            raise ValueError('Note not found')
        self._save_notes()

    # ---- button sequences run here, so timing does not depend on round trips ----
    def run_sequence(self, steps, check, hold, release, neutral):
        """steps: [{'buttons': [...], 'duration': s, 'wait': s}]. Returns a sequence ID; runs in the background."""
        from local_control import MIN_PRESS, MAX_PRESS, parse_inputs
        if self.sequence and self.sequence['thread'].is_alive():
            raise ValueError('A sequence is already running')
        if not isinstance(steps, list) or not 0 < len(steps) <= MAX_STEPS:
            raise ValueError(f'steps must be a list of 1-{MAX_STEPS} items')
        parsed, total = [], 0.0
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError('Each step must be an object')
            buttons = parse_inputs(step['buttons']) if step.get('buttons') else []
            duration = float(step.get('duration', .1))
            wait = float(step.get('wait', .1))
            if buttons and not MIN_PRESS <= duration <= MAX_PRESS:
                raise ValueError(f'duration must be {MIN_PRESS}-{MAX_PRESS} seconds')
            if not 0 <= wait <= 30:
                raise ValueError('wait must be 0-30 seconds')
            parsed.append((buttons, duration if buttons else 0, wait))
            total += (duration if buttons else 0) + wait
        if total > MAX_SEQUENCE_SECONDS:
            raise ValueError(f'The sequence is longer than {MAX_SEQUENCE_SECONDS} seconds')
        check()
        cancel = threading.Event()
        info = {'id': uuid.uuid4().hex[:8], 'total': len(parsed), 'done': 0, 'cancel': cancel, 'error': ''}

        def run():
            try:
                for buttons, duration, wait in parsed:
                    if cancel.is_set():
                        break
                    if buttons:
                        with self.core.lock:
                            check()
                            held = hold(buttons)
                        cancel.wait(duration)
                        with self.core.lock:
                            release(held)
                    if cancel.wait(wait):
                        break
                    info['done'] += 1
            except Exception as exc:
                info['error'] = str(exc)
            finally:
                with self.core.lock:
                    try:
                        neutral()
                    except Exception as exc:  # e.g. the port was lost mid-sequence
                        info['error'] = info['error'] or str(exc)
        info['thread'] = threading.Thread(target=run, daemon=True)
        self.sequence = info
        info['thread'].start()
        return info['id']

    def cancel_sequence(self):
        if self.sequence and self.sequence['thread'].is_alive():
            self.sequence['cancel'].set()

    def sequence_state(self):
        info = self.sequence
        if not info:
            return None
        return {'id': info['id'], 'running': info['thread'].is_alive(), 'done': info['done'], 'total': info['total'],
                'error': info['error']}

    # ---- templates: is this image on screen now? ----
    def templates(self):
        import script_files
        return script_files.image_names()

    def find_template(self, name, threshold=0.85, show=True):
        """Match a template (in Template, or "スクリプト/...") against the current frame (grayscale, like isContainTemplate)."""
        import cv2
        import script_files
        from ImageProcessing import getImage
        path = script_files.image_path(name)
        frame = self.core.camera.readFrame()
        if frame is None:
            raise ValueError('No live camera frame')
        template = getImage(path, mode='gray')
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if template.shape[0] > gray.shape[0] or template.shape[1] > gray.shape[1]:
            raise ValueError('The template is larger than the camera frame')
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, best, _, (x, y) = cv2.minMaxLoc(result)
        h, w = template.shape[:2]
        found = best >= float(threshold)
        recorder = getattr(self.core, 'recorder', None)
        if recorder is not None:
            recorder.note({'action': 'check', 'template': str(name), 'threshold': float(threshold),
                           'found': bool(found), 'similarity': round(float(best), 3)})
        if show:
            self.core.overlay.ImgRect(x, y, x + w, y + h, outline='green' if found else 'orange', tag='assist-find', ms=2500)
        return {'found': bool(found), 'similarity': round(float(best), 4), 'x': int(x), 'y': int(y), 'width': int(w), 'height': int(h)}

    def snapshot(self):
        recent = time.time() - self.status['at'] < 3600
        return {'status': self.status if recent and (self.status['doing'] or self.status['task']) else None,
                'activity': list(self.activity)[-50:], 'notes': self.notes, 'sequence': self.sequence_state()}
