# Rituals2Lox

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-jan__hajek-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/jan_hajek)

A [LoxBerry](https://wiki.loxberry.de) plugin that connects **Rituals Perfume Genie** smart diffusers to a **Loxone Miniserver**.

## Features

- Rituals account login with automatic token management
- Status and control of Genie devices
- Data delivered to the Miniserver via **UDP** (low Miniserver load)
- Generator for the **Loxone Wizard** XML (Virtual Inputs/Outputs)
- Web UI for setup and logs

## Requirements

- LoxBerry 2.0 or newer
- A Rituals account with a registered Perfume Genie
- Loxone Miniserver

## Installation

1. In LoxBerry open **System Update / Plugin Management -> Install Plugin**.
2. Upload the ZIP from the [latest release](https://github.com/mi3k8y/rituals2lox/releases/latest), or use "Install from URL".
3. Open the plugin, enter your Rituals credentials and the Miniserver UDP port.
4. Use the Loxone Wizard tab to create the Virtual Inputs/Outputs in Loxone Config.

## Disclaimer

This is an unofficial community project. It is **not affiliated with, endorsed by or supported by Rituals Cosmetics**.
It uses an undocumented API that may change without notice. "Rituals" and "Perfume Genie" are trademarks of their owners. Use at your own risk.

## Support the project

If the plugin saves you time, you can [buy me a coffee](https://buymeacoffee.com/jan_hajek).

## License

MIT, see [LICENSE](LICENSE).
