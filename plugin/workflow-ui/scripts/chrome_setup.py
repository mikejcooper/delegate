#!/usr/bin/env python3
"""Which steps of the external-browser (Claude in Chrome) setup are already done on this computer, so the
connections manager's tutorial only asks for the rest (core-connections, "Chrome").

    chrome_setup.py            prints one JSON object

Reads local files only, never the network, and changes nothing:
  - a Chromium browser installed (Chrome, Edge, Brave, Arc, Chrome Canary)
  - the Claude in Chrome extension in one of its profiles, and whether that profile has it turned off
  - the native messaging host Claude Code installs the first time it connects to the extension
  - the Claude desktop app's config (claude_desktop_config.json): its Claude in Chrome connector switched on
    (Settings > Customize > Connectors > Claude in Chrome) and a browser paired with it before
  - ~/.claude.json, for the terminal: the onboarding done and "Enabled by default" (/chrome)

The tutorial is for the Claude desktop app; where there is no desktop app config, the terminal's settings stand in.

Whether this session has the tools is not a file: the connections manager sees it (its mcp__claude-in-chrome__*
tools), and that step is done when they are there.

The result: {"surface": "desktop" | "cli", "browsers", "extension": {"installed", "enabled", "profiles"},
"desktop": {"connector_on", "paired"}, "native_host", "onboarded", "default_enabled", "steps": {"install", "sign_in", "allow", "new_session"}: "done" | "todo" | "unknown", "todo": [...]}
"""
import glob
import json
import os
import sys

EXT = "fcoeoabgfenejglbffodgkkbkcdhcgfn"   # Claude in Chrome on the Chrome Web Store
HOSTS = ("com.anthropic.claude_code_browser_extension.json", "com.anthropic.claude_browser_extension.json")


def roots():
    """{browser name: its user data folder} for this platform."""
    h = os.path.expanduser("~")
    if sys.platform == "darwin":
        a = os.path.join(h, "Library", "Application Support")
        return {"Chrome": f"{a}/Google/Chrome", "Chrome Canary": f"{a}/Google/Chrome Canary",
                "Edge": f"{a}/Microsoft Edge", "Brave": f"{a}/BraveSoftware/Brave-Browser", "Arc": f"{a}/Arc/User Data"}
    if os.name == "nt":
        a = os.environ.get("LOCALAPPDATA", os.path.join(h, "AppData", "Local"))
        return {"Chrome": f"{a}/Google/Chrome/User Data", "Edge": f"{a}/Microsoft/Edge/User Data",
                "Brave": f"{a}/BraveSoftware/Brave-Browser/User Data"}
    c = os.path.join(h, ".config")
    return {"Chrome": f"{c}/google-chrome", "Edge": f"{c}/microsoft-edge", "Brave": f"{c}/BraveSoftware/Brave-Browser"}


def load(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def desktop_config():
    """The Claude desktop app's claude_desktop_config.json, or None when there is no desktop app here."""
    h = os.path.expanduser("~")
    d = (os.path.join(h, "Library", "Application Support", "Claude") if sys.platform == "darwin" else
         os.path.join(os.environ.get("APPDATA", os.path.join(h, "AppData", "Roaming")), "Claude") if os.name == "nt" else
         os.path.join(h, ".config", "Claude"))
    p = os.path.join(d, "claude_desktop_config.json")
    return load(p) if os.path.isfile(p) else None


def profile_name(prof):
    return ((load(os.path.join(prof, "Preferences")).get("profile") or {}).get("name")) or os.path.basename(prof)


def main():
    browsers, profiles, host = [], [], False
    for name, root in roots().items():
        if not os.path.isdir(root):
            continue
        browsers.append(name)
        if any(os.path.isfile(os.path.join(root, "NativeMessagingHosts", f)) for f in HOSTS):
            host = True
        for d in glob.glob(os.path.join(root, "*", "Extensions", EXT)):
            prof = os.path.dirname(os.path.dirname(d))
            s = ((load(os.path.join(prof, "Secure Preferences")).get("extensions") or {}).get("settings") or {}).get(EXT) \
                or ((load(os.path.join(prof, "Preferences")).get("extensions") or {}).get("settings") or {}).get(EXT) or {}
            off = bool(s.get("disable_reasons")) or s.get("state") == 0
            profiles.append({"browser": name, "profile": profile_name(prof), "enabled": not off})
    cfg = load(os.path.expanduser("~/.claude.json"))
    installed, enabled = bool(profiles), any(p["enabled"] for p in profiles)
    onboarded = bool(cfg.get("hasCompletedClaudeInChromeOnboarding"))
    default_on = bool(cfg.get("claudeInChromeDefaultEnabled"))
    dc = desktop_config()
    pref = (dc or {}).get("preferences") or {}
    conn_on, paired = bool(pref.get("chromeExtensionEnabled")), bool((pref.get("chromeExtension") or {}).get("pairedDeviceId"))
    surface = "desktop" if dc is not None else "cli"
    was_connected = paired if surface == "desktop" else onboarded
    steps = {
        "install": "done" if enabled else "todo",                    # installed and turned on in a Chrome profile
        "sign_in": "done" if enabled and was_connected else "unknown" if enabled else "todo",
        # the app may use it: the desktop's connector switched on; the terminal's /chrome on by default
        "allow": "done" if (conn_on if surface == "desktop" else host and default_on) else "todo",
        "new_session": "unknown",                                     # the session's own tools say
    }
    print(json.dumps({"surface": surface, "browsers": browsers,
                      "extension": {"installed": installed, "enabled": enabled, "profiles": profiles},
                      "desktop": {"connector_on": conn_on, "paired": paired} if dc is not None else None,
                      "native_host": host, "onboarded": onboarded, "default_enabled": default_on,
                      "steps": steps, "todo": [k for k, v in steps.items() if v == "todo"]}, indent=1))

if __name__ == "__main__":
    main()
