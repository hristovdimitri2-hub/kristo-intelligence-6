"""
create_shortcut.py
==================
Creates a desktop shortcut "Kristo Intelligence Dashboard.url" on the current
Windows user's Desktop. The shortcut points to the live Render dashboard:

    https://kristo-intelligence-api.onrender.com/dashboard

Run:
    python create_shortcut.py
"""

import os
import sys

SHORTCUT_NAME = "Kristo Intelligence Dashboard.url"
TARGET_URL = "https://kristo-intelligence-api.onrender.com/dashboard"
ICON_PATH = ""  # Uses default browser icon if empty


def get_desktop_path() -> str:
    """Return the current user's Desktop path."""
    # On Windows, USERPROFILE points to C:\\Users\\<Username>
    userprofile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    desktop = os.path.join(userprofile, "Desktop")
    if not os.path.isdir(desktop):
        # Fallback: try OneDrive Desktop
        onedrive_desktop = os.path.join(userprofile, "OneDrive", "Desktop")
        if os.path.isdir(onedrive_desktop):
            desktop = onedrive_desktop
    return desktop


def create_url_shortcut(desktop_path: str, name: str, url: str, icon: str = "") -> str:
    """
    Create a .url shortcut file on the Desktop.

    A .url file is a simple INI-style text file that Windows treats as a
    web shortcut. This avoids needing winshell/pywin32 dependencies.
    """
    shortcut_path = os.path.join(desktop_path, name)

    content_lines = [
        "[InternetShortcut]",
        f"URL={url}",
    ]
    if icon:
        content_lines.append(f"IconFile={icon}")
        content_lines.append("IconIndex=0")

    content = "\r\n".join(content_lines) + "\r\n"

    with open(shortcut_path, "w", encoding="utf-8") as f:
        f.write(content)

    return shortcut_path


def create_lnk_shortcut(desktop_path: str, name: str, url: str) -> str:
    """
    Create a .lnk shortcut using PowerShell (no extra Python deps needed).
    Falls back to .url if PowerShell COM is unavailable.
    """
    lnk_path = os.path.join(desktop_path, name.replace(".url", ".lnk"))

    # PowerShell script to create a .lnk shortcut pointing to the URL
    ps_script = f'''
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{lnk_path}")
$Shortcut.TargetPath = "{url}"
$Shortcut.Save()
'''

    import subprocess
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return lnk_path
    except Exception as exc:
        print(f"  [WARN] Could not create .lnk via PowerShell ({exc}), using .url instead.")
        return create_url_shortcut(desktop_path, name, url)


def main():
    print("=" * 60)
    print("  Kristo Intelligence Dashboard - Desktop Shortcut Creator")
    print("=" * 60)

    desktop = get_desktop_path()
    print(f"  Desktop path : {desktop}")

    if not os.path.isdir(desktop):
        print(f"  [ERROR] Desktop directory not found: {desktop}")
        sys.exit(1)

    # Try .lnk first (nicer icon), fall back to .url
    print(f"  Target URL   : {TARGET_URL}")
    print(f"  Shortcut name: {SHORTCUT_NAME}")
    print("-" * 60)

    try:
        result_path = create_lnk_shortcut(desktop, SHORTCUT_NAME, TARGET_URL)
    except Exception:
        result_path = create_url_shortcut(desktop, SHORTCUT_NAME, TARGET_URL)

    if os.path.exists(result_path):
        print(f"  [OK] Shortcut created successfully!")
        print(f"  Path: {result_path}")
        print()
        print("  The icon should now be visible on your Desktop.")
        print("  Double-click it to open the Kristo Intelligence Dashboard.")
    else:
        print(f"  [ERROR] Failed to create shortcut at {result_path}")
        sys.exit(1)

    print("=" * 60)


if __name__ == "__main__":
    main()