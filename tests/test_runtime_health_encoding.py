# SPDX-License-Identifier: AGPL-3.0-only
"""The actual health-probe program must survive a legacy Windows encoding."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest


class RuntimeEncodingTests(unittest.TestCase):
    def test_chinese_runtime_prefix_is_ascii_json_even_on_a_gbk_stdout(self):
        source = Path(__file__).resolve().parents[1] / 'payload/utils/environment_lifecycle.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        method = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'managed_runtime_health')
        assignment = next(node for node in method.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'code' for t in node.targets))
        probe = ast.literal_eval(assignment.value)
        prefix = str(Path.cwd() / '中文目录' / 'runtime')
        setup = ('import sys, importlib, types, os; sys.stdout.reconfigure(encoding="gbk"); '
                 f'sys.prefix={prefix!r}; '
                 'importlib.import_module=lambda name: types.SimpleNamespace(__file__=os.path.join(sys.prefix,"Lib",name+".py")); ')
        result = subprocess.run([sys.executable, '-I', '-c', setup + probe], capture_output=True, check=True)
        result.stdout.decode('ascii')
        payload = json.loads(result.stdout.decode('utf-8'))
        self.assertTrue(payload['ok'])
        self.assertIn('中文目录', payload['root'])


if __name__ == '__main__':
    unittest.main()
