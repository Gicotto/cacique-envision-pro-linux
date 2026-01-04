#!/usr/bin/env python3
"""
SCUF Envision Pro -> Virtual Xbox-compatible controller (Citron fix)

Hardware mapping:
- Left trigger (L2)  → evdev ABS_RX  → virtual ABS_Z
- Right trigger (R2) → hidraw rx     → virtual ABS_RZ
- Right stick Y      → evdev ABS_Z   → virtual ABS_RY
- Right stick X      → evdev ABS_RZ  → virtual ABS_RX
- Left stick         → evdev ABS_X/Y → virtual ABS_X/Y
"""

import os
import struct
import selectors
import errno
from evdev import InputDevice, UInput, ecodes as e, AbsInfo

# --------- CONFIG ----------
EVDEV_PATH = "/dev/input/event3"
HIDRAW_PATH = "/dev/hidraw0"

# Stick filtering (signed -32768..32767)
LEFT_DEADZONE  = 3500
LEFT_JITTER    = 300

RIGHT_DEADZONE = 2000
RIGHT_JITTER   = 300

# Trigger max values
L2_MAX = 1023
R2_MAX = 1023
# --------------------------

# Button remaps
BUTTON_REMAP = {
    e.BTN_SOUTH: e.BTN_SOUTH,   # A
    e.BTN_EAST:  e.BTN_EAST,    # B
    e.BTN_NORTH: e.BTN_NORTH,   # Y
    e.BTN_C:     e.BTN_WEST,    # X

    e.BTN_WEST:  e.BTN_TL,      # L1 -> LB
    e.BTN_Z:     e.BTN_TR,      # R1 -> RB

    e.BTN_TR:    e.BTN_START,   # Start
    e.BTN_TL:    e.BTN_SELECT,  # Select

    e.BTN_MODE:   e.BTN_MODE,   # Guide
    e.BTN_TL2:    e.BTN_THUMBL, # L3 (SCUF uses BTN_TL2)
    e.BTN_TR2:    e.BTN_THUMBR, # R3 (SCUF uses BTN_TR2)
}

VIRTUAL_BUTTONS = [
    e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST,
    e.BTN_TL, e.BTN_TR,
    e.BTN_SELECT, e.BTN_START, e.BTN_MODE,
    e.BTN_THUMBL, e.BTN_THUMBR,
    e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT,
]

