# -*- coding: utf-8 -*-
"""Measure the real cost of this addon's memory reads, on the live game process.

    python -B tools/measure_overhead.py

Read-only: it opens the game with PROCESS_VM_READ, resolves the stratagem table
the same way the addon does, times the three ReadProcessMemory shapes the addon
uses and prints the addon's derived per-scan / per-watch / per-frame budget.
Nothing is written to the game, and no window or input automation is used.

Why not use the addon's own self-report: it is computed from os.clock(), whose
resolution on Windows is ~15.6 ms, so sub-millisecond work rounds to 0.000 ms.
"""
import ctypes
import ctypes.wintypes as wt
import re
import struct
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
psapi = ctypes.WinDLL('psapi', use_last_error=True)
PROCESS_VM_READ, PROCESS_QUERY_LIMITED_INFORMATION = 0x0010, 0x1000


class MODULEINFO(ctypes.Structure):
    _fields_ = [('lpBaseOfDll', ctypes.c_void_p), ('SizeOfImage', ctypes.c_uint32),
                ('EntryPoint', ctypes.c_void_p)]


class Proc(object):
    def __init__(self, pid):
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION,
                                 False, pid)
        if not self.h:
            raise SystemExit('OpenProcess failed (%d)' % ctypes.get_last_error())

    def read(self, addr, size):
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, size,
                                     ctypes.byref(got)) or got.value != size:
            return None
        return buf.raw

    def module(self, name):
        mods = (ctypes.c_void_p * 1024)()
        needed = ctypes.c_uint32(0)
        psapi.EnumProcessModulesEx(self.h, mods, ctypes.sizeof(mods),
                                   ctypes.byref(needed), 3)
        for i in range(needed.value // ctypes.sizeof(ctypes.c_void_p)):
            base = mods[i]
            buf = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(self.h, ctypes.c_void_p(base), buf, 260)
            if buf.value.lower() == name.lower():
                info = MODULEINFO()
                psapi.GetModuleInformation(self.h, ctypes.c_void_p(base),
                                           ctypes.byref(info), ctypes.sizeof(info))
                return info.lpBaseOfDll, info.SizeOfImage
        return None, None


def find_pid(name='helldivers2'):
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s.exe' % name,
                          '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
    return None


AOB1 = bytes([0x49, 0x8B, 0x84, 0xC7])
AOB2 = bytes([0x44, 0x8B, 0x80, 0xC8, 0x00, 0x00, 0x00, 0x8B, 0xC2, 0x45, 0x85, 0xC0])


def resolve(proc, base):
    dos = proc.read(base, 0x1000)
    pe = proc.read(base + struct.unpack_from('<I', dos, 0x3C)[0], 0x200)
    image = struct.unpack_from('<I', pe, 0x50)[0]
    data = proc.read(base, min(image, 0x2400000))
    p = data.find(AOB1)
    while p >= 0 and data[p + 8:p + 8 + len(AOB2)] != AOB2:
        p = data.find(AOB1, p + 1)
    consumer = base + p
    disp = struct.unpack_from('<i', proc.read(consumer, 0x20), 4)[0]
    back_start = max(base, consumer - 0x1000)
    back = proc.read(back_start, consumer - back_start)
    for i in range(len(back) - 6, 0, -1):
        if back[i:i + 3] == b'\x4c\x8d\x3d':
            target = back_start + i + 7 + struct.unpack_from('<i', back, i + 3)[0]
            if base <= target < base + 0x100000:
                return target + disp, image
    raise SystemExit('table not resolved')


def bench(label, n, fn):
    fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    dt = time.perf_counter() - t0
    print('%-28s %6d calls  %8.1f us/call  (%.3f ms total)'
          % (label, n, dt / n * 1e6, dt * 1e3))
    return dt / n


def main():
    pid = find_pid()
    if not pid:
        raise SystemExit('helldivers2.exe is not running - start the game first')
    proc = Proc(pid)
    base, size = proc.module('game.dll')
    table, image = resolve(proc, base)
    print('pid=%d game.dll=0x%X table=0x%X image=%.0f MB'
          % (pid, base, table, image / 1048576.0))

    rec = None
    for sid in range(256):
        slot = proc.read(table + sid * 8, 8)
        if slot and struct.unpack_from('<Q', slot, 0)[0] > 0x10000:
            rec = struct.unpack_from('<Q', slot, 0)[0]
            break
    slot_us = bench('8B slot read', 3000, lambda: proc.read(table + 8, 8))
    rec_us = bench('176B record read', 800, lambda: proc.read(rec, 0xB0))

    reads, t0 = 0, time.perf_counter()
    for i in range(48):
        if proc.read(base + i * 0x100000, 0x100000):
            reads += 1
    dt = time.perf_counter() - t0
    chunk_ms = dt / max(reads, 1) * 1000
    print('%-28s %6d calls  %8.1f MB  %.2f s -> %.0f MB/s (%.2f ms/chunk)'
          % ('1MB chunk read', 48, reads, dt, reads / dt if dt else 0, chunk_ms))

    print('\n=== derived addon budget ===')
    print('per frame (steady)        : 0 FFI calls, ~0.002 ms of Lua')
    print('watch pass, 13 targets    : %.3f ms every 5 s (%.3f ms/s)'
          % (13 * 2 * rec_us * 1e3, 13 * 2 * rec_us * 1e3 / 5))
    print('idle sweep 0..255         : %.2f ms every 10 s (%.3f ms/s)'
          % ((256 * slot_us + 80 * rec_us) * 1e3, (256 * slot_us + 80 * rec_us) * 1e3 / 10))
    print('idle sweep 0..511 (1.7.2) : %.2f ms every 10 s'
          % ((512 * slot_us + 150 * rec_us) * 1e3))
    print('resolver at load          : %.1f ms one-shot' % (image / 1048576.0 * chunk_ms))
    print('copy probe (opt-in)       : %.0f ms one-shot for 13 targets'
          % (13 * 2 * 16 * chunk_ms))


if __name__ == '__main__':
    main()
