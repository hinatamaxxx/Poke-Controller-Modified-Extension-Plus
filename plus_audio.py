"""Opening the capture board's sound, on top of the fork origin's Audio. MIT.

The fork origin opens an input by its name with WASAPI. On some PCs Windows' audio engine does not record (WASAPI,
DirectSound and MME all fail, and WASAPI may even hang), while kernel streaming (WDM-KS) still reads the board. So an
input is first tried briefly on its own thread, and when it does not open, the same device is opened through another
host API.

PortAudio learns the default output once, when it starts, so "the default playback device" would stay on the device that
was the default then (e.g. a TV) after Windows switched (e.g. to Steam's speakers while streaming). The default is read
from Windows each time playback opens, and when Windows reports that its default changed, playback reopens there.
"""
import re
import threading
from logging import getLogger

FALLBACK_APIS = ('Windows WDM-KS', 'Windows DirectSound', 'MME')
PROBE_SECONDS = 3  # how long opening an input may take before it counts as hung

_logger = getLogger(__name__)
_hung = set()  # (host API, name) whose opening never returned: not tried again in this process
_installed = False


def windows_default_output():
    """The name of Windows' default playback device now ('' when it cannot be read)."""
    import ctypes as c
    from WindowsDevices import GUID, method, release
    ole = c.OleDLL('ole32')
    initialize = c.windll.ole32.CoInitializeEx
    initialize.restype = c.c_long
    uninitialize = initialize(None, 0) >= 0
    enumerator, device, store = c.c_void_p(), c.c_void_p(), c.c_void_p()

    class PropertyKey(c.Structure):
        _fields_ = [('fmtid', GUID), ('pid', c.c_ulong)]

    class PropVariant(c.Structure):
        _fields_ = [('vt', c.c_ushort), ('reserved', c.c_ushort * 3), ('value', c.c_void_p), ('extra', c.c_void_p)]
    try:
        ole.CoCreateInstance(c.byref(GUID('BCDE0395-E52F-467C-8E3D-C4579291692E')), None, 1,
                             c.byref(GUID('A95664D2-9614-4F35-A746-DE8DB63617E6')), c.byref(enumerator))
        # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eMultimedia)
        if method(enumerator, 4, c.c_long, c.c_int, c.c_int, c.POINTER(c.c_void_p))(enumerator, 0, 1, c.byref(device)) < 0:
            return ''
        if method(device, 4, c.c_long, c.c_ulong, c.POINTER(c.c_void_p))(device, 0, c.byref(store)) < 0:  # STGM_READ
            return ''
        key = PropertyKey(GUID('A45C254E-DF1C-4EFD-8020-67D146A850E0'), 14)  # PKEY_Device_FriendlyName
        value = PropVariant()
        if method(store, 5, c.c_long, c.POINTER(PropertyKey), c.POINTER(PropVariant))(store, c.byref(key), c.byref(value)) < 0:
            return ''
        name = c.wstring_at(value.value) if value.vt == 31 and value.value else ''  # VT_LPWSTR
        ole.PropVariantClear(c.byref(value))
        return name
    except OSError as error:
        _logger.info(f'The default playback device could not be read: {error}')
        return ''
    finally:
        release(store)
        release(device)
        release(enumerator)
        if uninitialize:
            ole.CoUninitialize()


def follow_default(capture):
    """Reopen playback on Windows' default device when it changed (only when playing on "the default")."""
    if capture is None or capture.output_device_name or not capture.is_playing:
        return False
    name = windows_default_output()
    if not name or name == getattr(capture, 'opened_default', None):
        return False
    print(f'Audio: 既定の再生デバイスが {name} に変わったので、そちらで鳴らします')
    capture.set_playback(False)
    capture.set_playback(True)
    return True


_watcher = None  # keeps Windows' device notification registered for this process


