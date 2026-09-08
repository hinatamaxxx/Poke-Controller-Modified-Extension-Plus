"""Use the same SDL DLL as pygame; no hardware events or controller output."""
import ctypes as c
from pathlib import Path
import os
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
os.environ.setdefault('SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS', '1')
import pygame


class VirtualPads:
    def __init__(self, count=1):
        self.count = count
        self.indices, self.handles, self.sticks = [], [], []
        self.sdl = c.CDLL(str(Path(pygame.__file__).parent / 'SDL2.dll'))
        for name, result, args in (
            ('SDL_JoystickAttachVirtual', c.c_int, [c.c_int, c.c_int, c.c_int, c.c_int]),
            ('SDL_JoystickDetachVirtual', c.c_int, [c.c_int]),
            ('SDL_JoystickOpen', c.c_void_p, [c.c_int]),
            ('SDL_JoystickClose', None, [c.c_void_p]),
            ('SDL_JoystickSetVirtualAxis', c.c_int, [c.c_void_p, c.c_int, c.c_int16]),
            ('SDL_JoystickSetVirtualButton', c.c_int, [c.c_void_p, c.c_int, c.c_uint8]),
            ('SDL_JoystickSetVirtualHat', c.c_int, [c.c_void_p, c.c_int, c.c_uint8]),
        ):
            function = getattr(self.sdl, name)
            function.restype, function.argtypes = result, args

    def __enter__(self):
        pygame.display.init()
        pygame.joystick.init()
        try:
            for _ in range(self.count):
                index = self.sdl.SDL_JoystickAttachVirtual(1, 6, 16, 1)
                if index < 0:
                    raise RuntimeError('Virtual joystick unavailable')
                self.indices.append(index)
                self.handles.append(self.sdl.SDL_JoystickOpen(index))
                self.sticks.append(pygame.joystick.Joystick(index))
            pygame.event.get()
            return self
        except Exception:
            self.__exit__()
            raise

    def detach(self, number):
        if self.indices[number] >= 0:
            self.sdl.SDL_JoystickDetachVirtual(self.indices[number])
            self.indices[number] = -1

    def __exit__(self, *args):
        for stick in self.sticks:
            stick.quit()
        for handle in self.handles:
            self.sdl.SDL_JoystickClose(handle)
        for number in reversed(range(len(self.indices))):
            self.detach(number)
        pygame.joystick.quit()
        pygame.display.quit()
