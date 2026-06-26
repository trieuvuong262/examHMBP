#!/usr/bin/env python3
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
import django
django.setup()
from nas_storage.nas_acl_apply import _run_ssh_commands
cmds = [
    "id tailscale-justplay 2>&1 || echo NO_LOCAL_USER",
    "getent passwd tailscale-justplay 2>&1 | head -1",
    "synouser --get tailscale-justplay 2>&1 | head -30",
    "cat /etc/samba/smb.conf 2>/dev/null | grep -E \"^(workgroup|security|passdb)\" | head -10",
]
print(_run_ssh_commands(cmds))
