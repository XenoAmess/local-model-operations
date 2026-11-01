"""Focused boundaries of the zero-owned-file configuration; no model calls."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from opencode_config import ConfigError, build_config
from opencode_readonly_config import build_readonly_config, isolated_environment


class ReadonlyConfigTests(unittest.TestCase):
    def setUp(self):
        self.executor = {'base_url': 'http://127.0.0.1:8080/v1', 'model': 'fixture'}

    def test_zero_edit_scope_and_source_coordinates(self):
        original = copy.deepcopy(self.executor)
        config = build_readonly_config(self.executor, source_root='D:/Project/java')
        permission = config['permission']
        self.assertEqual(permission['*'], 'deny')
        self.assertNotIn('edit', permission)
        self.assertNotIn('write', permission)
        self.assertEqual(permission['read'], {'*': 'deny', 'Project/java/**': 'allow'})
        self.assertEqual(permission['external_directory'], {
            '*': 'deny', 'd:/Project/java/**': 'allow', 'D:/Project/java/**': 'allow'})
        self.assertEqual(permission['invalid'], 'allow')
        self.assertEqual(self.executor, original)
        config['agent']['pilot']['permission']['read']['*'] = 'allow'
        self.assertEqual(permission['read']['*'], 'deny')

    def test_reject_scope_expansion_and_preserve_edit_entry_contract(self):
        for root in ['D:/', '/', 'D:relative', 'D:/Project/../other', 'D:/Project/*', 'D:/Project/.git']:
            with self.subTest(root=root), self.assertRaises(ConfigError):
                build_readonly_config(self.executor, source_root=root)
        with self.assertRaises(ConfigError):
            build_config(self.executor, workspace='D:/Project', worktree='D:/', owned_files=[])
        edit = build_config(self.executor, workspace='D:/Project', worktree='D:/',
                            owned_files=['one.py', 'two.py'])
        self.assertEqual(edit['permission']['edit'], {
            '*': 'deny', 'Project/one.py': 'allow', 'Project/two.py': 'allow'})

    def test_native_parameters_and_finite_reply_without_total_quota(self):
        config = build_readonly_config(self.executor, source_root='/project/java', max_output_tokens=8000)
        model = config['provider']['pilot']['models']['fixture']
        self.assertEqual(model['limit']['output'], 8000)
        self.assertTrue(model['temperature'])
        self.assertEqual(config['agent']['pilot']['temperature'], 0)
        self.assertEqual(model['options']['stream_options'], {'include_usage': True})
        self.assertEqual(model['options']['chat_template_kwargs'], {'enable_thinking': False})
        for field in ['maxOutputTokens', 'maxRetries', 'response_format']:
            self.assertNotIn(field, model['options'])
        for field in ['steps', 'maxSteps']:
            self.assertNotIn(field, config['agent']['pilot'])
        with self.assertRaises(ConfigError):
            build_readonly_config(self.executor, source_root='/project/java', max_output_tokens=True)

    def test_environment_disables_parent_config_and_inline_overrides(self):
        env = isolated_environment(config='one.json', config_dir='config', data_dir='data',
                                   state_dir='state', cache_dir='shared-cache')
        self.assertEqual(env['OPENCODE_DISABLE_PROJECT_CONFIG'], 'true')
        self.assertEqual(env['OPENCODE_CONFIG_CONTENT'], '')
        self.assertEqual(env['OPENCODE_PERMISSION'], '')
        self.assertEqual(env['XDG_CACHE_HOME'], 'shared-cache')
        self.assertEqual(env['OPENCODE_CONFIG'], 'one.json')


if __name__ == '__main__':
    unittest.main()
