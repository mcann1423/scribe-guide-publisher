"""Visible-browser assistant for exporting guides through Scribe's normal UI.

The user's Microsoft Edge profile used here is a separate local profile.  Login,
MFA, and Scribe permissions remain in the browser; this program never receives a
password or calls Scribe's undocumented APIs.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request


WORKSPACE_URL = "https://scribehow.com/workspace"


@dataclass(frozen=True)
class ScribeGuide:
    title: str
    url: str


def is_scribe_url(url: str) -> bool:
    """Accept only Scribe document-viewer links, never arbitrary workspace links."""
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" and parts.hostname in {"scribehow.com", "www.scribehow.com"} and "/viewer/" in parts.path


def guide_filename(title: str, used: set[str]) -> str:
    """Produce a unique simple HTML filename without importing the publisher UI."""
    stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:90] or "scribe-guide"
    candidate, number = stem + ".html", 2
    while candidate.casefold() in used:
        candidate = stem + "-" + str(number) + ".html"; number += 1
    used.add(candidate.casefold())
    return candidate


def edge_candidates() -> list[Path]:
    """Known Edge locations plus Windows' registered application path."""
    candidates: list[Path] = []
    if os.name == "nt":
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as key:
                        candidates.append(Path(winreg.QueryValueEx(key, None)[0]))
                except OSError:
                    pass
        except ImportError:
            pass
    for root in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if root:
            candidates.append(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    return candidates


def edge_executable(candidates: list[Path] | None = None) -> Path | None:
    return next((path for path in (candidates if candidates is not None else edge_candidates()) if path.is_file()), None)


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_edge_cdp(engine, edge: Path, profile: Path, headless: bool = False):
    """Start Edge normally, then attach Playwright over loopback CDP.

    This avoids Playwright's direct browser-launch mode, which some managed or
    newer Edge installations close immediately.
    """
    port = _unused_local_port()
    args = [str(edge), "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=" + str(port), "--remote-allow-origins=*", "--user-data-dir=" + str(profile), "--no-first-run", "--new-window", "about:blank"]
    if headless:
        args.append("--headless=new")
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    endpoint = "http://127.0.0.1:" + str(port)
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(endpoint + "/json/version", timeout=1) as response:
                    if response.status == 200:
                        return process, engine.chromium.connect_over_cdp(endpoint)
            except OSError:
                time.sleep(.2)
        raise RuntimeError("Timed out waiting for Edge's local automation connection.")
    except Exception:
        if process.poll() is None:
            process.terminate()
        raise


def stop_edge(process, browser) -> None:
    if browser:
        try: browser.close()
        except Exception: pass
    if process and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill()


def browser_self_test() -> None:
    """Validate the packaged Playwright driver can start the installed Edge browser."""
    edge = edge_executable()
    if not edge:
        raise RuntimeError("Microsoft Edge was not found in its registered or standard Windows locations.")
    import tempfile
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix="scribe-edge-test-") as profile, sync_playwright() as engine:
        process, browser = start_edge_cdp(engine, edge, Path(profile), headless=True)
        try:
            browser.contexts[0].new_page().goto("about:blank")
        finally:
            stop_edge(process, browser)


