from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    assert "%LOCALAPPDATA%\\anthos\\anthos-agent\\venv\\Scripts" in doc
    assert "Get-Command anthos        # should print C:\\Users\\<you>\\AppData\\Local\\anthos\\anthos-agent\\venv\\Scripts\\anthos.exe" in doc
    assert '$anthosBin = "$InstallDir\\venv\\Scripts"' in install
