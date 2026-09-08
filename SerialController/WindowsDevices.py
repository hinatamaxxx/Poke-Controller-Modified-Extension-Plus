"""Enumerate DirectShow monikers using Windows COM, without a managed DLL.

The enumeration order is the same category used by OpenCV CAP_DSHOW.
DevicePath disambiguates devices with identical friendly names.
"""
import ctypes as c
import uuid
import hashlib
import os
import tempfile
from pathlib import Path


class GUID(c.Structure):
    _fields_ = [("data", c.c_ubyte * 16)]

    def __init__(self, value):
        super().__init__()
        self.data[:] = uuid.UUID(value).bytes_le


class Variant(c.Structure):
    _fields_ = [("vt", c.c_ushort), ("reserved", c.c_ushort * 3),
                ("value", c.c_void_p), ("extra", c.c_void_p)]


def method(obj, index, result, *args):
    table = c.cast(obj, c.POINTER(c.POINTER(c.c_void_p))).contents
    return c.WINFUNCTYPE(result, c.c_void_p, *args)(table[index])


def release(obj):
    if obj:
        method(obj, 2, c.c_ulong)(obj)


def enumerate_cameras():
    ole = c.OleDLL("ole32")
    automation = c.OleDLL("oleaut32")
    hr = ole.CoInitializeEx(None, 2)
    uninitialize = hr >= 0
    devices, enumerator = c.c_void_p(), c.c_void_p()
    result = []
    try:
        cls = GUID("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")
        iid = GUID("29840822-5B84-11D0-BD3B-00A0C911CE86")
        category = GUID("860BB310-5D01-11D0-BD3B-00A0C911CE86")
        bag_iid = GUID("55272A00-42CB-11CE-8135-00AA004BB851")
        ole.CoCreateInstance(c.byref(cls), None, 1, c.byref(iid), c.byref(devices))
        hr = method(devices, 3, c.c_long, c.POINTER(GUID), c.POINTER(c.c_void_p), c.c_ulong)(
            devices, c.byref(category), c.byref(enumerator), 0)
        if hr == 1:
            return []
        if hr < 0:
            raise OSError(f"CreateClassEnumerator: {hr:#x}")
        while True:
            moniker, bag = c.c_void_p(), c.c_void_p()
            fetched = c.c_ulong()
            hr = method(enumerator, 3, c.c_long, c.c_ulong, c.POINTER(c.c_void_p), c.POINTER(c.c_ulong))(
                enumerator, 1, c.byref(moniker), c.byref(fetched))
            if hr != 0:
                break
            try:
                hr = method(moniker, 9, c.c_long, c.c_void_p, c.c_void_p, c.POINTER(GUID), c.POINTER(c.c_void_p))(
                    moniker, None, None, c.byref(bag_iid), c.byref(bag))
                values = {}
                if hr >= 0:
                    for key in ("FriendlyName", "DevicePath"):
                        value = Variant()
                        hr = method(bag, 3, c.c_long, c.c_wchar_p, c.POINTER(Variant), c.c_void_p)(
                            bag, key, c.byref(value), None)
                        if hr >= 0 and value.vt == 8:
                            values[key] = c.wstring_at(value.value)
                        automation.VariantClear(c.byref(value))
                index = len(result)
                result.append({"index": index, "name": values.get("FriendlyName", f"Camera {index}"),
                               "path": values.get("DevicePath", "")})
            finally:
                release(bag)
                release(moniker)
        return result
    finally:
        release(enumerator)
        release(devices)
        if uninitialize:
            ole.CoUninitialize()


class CameraLease:
    def __init__(self, identity):
        import msvcrt
        folder = Path(tempfile.gettempdir()) / "poke-plus-device-locks"
        folder.mkdir(exist_ok=True)
        path = folder / (hashlib.sha256(identity.encode()).hexdigest() + ".lock")
        self.file = open(path, "a+b")
        self.file.seek(0)
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.file.close()
            raise RuntimeError("このキャプチャ機器は別の機体で使用中です。")

    def close(self):
        self.file.close()
