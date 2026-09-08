"""Hardware-free script used for validating the packaged app and MCP."""
from Commands.PythonCommandBase import PythonCommand


class PortableDemo(PythonCommand):
    NAME = 'PortableDemo / ボタン送信なし'

    def do(self):
        counter = 0
        while True:
            counter += 1
            self.print_t(f'PortableDemo: {counter}')
            self.wait(.5)
