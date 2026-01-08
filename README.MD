# SCUF Envision Pro Linux Bridge

A Python-based virtual controller bridge that makes the SCUF Envision Pro controller fully compatible with Linux applications and emulators (specifically tested with Citron).

## Overview

The SCUF Envision Pro controller exposes its inputs across multiple device interfaces on Linux (`/dev/input/eventX` and `/dev/hidraw`), with non-standard axis mappings that confuse most applications. This bridge reads from both interfaces, remaps all inputs to standard Xbox controller format, and creates a virtual controller that "just works" with games and emulators.

### What it does:
- **Remaps triggers**: L2/R2 are split between evdev and hidraw - combines them into standard `ABS_Z`/`ABS_RZ` axes
- **Fixes stick mappings**: Right stick uses non-standard axes - remaps to proper `ABS_RX`/`ABS_RY`
- **Converts D-pad**: Transforms HAT switch input to standard D-pad buttons
- **Corrects button codes**: Maps SCUF's non-standard button codes (like `BTN_TL2` for L3) to standard Xbox equivalents
- **Applies filtering**: Deadzone and jitter filtering for smooth analog stick input
- **Creates Xbox identity**: Virtual device mimics Xbox Elite 2 controller for maximum compatibility

## Installation

### Prerequisites

```bash
# Install required Python packages
sudo pacman -S python-evdev

# Load uinput kernel module
sudo modprobe uinput

# Make uinput load on boot
echo "uinput" | sudo tee /etc/modules-load.d/uinput.conf
```

### Setup

1. **Configure device paths** (if needed):
   
   Find your SCUF controller's event and hidraw devices:
   ```bash
   # Find evdev device
   ls -la /dev/input/by-id/ | grep -i scuf
   
   # Check all devices to find SCUF
   cat /proc/bus/input/devices | grep -A 10 -i scuf
   ```
   
   Update `EVDEV_PATH` and `HIDRAW_PATH` in `scuf_virtual_pad.py` if they differ from `/dev/input/event3` and `/dev/hidraw0`.

2. **Install systemd service**:


   IMPORTANT!: Update file path in scuf-virtual-controller.service to where scuf_virtual_pad.py exists (default where the repo is /path-to-repo/path-to-file/scuf_virtual_pad.py)
   Example: ExecStart=/usr/bin/python3 /file/path/to/scuf_virtual_pad.py -> ExecStart=/usr/bin/python3 /home/user/repo/scuf_virtual_pad.py

   ```bash
   # Copy service file to systemd directory
   sudo cp scuf-virtual-controller.service /etc/systemd/system/
   
   # Reload systemd to recognize new service
   sudo systemctl daemon-reload
   
   # Enable service to start on boot
   sudo systemctl enable scuf-virtual-controller.service
   
   # Start service immediately
   sudo systemctl start scuf-virtual-controller.service
   ```

3. **Verify it's running**:
   
   ```bash
   # Check service status
   sudo systemctl status scuf-virtual-controller.service
   
   # View live logs
   sudo journalctl -u scuf-virtual-controller.service -f
   ```

## Usage

Once the service is running, your SCUF Envision Pro will appear as a "Virtual SCUF Envision Pro" controller that works with all Linux applications.

### Testing the virtual controller

```bash
# List input devices (should see "Virtual SCUF Envision Pro")
sudo evtest

# Select the virtual device and test all buttons/sticks/triggers
```

### Service Management

```bash
# Stop the service
sudo systemctl stop scuf-virtual-controller.service

# Restart the service
sudo systemctl restart scuf-virtual-controller.service

# Disable auto-start on boot
sudo systemctl disable scuf-virtual-controller.service

# View logs
sudo journalctl -u scuf-virtual-controller.service
```

## How It Works

The bridge operates by:

1. **Grabbing exclusive access** to the physical SCUF controller (prevents direct application access)
2. **Reading from two sources simultaneously**:
   - `/dev/input/eventX` - Most buttons, sticks, L2 trigger, D-pad
   - `/dev/hidraw` - R2 trigger data (sent via HID reports)
3. **Remapping and filtering** all inputs to standard Xbox controller format
4. **Writing to a virtual uinput device** that applications see as a real Xbox controller

The service automatically:
- Waits for the controller to be plugged in
- Handles disconnections gracefully (restarts and waits for reconnection)
- Runs on system startup

## Troubleshooting

### Controller not detected
```bash
# Check if controller is connected
lsusb | grep -i scuf

# Find the correct device paths
cat /proc/bus/input/devices
ls -la /dev/input/by-id/
```

### Service fails to start
```bash
# Check detailed error logs
sudo journalctl -u scuf-virtual-controller.service -n 50

# Verify Python dependencies
python3 -c "import evdev; print('evdev OK')"

# Check uinput module
lsmod | grep uinput
```

### Triggers not working in games
The virtual controller uses the exact same axis specifications as an Xbox Elite 2 controller (0-1023 range for triggers). If triggers don't work, check the game's controller configuration.

## Steam Configuration

### Hide the physical SCUF controller from Steam

Since the bridge creates a virtual controller, you must prevent Steam from detecting the physical SCUF device to avoid having both controllers appear in Steam.

**Create a udev rule to hide the physical device:**

```bash
sudo nano /etc/udev/rules.d/69-scuf-rename.rules
```

Add these lines:
```
# Rename SCUF physical controller so Steam doesn't recognize it
SUBSYSTEM=="input", ATTRS{idVendor}=="2e95", ATTRS{idProduct}=="434d", KERNEL=="event*", ENV{ID_INPUT_JOYSTICK}="", ENV{ID_INPUT_GAMEPAD}="", ENV{ID_INPUT_KEY}="1", ENV{.INPUT_CLASS}="kbd", NAME="scuf-hidden-%k"
SUBSYSTEM=="input", ATTRS{idVendor}=="2e95", ATTRS{idProduct}=="434d", KERNEL=="js*", MODE="0000", OPTIONS+="ignore_device"
```

**Reload udev rules:**
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

**Restart Steam** and unplug/replug your controller.

### Verify it worked

In Steam Big Picture Mode:
- Go to Settings → Controller → Controller Settings
- You should only see "Virtual SCUF Envision Pro"
- The physical "Gaming SCUF Envision Pro Controller" should NOT appear

**Note**: This udev rule renames the physical device and removes its joystick/gamepad tags, making it invisible to Steam while still allowing the bridge script to access it.

## Configuration

Edit `scuf_virtual_pad.py` to customize:

- **Deadzone values**: `LEFT_DEADZONE`, `RIGHT_DEADZONE`
- **Jitter filtering**: `LEFT_JITTER`, `RIGHT_JITTER`
- **Device paths**: `EVDEV_PATH`, `HIDRAW_PATH`
- **Button mappings**: `BUTTON_REMAP` dictionary

After changes, restart the service:
```bash
sudo systemctl restart scuf-virtual-controller.service
```

## License

MIT

## Credits

Created for the SCUF Envision Pro controller on Arch Linux. Tested with Citron emulator. Author: Julian Cotto
