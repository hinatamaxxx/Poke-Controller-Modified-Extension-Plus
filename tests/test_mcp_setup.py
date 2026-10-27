import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import library_update
import mcp_setup


class McpSetupTest(unittest.TestCase):
    def test_entry_prefers_packaged_exe(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(mcp_setup.server_entry(folder)['args'], [str(Path(folder).resolve() / 'controller_mcp.py')])
            (Path(folder) / 'PokeControllerMCP.exe').touch()
            entry = mcp_setup.server_entry(folder)
            self.assertEqual(entry, {'command': str(Path(folder).resolve() / 'PokeControllerMCP.exe'), 'args': []})

    def test_claude_code_command_quotes_spaces(self):
        with tempfile.TemporaryDirectory(prefix='with space ') as folder:
            (Path(folder) / 'PokeControllerMCP.exe').touch()
            command = mcp_setup.claude_code_command(folder)
            self.assertTrue(command.startswith('claude mcp add --scope user poke-controller -- "'))

    def test_register_keeps_other_settings_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'claude_desktop_config.json'
            original = {'preferences': {'x': True}, 'mcpServers': {'other': {'command': 'a'}}}
            config.write_text(json.dumps(original), encoding='utf-8')
            mcp_setup.register_desktop(config, folder)
            data = json.loads(config.read_text(encoding='utf-8'))
            self.assertEqual(data['preferences'], {'x': True})
            self.assertEqual(data['mcpServers']['other'], {'command': 'a'})
            self.assertIn('poke-controller', data['mcpServers'])
            self.assertEqual(json.loads(config.with_name(config.name + '.bak').read_text(encoding='utf-8')), original)

    def test_register_rejects_unexpected_format(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'claude_desktop_config.json'
            config.write_text('{"mcpServers": []}', encoding='utf-8')
            with self.assertRaises(ValueError):
                mcp_setup.register_desktop(config, folder)
            self.assertEqual(config.read_text(encoding='utf-8'), '{"mcpServers": []}')


class PruneRuntimesTest(unittest.TestCase):
    def test_removes_unused_runtimes_only(self):
        with tempfile.TemporaryDirectory() as folder:
            updates = Path(folder) / '.runtime-updates'
            keep, old = updates / ('a' * 32), updates / ('b' * 32)
            for path in (keep, old, updates / 'leftover.delete', updates / 'other'):
                path.mkdir(parents=True)
                (path / 'python.exe').touch()
            library_update.prune_runtimes(folder, [keep])
            self.assertEqual(sorted(p.name for p in updates.iterdir()), ['a' * 32, 'other'])


if __name__ == '__main__':
    unittest.main()
