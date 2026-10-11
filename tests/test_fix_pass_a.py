"""Final-review fix pass A: Windows entry script, PATH, helpers, catalog and CI details."""
import json
import re

from loadout import paths

PS1 = paths.kit_root() / "bootstrap.ps1"


def test_ps1_warning_names_the_full_wsl_url():
    assert ("Write-Warning 'Native Windows is experimental and not recommended. WSL 2 is the recommended setup on "
            "Windows: https://github.com/jonasyr/agent-loadout/blob/main/docs/how-to/wsl.md'") in PS1.read_text()


def test_ps1_never_exits_when_run_as_a_scriptblock():
    """The one-liner runs the script as a scriptblock: `exit` there closes the user's PowerShell window."""
    text = PS1.read_text()
    assert "$asFile = [bool]$PSCommandPath" in text
    code = [l for l in text.splitlines() if not l.lstrip().startswith("#")]
    for line in code:
        if re.search(r"\bexit\b", line):
            assert "if ($asFile)" in line, line
    assert not any("Write-Error" in l for l in code)  # under 'Stop' it throws instead of returning
    assert "$global:LASTEXITCODE = $code" in text
    assert "Set-Location" not in text  # Push/Pop-Location: the user's folder is left as it was
