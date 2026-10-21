"""Install a reversible, local launchd collection schedule without cloud services."""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from observatory.settings import get_settings

LABEL = "local.battleground-senate-observatory.collect"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--publish-web", action="store_true", help="Collect, validate and publish the configured free website")
    parser.add_argument("--defer-first-run", action="store_true", help="Begin at the next interval after a manually verified first deployment")
    args = parser.parse_args()
    settings = get_settings()
    settings.prepare()
    target = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    domain = f"gui/{os.getuid()}"
    if args.remove:
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], check=False, capture_output=True)
        target.unlink(missing_ok=True)
        print(f"Removed {LABEL}; evidence and research data retained.")
        return
    arguments = [str(settings.project_root / ".venv" / "bin" / "python"), "-m", "observatory.cli", "collect", "--due", "--warm-forecasts"]
    environment = {"OBSERVATORY_DATA_DIR": str(settings.data_dir)}
    if args.publish_web:
        if not (settings.data_dir / "web-publishing.json").exists():
            raise SystemExit("Verify the first website deployment and configure web-publishing.json before scheduling it")
        arguments = [str(settings.project_root / ".venv" / "bin" / "python"), str(settings.project_root / "scripts" / "update_web.py")]
        directories = [str(Path(executable).parent) for command in ("node", "pnpm") if (executable := shutil.which(command))]
        environment["PATH"] = ":".join(dict.fromkeys(directories + [str(settings.project_root / ".venv" / "bin"), "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]))
    payload = {"Label": LABEL,
               "ProgramArguments": arguments,
               "WorkingDirectory": str(settings.project_root), "RunAtLoad": not args.defer_first_run, "StartInterval": 7200,
               "EnvironmentVariables": environment,
               "StandardOutPath": str(settings.data_dir / "collector.log"),
               "StandardErrorPath": str(settings.data_dir / "collector-errors.log"),
               "ProcessType": "Background", "LowPriorityIO": True}
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], check=False, capture_output=True)
    target.write_bytes(plistlib.dumps(payload))
    subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=True)
    print(f"Installed {target}. Checks every two hours while the Mac is available; --remove uninstalls only the schedule.")


if __name__ == "__main__":
    main()
