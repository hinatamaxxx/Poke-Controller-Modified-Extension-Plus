"""Opening the capture board's sound, on top of the fork origin's Audio. MIT.

The fork origin opens an input by its name with WASAPI. On some PCs Windows' audio engine does not record (WASAPI,
DirectSound and MME all fail, and WASAPI may even hang), while kernel streaming (WDM-KS) still reads the board. So an
input is first tried briefly on its own thread, and when it does not open, the same device is opened through another
host API.
"""
import re
import threading
from logging import getLogger

FALLBACK_APIS = ('Windows WDM-KS', 'Windows DirectSound', 'MME')
PROBE_SECONDS = 3  # how long opening an input may take before it counts as hung

_logger = getLogger(__name__)
_hung = set()  # (host API, name) whose opening never returned: not tried again in this process
_installed = False


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