def make_uinput():
    """Create virtual controller matching Xbox Elite 2 specs exactly"""
    
    # Match Xbox Elite 2 axis specifications exactly
    cap = {
        e.EV_KEY: VIRTUAL_BUTTONS,
        e.EV_ABS: [
            (e.ABS_X, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
            (e.ABS_Y, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
            (e.ABS_Z, AbsInfo(value=0, min=0, max=1023, fuzz=0, flat=0, resolution=0)),
            (e.ABS_RX, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
            (e.ABS_RY, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
            (e.ABS_RZ, AbsInfo(value=0, min=0, max=1023, fuzz=0, flat=0, resolution=0)),
            (e.ABS_HAT0X, AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)),
            (e.ABS_HAT0Y, AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)),
        ],
        e.EV_FF: [e.FF_RUMBLE],  # Add rumble support for better compatibility
    }

    ui = UInput(cap, name="Virtual SCUF Envision Pro", 
                vendor=0x045e, product=0x02ea, version=0x0301,
                bustype=0x0003)  # USB
    
    # Initialize all axes at rest position
    ui.write(e.EV_ABS, e.ABS_X, 0)
    ui.write(e.EV_ABS, e.ABS_Y, 0)
    ui.write(e.EV_ABS, e.ABS_RX, 0)
    ui.write(e.EV_ABS, e.ABS_RY, 0)
    ui.write(e.EV_ABS, e.ABS_Z, 0)
    ui.write(e.EV_ABS, e.ABS_RZ, 0)
    ui.write(e.EV_ABS, e.ABS_HAT0X, 0)
    ui.write(e.EV_ABS, e.ABS_HAT0Y, 0)
    ui.syn()
    
    # print("[uinput] Virtual Xbox controller created")
    # print(f"[uinput] Device: {ui.device.path}")
    return ui

def parse_report6(report: bytes):
    """Extract Rx (R2 only) from hidraw report 6"""
    if not report or report[0] != 0x06:
        return None
    if len(report) < 14:
        return None
    rx = struct.unpack_from("<H", report, 9)[0]   # Right trigger (R2)
    return rx

def centered_u16_to_trigger(raw_u16: int, max_val: int) -> int:
    """Convert centered uint16 (0x8000 = rest) to 0-max_val trigger value"""
    delta = raw_u16 - 0x8000
    if delta < 0:
        delta = 0
    if delta > 0x7FFF:
        delta = 0x7FFF
    return int(round((delta / 0x7FFF) * max_val))

def apply_stick_filter(axis_code: int, signed_value: int, last: dict) -> int | None:
    """Apply deadzone and jitter filtering to stick axes"""
    if axis_code in (e.ABS_RX, e.ABS_RY):
        dz = RIGHT_DEADZONE
        js = RIGHT_JITTER
    else:
        dz = LEFT_DEADZONE
        js = LEFT_JITTER

    v = 0 if abs(signed_value) < dz else signed_value
    prev = last.get(axis_code)

    if prev is not None and v != 0 and abs(v - prev) < js:
        return None
    if prev is not None and v == 0 and prev == 0:
        return None

    last[axis_code] = v
    return v

def main():
    dev = InputDevice(EVDEV_PATH)
    dev.grab()

    hid_fd = os.open(HIDRAW_PATH, os.O_RDONLY | os.O_NONBLOCK)

    ui = make_uinput()
    # print(f"[init] evdev={EVDEV_PATH} hidraw={HIDRAW_PATH}")
    # print("[init] Mapping:")
    # print("  L2 trigger  → evdev ABS_RX  → virtual ABS_Z")
    # print("  R2 trigger  → hidraw Rx     → virtual ABS_RZ")
    # print("  Right stick → evdev ABS_Z/RZ → virtual ABS_RX/RY")
    # print("  Left stick  → evdev ABS_X/Y  → virtual ABS_X/Y")
    # print("  D-pad       → evdev HAT      → virtual DPAD buttons")

    sel = selectors.DefaultSelector()
    sel.register(dev.fd, selectors.EVENT_READ, data="evdev")
    sel.register(hid_fd, selectors.EVENT_READ, data="hidraw")

    last_stick = {}
    last_l2 = 0
    last_r2 = 0

    # D-pad hat -> DPAD buttons
    hat_x = 0
    hat_y = 0
    last_dpad = {e.BTN_DPAD_LEFT:0, e.BTN_DPAD_RIGHT:0, e.BTN_DPAD_UP:0, e.BTN_DPAD_DOWN:0}

    def apply_dpad():
        dpad = {
            e.BTN_DPAD_LEFT:  1 if hat_x == -1 else 0,
            e.BTN_DPAD_RIGHT: 1 if hat_x ==  1 else 0,
            e.BTN_DPAD_UP:    1 if hat_y == -1 else 0,  # Fixed inversion
            e.BTN_DPAD_DOWN:  1 if hat_y ==  1 else 0,  # Fixed inversion
        }
        for btn, state in dpad.items():
            if last_dpad[btn] != state:
                ui.write(e.EV_KEY, btn, state)
                last_dpad[btn] = state

    # print("[ready] Controller bridge running...")
    # print("[info] Test triggers with: sudo evtest and select this virtual device")

    while True:
        for key, _mask in sel.select():
            src = key.data

            if src == "hidraw":
                try:
                    data = os.read(hid_fd, 64)
                except BlockingIOError:
                    continue

                raw_rx = parse_report6(data)
                if raw_rx is None:
                    continue

                # Right trigger from hidraw Rx
                r2_val = centered_u16_to_trigger(raw_rx, R2_MAX)
                if r2_val != last_r2:
                    ui.write(e.EV_ABS, e.ABS_RZ, r2_val)
                    last_r2 = r2_val
                    ui.syn()

            elif src == "evdev":
                try:
                    batch = dev.read()
                except BlockingIOError:
                    continue

                for ev in batch:
                    if ev.type == e.EV_KEY:
                        out = BUTTON_REMAP.get(ev.code, ev.code)
                        if out in VIRTUAL_BUTTONS:
                            ui.write(e.EV_KEY, out, ev.value)

                    elif ev.type == e.EV_ABS:
                        # Left stick - forward as-is with filtering
                        if ev.code in (e.ABS_X, e.ABS_Y):
                            filtered = apply_stick_filter(ev.code, ev.value, last_stick)
                            if filtered is not None:
                                ui.write(e.EV_ABS, ev.code, filtered)

                        # Left trigger (L2) from evdev ABS_RX (unsigned 0-1023)
                        elif ev.code == e.ABS_RX:
                            if ev.value != last_l2:
                                ui.write(e.EV_ABS, e.ABS_Z, ev.value)
                                last_l2 = ev.value

                        # Right stick X from evdev ABS_Z (signed)
                        elif ev.code == e.ABS_Z:
                            filtered = apply_stick_filter(e.ABS_RX, ev.value, last_stick)
                            if filtered is not None:
                                ui.write(e.EV_ABS, e.ABS_RX, filtered)

                        # Right stick Y from evdev ABS_RZ (signed)
                        elif ev.code == e.ABS_RZ:
                            filtered = apply_stick_filter(e.ABS_RY, ev.value, last_stick)
                            if filtered is not None:
                                ui.write(e.EV_ABS, e.ABS_RY, filtered)

                        # Ignore evdev ABS_RY (noisy/unused)
                        elif ev.code == e.ABS_RY:
                            pass

                        # D-pad hat
                        elif ev.code == e.ABS_HAT0X:
                            hat_x = ev.value
                            apply_dpad()
                        elif ev.code == e.ABS_HAT0Y:
                            hat_y = ev.value
                            apply_dpad()

                ui.syn()

if __name__ == "__main__":
    main()