class ScribeBrowser:
    """Owns a visible Edge/Playwright session on one worker thread."""
    def __init__(self):
        self.commands: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self.error: Exception | None = None
        self.thread: threading.Thread | None = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="Scribe browser", daemon=True)
        self.thread.start()

    def submit(self, name: str, *args, callback):
        """Run a browser command and invoke callback(value, error) from a helper thread."""
        reply: queue.Queue = queue.Queue(maxsize=1)
        self.commands.put((name, args, reply))
        def wait_for_reply():
            value, error = reply.get()
            callback(value, error)
        threading.Thread(target=wait_for_reply, daemon=True).start()

    def close(self):
        if self.thread and self.thread.is_alive():
            self.commands.put(("close", (), None))

    def _run(self):
        process = browser = None
        try:
            from playwright.sync_api import sync_playwright
            local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
            profile = local / "HelpGuidePublisher" / "scribe-edge-profile"
            profile.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as engine:
                edge = edge_executable()
                if not edge:
                    raise RuntimeError("Microsoft Edge was not found. The exporter searched its registered Windows path and standard install folders. Reinstall or repair Edge, then try again.")
                try:
                    process, browser = start_edge_cdp(engine, edge, profile)
                    context = browser.contexts[0]
                except Exception as error:
                    raise RuntimeError("Microsoft Edge was found at " + str(edge) + " but browser automation could not start. Details: " + str(error)[:500]) from error
                page = context.pages[0] if context.pages else context.new_page()
                context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://scribehow.com")
                page.goto(WORKSPACE_URL, wait_until="domcontentloaded")
                self.ready.set()
                while True:
                    name, args, reply = self.commands.get()
                    if name == "close":
                        return
                    try:
                        if name == "scan": value = self._scan(page)
                        elif name == "export": value = self._export(page, *args)
                        else: raise ValueError("Unknown Scribe browser action.")
                        reply.put((value, None))
                    except Exception as error:
                        reply.put((None, error))
        except Exception as error:
            self.error = error; self.ready.set()
        finally:
            stop_edge(process, browser)

    @staticmethod
    def _click(page, stage: str, patterns: list[str]):
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        for pattern in patterns:
            matcher = re.compile(pattern, re.I)
            locators = [page.get_by_role(role, name=matcher) for role in ("button", "link", "menuitem", "option")]
            locators += [page.locator("button, a, [role=button], [role=link], [role=menuitem], [role=option]").filter(has_text=matcher)]
            for locator in locators:
                try:
                    locator.first.click(timeout=2500); return
                except PlaywrightTimeout:
                    continue
        raise RuntimeError("Scribe's " + stage + " control was not found. Check the visible browser, then retry.")

    def _scan(self, page) -> list[ScribeGuide]:
        # Scan the list the user deliberately opened in the visible Edge window.
        # Do not navigate back to Workspace here: that would discard a Documents
        # filter/folder and leave nothing useful to enumerate.
        page.bring_to_front()
        # Scribe uses a virtualized list; scroll until several passes find no new viewer links.
        found: dict[str, str] = {}
        unchanged = 0
        for _ in range(40):
            anchors = page.locator("a[href]").evaluate_all("""links => links.map(a => ({url:a.href, title:(a.innerText || a.getAttribute('aria-label') || '').trim()}))""")
            before = len(found)
            for item in anchors:
                if is_scribe_url(item["url"]):
                    found[item["url"]] = item["title"] or item["url"].rsplit("/", 1)[-1].replace("_", " ")
            unchanged = unchanged + 1 if len(found) == before else 0
            if unchanged >= 3: break
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)"); page.wait_for_timeout(700)
        page.evaluate("window.scrollTo(0, 0)")
        if not found:
            raise RuntimeError("No accessible Scribe guides were found. In the visible Edge window, open Documents or the folder containing your guides, then scan again.")
        return [ScribeGuide(title, url) for url, title in sorted(found.items(), key=lambda item: item[1].casefold())]

    def _export(self, page, guide: ScribeGuide) -> str:
        page.goto(guide.url, wait_until="domcontentloaded"); page.bring_to_front(); page.wait_for_timeout(800)
        self._click(page, "Share", [r"^share$", r"share this scribe"]); page.wait_for_timeout(300)
        self._click(page, "Export menu", [r"^export$", r"^export\b", r"download"]); page.wait_for_timeout(300)
        self._click(page, "HTML export", [r"export.*html", r"html.*export", r"^html$", r"web page"]); page.wait_for_timeout(300)
        self._click(page, "Copy HTML", [r"copy.*clipboard", r"copy.*html", r"^copy$"])
        page.wait_for_timeout(300)
        content = page.evaluate("navigator.clipboard.readText()")
        if not isinstance(content, str) or "<" not in content or ">" not in content:
            raise RuntimeError("Scribe did not place HTML on the clipboard. Confirm HTML export is enabled for this guide and try again.")
        return content
