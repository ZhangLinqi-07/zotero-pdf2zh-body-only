# SPDX-License-Identifier: AGPL-3.0-only
"""Register the managed loopback backend at Windows user logon."""
import json
import os
from pathlib import Path
import subprocess
import sys


def configure(root, port, host='127.0.0.1'):
    if sys.platform != 'win32' or host not in {'127.0.0.1', 'localhost'}:
        return {'state': 'unsupported', 'message': '自动启动仅适用于 Windows 本机后台'}
    root = Path(root).resolve()
    task_name = f'Kinbo Backend ({port})'
    try:
        settings = json.loads((root / '.body-only-launch.json').read_text(encoding='utf-8'))
        pythonw = Path(settings['server_python']).with_name('pythonw.exe')
        launcher = root / 'run_body_only.py'
        if not pythonw.is_file() or not launcher.is_file():
            raise ValueError('Missing managed launcher')
        arguments = subprocess.list2cmdline([str(launcher), '--server-dir', str(root), '--port', str(port)])
        def literal(value):
            return "'" + str(value).replace("'", "''") + "'"
        script = f"""$ErrorActionPreference = 'Stop'
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute {literal(pythonw)} -Argument {literal(arguments)} -WorkingDirectory {literal(root)}
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName {literal(task_name)} -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Kinbo local backend: start silently at user logon; retry on failure.' -Force | Out-Null
"""
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise OSError('Task registration failed')
        return {'state': 'enabled', 'taskName': task_name, 'message': '已启用 Windows 登录后静默启动，异常退出每分钟重试，最多三次'}
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return {'state': 'failed', 'taskName': task_name,
                'message': 'Windows 自动启动配置失败，请检查计划任务权限；当前后台仍可继续使用'}
