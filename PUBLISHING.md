# Publishing checklist - Rituals2Lox

1. Replace `YOUR_PUBLIC_EMAIL@example.com` in `plugin.cfg` and `release.cfg`.
2. Copy `templates/plugin.cfg` into your plugin source root (merge with your existing one), add `icons/icon_{64,128,256,512}.png`, and paste `templates/support-footer.html` into the web UI footer.
3. Build: `./build.sh /path/to/plugin-source` -> `rituals2lox-vX.Y.Z.zip`
4. Test on a clean LoxBerry: install ZIP, then upgrade from the previous version.
5. Create GitHub repo `mi3k8y/rituals2lox` (public), push source + README, LICENSE, `.github/FUNDING.yml`, `release.cfg`.
6. `git tag v1.0.0 && git push --tags`, then create a GitHub Release and attach the ZIP.
7. Announce in the Loxforum plugin section and register on the LoxBerry plugin directory (check current instructions on wiki.loxberry.de).
8. For each new version: bump `VERSION` in `plugin.cfg` and `release.cfg`, update `ARCHIVEURL`/`INFOURL`, tag, release.

Note: the `release.cfg` / `[AUTOUPDATE]` keys follow the LoxBerry plugin auto-update format as I know it; verify against the current LoxBerry wiki before the first release.