def watch_default(get_capture, lock):
    """Ask Windows to tell when the default playback device changes (IMMNotificationClient), and then reopen
    playback on it. Nothing is checked periodically."""
    global _watcher
    import ctypes as c
    from WindowsDevices import GUID, method
    if _watcher is not None:
        return
    HRESULT, ULONG = c.c_long, c.c_ulong
    this = c.c_void_p

    def changed():
        with lock:
            try:
                follow_default(get_capture())
            except Exception as error:
                print(f'Audio: {error}')

    def query_interface(self, iid, out):
        c.cast(out, c.POINTER(c.c_void_p))[0] = self
        return 0

    def on_default(self, flow, role, device_id):
        if flow == 0 and role == 1:  # eRender, eMultimedia
            # Windows calls this on its own thread and must not be held up; reopening is done elsewhere.
            threading.Thread(target=changed, name='audio-default', daemon=True).start()
        return 0
    slots = [
        c.WINFUNCTYPE(HRESULT, this, c.c_void_p, c.c_void_p)(query_interface),
        c.WINFUNCTYPE(ULONG, this)(lambda self: 1),  # AddRef: kept for the life of the process
        c.WINFUNCTYPE(ULONG, this)(lambda self: 1),  # Release
        c.WINFUNCTYPE(HRESULT, this, c.c_wchar_p, c.c_ulong)(lambda *args: 0),  # OnDeviceStateChanged
        c.WINFUNCTYPE(HRESULT, this, c.c_wchar_p)(lambda *args: 0),  # OnDeviceAdded
        c.WINFUNCTYPE(HRESULT, this, c.c_wchar_p)(lambda *args: 0),  # OnDeviceRemoved
        c.WINFUNCTYPE(HRESULT, this, c.c_int, c.c_int, c.c_wchar_p)(on_default),  # OnDefaultDeviceChanged
        c.WINFUNCTYPE(HRESULT, this, c.c_wchar_p, c.c_void_p)(lambda *args: 0),  # OnPropertyValueChanged
    ]
    table = (c.c_void_p * len(slots))(*[c.cast(slot, c.c_void_p) for slot in slots])
    client = c.pointer(c.pointer(table))
    try:
        ole = c.OleDLL('ole32')
        c.windll.ole32.CoInitializeEx(None, 0)  # multithreaded: the notifications come on Windows' own thread
        enumerator = c.c_void_p()
        ole.CoCreateInstance(c.byref(GUID('BCDE0395-E52F-467C-8E3D-C4579291692E')), None, 1,
                             c.byref(GUID('A95664D2-9614-4F35-A746-DE8DB63617E6')), c.byref(enumerator))
        # IMMDeviceEnumerator::RegisterEndpointNotificationCallback
        if method(enumerator, 6, HRESULT, c.c_void_p)(enumerator, c.cast(client, c.c_void_p)) < 0:
            return
    except OSError as error:
        _logger.info(f'Changes of the default playback device cannot be followed: {error}')
        return
    _watcher = (slots, table, client, enumerator)


def plain_name(name):
    """The device name without what differs between host APIs ('(2- Cam Link 4K)' -> '(Cam Link 4K)')."""
    return re.sub(r'\(\d+- ', '(', name).strip()


def same_device(name, other, api):
    a, b = plain_name(name), plain_name(other)
    # MME cuts names at 31 characters.
    return a == b or (api == 'MME' and len(b) >= 20 and a.startswith(b))


def opens(sd, index, device, api, seconds=PROBE_SECONDS):
    """Whether the input opens (tried on a thread: a hung open does not hold the caller)."""
    key = (api, device['name'])
    if key in _hung:
        return False
    result = {}

    def run():
        try:
            stream = sd.InputStream(device=index, samplerate=int(device['default_samplerate']),
                                    channels=min(2, int(device['max_input_channels'])), dtype='float32',
                                    callback=lambda *args: None)  # WDM-KS opens only with a callback
            stream.close()
            result['ok'] = True
        except Exception as error:
            result['error'] = error

    thread = threading.Thread(target=run, name='audio-probe', daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        _hung.add(key)
        _logger.warning(f'Opening the audio input hung: {device["name"]} ({api})')
        return False
    if 'error' in result:
        _logger.info(f'The audio input does not open: {device["name"]} ({api}): {result["error"]}')
    return bool(result.get('ok'))


def install():
    """Let the fork origin's AudioCapture open an input through another host API when its own does not work."""
    global _installed
    import Audio
    if _installed or not Audio.AUDIO_AVAILABLE:
        return
    _installed = True
    sd, original = Audio.sd, Audio._find_input_device

    def api_name(device):
        return sd.query_hostapis(device['hostapi'])['name']

    def find_input_device(name):
        index, device = original(name)
        if opens(sd, index, device, api_name(device)):
            return index, device
        devices = list(enumerate(sd.query_devices()))
        for api in FALLBACK_APIS:
            for other_index, other in devices:
                if (other['max_input_channels'] > 0 and api_name(other) == api and same_device(name, other['name'], api)
                        and opens(sd, other_index, other, api)):
                    print(f'Audio: {name} を {api} で開きます（Windows の標準の方式では開けませんでした）')
                    return other_index, other
        return index, device  # the fork origin reports why it does not open

    Audio._find_input_device = find_input_device

    open_output = Audio.AudioCapture._open_output

    def open_output_on_the_default(capture):
        """For "the default", open Windows' default device now by its name (PortAudio's default may be stale)."""
        if capture.output_device_name:
            return open_output(capture)
        name = windows_default_output()
        capture.opened_default = name
        try:
            Audio._find_output_device(name)
        except Exception:
            return open_output(capture)  # not a device PortAudio knows: the fork origin's default
        capture.output_device_name = name
        try:
            return open_output(capture)
        finally:
            capture.output_device_name = ''

    Audio.AudioCapture._open_output = open_output_on_the_default
