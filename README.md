# FreePing 🎮

Tu **NoPing** personal, gratuito y autoalojado. Usa Oracle Cloud Free Tier para crear un túnel WireGuard que reduce la latencia en tus juegos.

## Requisitos

- Python 3.12+
- Oracle Cloud cuenta (gratis en [signup.cloud.oracle.com](https://signup.cloud.oracle.com))
- Linux o Windows
- WireGuard instalado ([wireguard.com/install](https://www.wireguard.com/install/))

## Instalación (un solo comando)

```bash
git clone https://github.com/diegogaleano/freeping.git
cd freeping
./install.sh
```

O directamente:

```bash
pip install freeping[gui]
freeping
```

## Cómo funciona

1. El **Setup Wizard** te guía para conectar FreePing con tu cuenta de Oracle Cloud
2. FreePing crea automáticamente una VM gratuita (4 OCPU, 24 GB RAM) con WireGuard
3. Activas el túnel desde la interfaz gráfica, seleccionas tu juego, y jugás con menor latencia

## Funcionalidades

- **Setup guiado** — Te guía paso a paso desde la creación de cuenta Oracle hasta tener el túnel funcionando
- **Dashboard de latencia** — Comparación visual del ping con/sin túnel
- **Selector de juegos** — Lista precargada de IPs de servidores de juegos populares
- **Auto-test** — Al activar el túnel, mide automáticamente la mejora
- **System tray** — Minimiza a la bandeja del sistema para acceso rápido
- **Watchdog** — Reconexión automática si el túnel se cae
- **Cross-platform** — Funciona en Linux y Windows

## Desarrollo

```bash
pip install -e ".[gui,dev]"
freeping  # o: python -m freeping
```

### Tests

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ -v
```

### Build (PyInstaller)

```bash
pip install ".[build]"
pyinstaller build/freeping.spec
```

## Stack

- Python 3.12+ · PySide6 · WireGuard · Oracle Cloud Always Free
- httpx · PyYAML · PyInstaller

## Licencia

MIT
