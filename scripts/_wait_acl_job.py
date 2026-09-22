"""Wait until apply_nas_acl_all exits, then print the job log."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

LOG = Path('/tmp/nas_acl_apply.log')


def job_running() -> bool:
    out = subprocess.check_output(['ps', 'aux'], text=True, errors='replace')
    return any('apply_nas_acl_all' in line and 'grep' not in line for line in out.splitlines())


def main() -> None:
    for i in range(160):
        running = job_running()
        print(f'{i} running={running}', flush=True)
        if not running:
            text = LOG.read_text(errors='replace') if LOG.exists() else ''
            print(text[-3000:])
            return
        time.sleep(15)
    print('TIMEOUT')
    if LOG.exists():
        print(LOG.read_text(errors='replace')[-800:])


if __name__ == '__main__':
    main()
