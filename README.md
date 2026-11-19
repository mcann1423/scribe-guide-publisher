# Help Guide Publisher

Prepare static, public help guides from Scribe HTML exports on a Windows PC. It does not upload files, connect to Apache, or alter the original exports. Guides and screenshots must be reviewed for sensitive information before publication.

## Install on Windows

Download and run `HelpGuidePublisherSetup.exe` from the project's GitHub **Releases** page. The installer includes the application, Python, Tcl/Tk, and its standard-library dependencies; Python does **not** need to be installed separately. It creates Start Menu and optional desktop shortcuts, supports in-place upgrades, and uses the normal Windows uninstaller.

The installer does not install or change Apache, FTP software, browser extensions, services, scheduled tasks, or anything on the web server. You still need access to the export and prepared website folders, including the `H:` drive if using the defaults, plus internet access to download screenshots.

## Updates

Use **Check for updates** in the application. It checks the public GitHub Releases page over HTTPS. When a newer release is available, the application downloads the single installer, verifies its advertised size (and SHA-256 checksum when GitHub provides one), launches it, and closes so the normal installer can upgrade the app. No GitHub account, token, Python installation, or separate updater is required. You can also download the newest installer manually from Releases.

If an installer is not available yet, developers can run the source checkout with Windows 10/11 and Python 3.10 or later (including Tcl/Tk and the Python launcher `py`) by double-clicking `Start-Guide-Publisher.bat`.

The defaults are `H:\HTML\Exports` and `H:\HTML\luna\tech-services\help-guides`. Select different folders with Browse and click **Load / refresh**. The paths must not overlap. Use a **dedicated** output folder: the app owns its `index.html`, `guide-style.css` and `guide-search.js`; it refuses first use if any already exist. Do not manually add files to its per-guide image folders.

## Workflow

1. Export HTML to the Exports folder, **or** click **Paste HTML and publish** and paste an export directly into the app. In the paste window, choose the export filename; the app saves the original UTF-8 HTML in the Exports folder before publishing it. Name each export uniquely; the filename becomes a normalized public URL. Review the guide and screenshots for sensitive details; output will be public.
2. Load / refresh. Select an export and **Publish / update selected**. The tool downloads images, then creates a local page and updates the index. Empty alt text and unsupported relative links are reported for review.
3. Replace an export with an updated version using the **same filename**, then publish it again to keep its link. Different filenames are new guides. Similar filenames can normalize to the same URL: the tool reports the collision rather than overwriting another guide.
4. **Unpublish selected** removes the local generated guide, its managed image folder, and its index entry. This does **not** remove an existing server copy. Open **Server removal list** to see paths that may still be live. Remove them manually or perform your usual clean-copy deployment; clear notices only after verifying the live site. If a guide is republished, a prior removal notice stays until cleared: do not delete its current server copy without checking.
5. FTP the prepared files to staging, then copy into the Apache web directory as usual. Upload the entire help-guides folder, including `guide-search.js`, `guide-style.css`, and `images`. The site works as static files, with search using local JavaScript; the full listing remains available without JavaScript.

State is stored as `.scribe-publisher-state.json` in the export directory, **outside the public output**. Back up this file with the original exports; it records publication ownership and server cleanup notices. Do not modify or delete it while continuing to use the same output. An export folder is tied to one output folder. The state and output must be restored together from backup. The tool never detects what is actually live on the server.

## Export from Scribe

Click **Export from Scribe** to open a visible Microsoft Edge session. Sign in to Scribe yourself, complete MFA/SSO there, and open the Documents page to the guide list you want. The app does not ask for, receive, or store your Scribe password. Click **Scan accessible guides**, select documents, review their generated filenames, and export them one at a time through Scribe's normal HTML export controls. Exported HTML is saved to the Exports folder; use **Publish locally after each export** only after reviewing what will become public.

The browser keeps a separate local Edge profile so a normal Scribe session can persist for the same Windows user. Its cookies are managed by Edge/Windows and can be cleared by removing the `HelpGuidePublisher\\scribe-edge-profile` folder under `%LOCALAPPDATA%`. The exporter only sees guides visible to the signed-in account. It does not use Scribe's undocumented APIs, bypass sharing permissions, or automate CAPTCHA or MFA. Scribe UI changes, export permissions, and inaccessible guides can stop a batch; the visible browser stays open so you can correct the issue and retry.

## Behavior and limitations

- Downloads PNG, JPEG, GIF and WebP images (up to 25 MB each), based on actual file signatures. Relative image paths must stay within the export directory. An unavailable or unsupported image blocks that guide's publication/update; a previous version is retained for download failures. No network access occurs during website viewing for guide images.
- To limit unsafe network requests from imported HTML, remote images and redirects must use HTTPS and the `colony-recorder.s3.us-west-1.amazonaws.com` host found in the supplied export. Other hosts are rejected; an export using a different legitimate Scribe host requires an explicit code update after review. Original exports should also be treated as sensitive local files.
- HTML is treated as untrusted: scripts, forms, embeds, styles, event attributes and most non-content tags are removed. Only HTTP(S), mailto, and fragment links are kept. Remote links may still lead off-site. Original exports remain untouched. Scribe author/footer attribution blocks are omitted from published copies; check applicable terms before redistribution.
- Exports are expected to be UTF-8 HTML. This is designed around a supplied Scribe example; other Scribe content (e.g. videos, interactive embeds, unusual layouts, and animations) may not be preserved. Inspect the finished pages before deployment. Empty screenshot alt text is preserved rather than guessed; add meaningful descriptions to the export as needed.
- Filename-derived URLs are lower-case ASCII slugs; reserved names and collisions are rejected. Paths on the server are case-sensitive. Changing a filename creates a new guide; unpublish the old one if needed.
- This is a single-user local tool: do not run two instances or edit generated files while it operates. It uses staged downloads and best-effort rollback, but a crash or interrupted file operation can leave partially updated output; keep backups and inspect before FTP. State is not a backup of the generated site.
- The UI is synchronous: large or inaccessible images can pause it while a download times out.

## Tests

`py -3 -m unittest discover -s tests -v`. The tests use temporary directories and synthetic image responses, and do not modify H: or contact the network. Live Scribe URLs and Windows/Apache integration must be validated separately in your environment.

## Building the installer

The Windows GitHub Actions workflow runs the tests, bundles the GUI and the Playwright browser driver with PyInstaller, then compiles `installer/HelpGuidePublisher.iss` with Inno Setup. Its output is `HelpGuidePublisherSetup.exe`. Tagged builds publish it as a GitHub Release; manually dispatched builds retain it as a workflow artifact. The built application is self-contained, so no dependency downloader or administrator-installed Python is required on the target PC. The Scribe exporter uses Microsoft Edge already included in supported Windows installations.
