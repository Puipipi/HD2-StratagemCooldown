# -*- coding: utf-8 -*-
"""Offline sandbox for 战备冷却 / Stratagem Cooldown.

The addon runs inside the game's LuaJIT with Bingus Shared Loader's FFI.  This
sandbox reproduces that contract far enough to test the parts that actually
failed in the game:

  * a **synthetic game.dll image** with the exact AOB pair, the ``lea r15``
    anchor and the StratagemInfo slot array, so ``locate_table()`` runs for
    real (chunked reads, PE header, displacement decode) instead of being
    stubbed;
  * a **memory model** (image + heap records) behind ReadProcessMemory /
    WriteProcessMemory, with optional hostile addresses and failing writes;
  * a **fake ffi module** with the cdata shapes the addon uses (``uint8_t[?]``,
    ``size_t[1]``, ``uint32_t[1]``, ``float[1]`` and the shared-storage cast
    between ``float[1]`` and ``uint32_t *``).

LuaJIT's FFI is not available inside lupa (the bundled LuaJIT is built with the
FFI module disabled), so one rule is modelled explicitly: a Lua number that
cannot be represented as a 64-bit pointer (negative, fractional or >= 2**64)
cannot be converted by ``ffi.cast`` and raises.  That is the class of failure
the 1.5.1 sweep walked into; the tests assert the fixed source never depends on
it and always keeps the error visible.
"""
import importlib
import os
import re
import struct
import tempfile

# ---------------------------------------------------------------- memory model

IMAGE_BASE = 0x00007FF900000000
IMAGE_SIZE = 0x300000
CONSUMER_RVA = 0x180000
LEA_RVA = CONSUMER_RVA - 0x40
R15_RVA = 0x80000
TABLE_RVA = 0x200000
HEAP_BASE = 0x000001D500000000
RECORD_STRIDE = 0x100
SCAN_SLOTS = 146
COOLDOWN_OFF = 0x68
USES_OFF = 0x50            # int32 charges, -1 = unlimited
NAME_OFF = 0x10
ID_OFF = 0x00
VANILLA = 780.0
POISON = 0xFFFFFFFFFFFFFFFF
MAX_SANE = 0x00007FFFFFFFFFFF


def _f32(v):
    return struct.pack('<f', v)


class FakeMemory(object):
    """Synthetic game.dll image plus heap records."""

    def __init__(self, records, table_ids=None):
        self.image = bytearray(IMAGE_SIZE)
        self.casts = []            # every number handed to ffi.cast('uint8_t *', n)
        self.trace = []            # (op, address, payload) for debugging
        self.reads = 0
        self.writes = 0
        self.fail_writes = False
        self.hostile = None        # address that makes the memory layer raise
        self.records = {}
        self._build_image()
        self._build_records(records, table_ids)

    # -- construction ------------------------------------------------------
    def _build_image(self):
        img = self.image
        img[0:2] = b'MZ'
        peoff = 0x80
        struct.pack_into('<I', img, 0x3C, peoff)
        img[peoff:peoff + 4] = b'PE\0\0'
        struct.pack_into('<I', img, peoff + 0x50, IMAGE_SIZE)
        disp = TABLE_RVA - R15_RVA
        img[CONSUMER_RVA:CONSUMER_RVA + 4] = bytes([0x49, 0x8B, 0x84, 0xC7])
        struct.pack_into('<i', img, CONSUMER_RVA + 4, disp)
        img[CONSUMER_RVA + 8:CONSUMER_RVA + 19] = bytes(
            [0x44, 0x8B, 0x80, 0xC8, 0x00, 0x00, 0x00, 0x8B, 0xC2, 0x45, 0x85, 0xC0])
        ds = R15_RVA - (LEA_RVA + 7)
        img[LEA_RVA] = 0x4C
        img[LEA_RVA + 1] = 0x8D
        img[LEA_RVA + 2] = 0x3D
        struct.pack_into('<i', img, LEA_RVA + 3, ds)

    def _build_records(self, records, table_ids):
        """records: list of dicts {id, name, cooldown, name_ptr, ptr}."""
        for entry in records:
            rid = entry['id']
            addr = HEAP_BASE + rid * RECORD_STRIDE
            buf = bytearray(0x100)
            struct.pack_into('<I', buf, ID_OFF, entry.get('rec_id', rid))
            struct.pack_into('<f', buf, COOLDOWN_OFF, entry.get('cooldown', VANILLA))
            struct.pack_into('<i', buf, USES_OFF, entry.get('uses', -1))
            name_addr = HEAP_BASE + 0x400000 + rid * 0x100
            if entry.get('name') is not None:
                raw = entry['name'].encode('latin-1') + b'\0'
                raw = raw + b'\0' * (0x200 - len(raw))     # readable page tail
                self.records.setdefault('names', {})[name_addr] = raw
            struct.pack_into('<Q', buf, NAME_OFF,
                             entry['name_ptr'] if 'name_ptr' in entry else name_addr)
            self.records[addr] = buf
        self.records.setdefault('names', {})
        if table_ids is None:
            table_ids = {}
            for entry in records:
                table_ids[entry['id']] = HEAP_BASE + entry['id'] * RECORD_STRIDE
        base = TABLE_RVA
        for sid in range(SCAN_SLOTS):
            ptr = table_ids.get(sid, 0)
            struct.pack_into('<Q', self.image, base + sid * 8, ptr)

    # -- helpers -----------------------------------------------------------
    def record_addr(self, rid):
        return HEAP_BASE + rid * RECORD_STRIDE

    def name_addr(self, rid):
        return HEAP_BASE + 0x400000 + rid * 0x100

    def cooldown(self, rid):
        buf = self.records[self.record_addr(rid)]
        return struct.unpack_from('<f', buf, COOLDOWN_OFF)[0]

    def uses(self, rid):
        buf = self.records[self.record_addr(rid)]
        return struct.unpack_from('<i', buf, USES_OFF)[0]

    def set_cooldown(self, rid, value):
        buf = self.records[self.record_addr(rid)]
        struct.pack_into('<f', buf, COOLDOWN_OFF, value)

    def inject(self, entry):
        """Add a vehicle record + slot pointer to a live sandbox (the game
        builds these tables after a mission loads)."""
        rid = entry['id']
        addr = self.record_addr(rid)
        buf = bytearray(0x100)
        struct.pack_into('<I', buf, ID_OFF, rid)
        struct.pack_into('<f', buf, COOLDOWN_OFF, entry.get('cooldown', VANILLA))
        struct.pack_into('<i', buf, USES_OFF, entry.get('uses', -1))
        name_addr = self.name_addr(rid)
        raw = entry['name'].encode('latin-1') + b'\0'
        self.records['names'][name_addr] = raw + b'\0' * (0x200 - len(raw))
        struct.pack_into('<Q', buf, NAME_OFF, name_addr)
        self.records[addr] = buf
        struct.pack_into('<Q', self.image, TABLE_RVA + rid * 8, addr)

    def slot_target(self, sid):
        return struct.unpack_from('<Q', self.image, TABLE_RVA + sid * 8)[0]

    # -- the memory layer seen by the fake kernel32 ------------------------
    def _locate(self, addr, size):
        if self.hostile is not None and addr == self.hostile:
            raise RuntimeError('hostile address 0x%X (simulated FFI fault)' % addr)
        if addr < 0 or addr + size > 0x0000800000000000:
            return None
        off = addr - IMAGE_BASE
        if 0 <= off and off + size <= IMAGE_SIZE:
            return ('image', off)
        if HEAP_BASE <= addr < HEAP_BASE + 0x800000:
            return ('heap', addr)
        return None

    def read(self, addr, size):
        self.reads += 1
        where = self._locate(int(addr), int(size))
        if where is None:
            return None
        kind, pos = where
        if kind == 'image':
            return bytes(self.image[pos:pos + size])
        # heap: records and their name strings live in separate ranges
        for base, buf in self.records.items():
            if base == 'names':
                continue
            if base <= pos and pos + size <= base + len(buf):
                return bytes(buf[pos - base:pos - base + size])
        for base, raw in self.records['names'].items():
            if base <= pos and pos + size <= base + len(raw):
                return bytes(raw[pos - base:pos - base + size])
        return None

    def write(self, addr, data):
        self.writes += 1
        if self.fail_writes:
            return False
        if isinstance(data, str):                    # lupa may hand over Lua strings
            data = data.encode('latin-1')
        elif isinstance(data, dict):                 # a Lua table can arrive as a dict
            data = bytes(data[k] for k in sorted(data))
        elif not isinstance(data, (bytes, bytearray)):
            data = bytes(int(data[i]) for i in range(1, len(data) + 1))   # _LuaTable
        self.trace.append(('write', int(addr), bytes(data)))
        where = self._locate(int(addr), len(data))
        if where is None:
            return False
        kind, pos = where
        if kind == 'image':
            self.image[pos:pos + len(data)] = data
            return True
        for base, buf in self.records.items():
            if base == 'names':
                continue
            if base <= pos and pos + len(data) <= base + len(buf):
                buf[pos - base:pos - base + len(data)] = data
                return True
        return False


# ------------------------------------------------------------------ lua shim

LUA_SHIM = r"""
local py_read, py_write, py_ptr_seen = ...
local U64 = 18446744073709551616          -- 2^64 as a double

local ffi = {}
ffi.NULL = nil
ffi.cdef = function() end

local function check_ptr(n, ctype)
    -- model LuaJIT: a double that no 64-bit pointer can hold cannot be cast
    if type(n) ~= 'number' or n < 0 or n >= U64 or n ~= math.floor(n) then
        error("cannot convert 'number' to '" .. ctype .. "'", 2)
    end
    return n
end

local function scalar_meta(get, set)
    return {
        __index = function(t, k)
            if type(k) == 'number' then return get(t, k) end
            return rawget(t, k)
        end,
        __newindex = function(t, k, v)
            if type(k) == 'number' then return set(t, k, v) end
            rawset(t, k, v)
        end,
    }
end

local FLOAT_MT = scalar_meta(
    function(t, k) return py_bits_f32(t.__cell.bits % 4294967296) end,
    function(t, k, v) t.__cell.bits = py_f32_bits(v) end)
local U32_MT = scalar_meta(
    function(t, k) return t.__cell.bits % 4294967296 end,
    function(t, k, v)
        local n = check_ptr(v, 'uint32_t')
        t.__cell.bits = n % 4294967296
    end)
local SIZE_MT = scalar_meta(
    function(t, k) return t.__cell.val end,
    function(t, k, v)
        if type(v) ~= 'number' then error("cannot convert to 'size_t'", 2) end
        t.__cell.val = math.floor(v)
    end)
local BYTE_MT = scalar_meta(
    function(t, k) return string.byte(t.__data, k + 1) or 0 end,
    function(t, k, v) error('byte writes are not used by the addon', 2) end)

local function new_scalar(ctype, cell, mt)
    local t = setmetatable({__ctype = ctype, __cell = cell or {bits = 0, val = 0}}, mt)
    return t
end

function ffi.new(ctype, n)
    if ctype == 'uint8_t[?]' then
        return setmetatable({__ctype = ctype, __n = n, __data = string.rep('\0', n)}, BYTE_MT)
    elseif ctype == 'float[1]' then
        return new_scalar(ctype, nil, FLOAT_MT)
    elseif ctype == 'uint32_t[1]' then
        return new_scalar(ctype, nil, U32_MT)
    elseif ctype == 'size_t[1]' then
        return new_scalar(ctype, nil, SIZE_MT)
    end
    error('sandbox ffi.new does not implement ' .. tostring(ctype), 2)
end

function ffi.cast(ctype, v)
    if ctype == 'uint8_t *' or ctype == 'void *' then
        local n = check_ptr(v, ctype)
        py_ptr_seen(n)
        return {__addr = n, __ctype = ctype}
    elseif ctype == 'uintptr_t' then
        if type(v) ~= 'table' or v.__addr == nil then
            error("cannot convert to 'uintptr_t'", 2)
        end
        return v.__addr
    elseif ctype == 'uint32_t *' then
        if type(v) ~= 'table' or v.__cell == nil then
            error("cannot convert to 'uint32_t *'", 2)
        end
        return new_scalar(ctype, v.__cell, U32_MT)
    end
    error('sandbox ffi.cast does not implement ' .. tostring(ctype), 2)
end

function ffi.string(buf, len)
    if type(buf) == 'table' and buf.__data then
        return buf.__data:sub(1, len or #buf.__data)
    end
    error('sandbox ffi.string expects a uint8 buffer', 2)
end

local kernel = {}
function kernel.GetCurrentProcess() return 1 end
function kernel.GetModuleHandleA(name)
    if name == 'game.dll' and py_module_base then
        return ffi.cast('void *', py_module_base)
    end
    return nil
end
function kernel.ReadProcessMemory(proc, addrptr, buf, size, got)
    local data = py_read(addrptr.__addr, size)
    if not data then return 0 end
    buf.__data = data
    if got then got[0] = size end
    return 1
end
function kernel.WriteProcessMemory(proc, addrptr, src, size, wrote)
    -- lupa decodes Lua strings as UTF-8 on the way into Python, so raw bytes
    -- travel as a table of numbers instead
    local bytes = {}
    for i = 1, size do bytes[i] = string.byte(src, i) end
    if not py_write(addrptr.__addr, bytes) then return 0 end
    if wrote then wrote[0] = size end
    return 1
end
function kernel.VirtualProtect(addrptr, size, newp, oldp)
    if oldp then oldp[0] = 4 end
    return 1
end

function ffi.load(name)
    if name ~= 'kernel32' then error('sandbox ffi.load only knows kernel32', 2) end
    return kernel
end

package.loaded['ffi'] = ffi
"""


class Sandbox(object):
    """Load the addon against the fake environment and drive its update chain."""

    RUNTIMES = ('lua51', 'lua53', 'luajit21')

    def __init__(self, source, runtime='lua51', records=None, table_ids=None,
                 config=None, chain=True, loader=True, ffi=True, hostile=None,
                 fail_writes=False, module=True, capture_pcall=False):
        self.source = source
        self.runtime_name = runtime
        self.mod = importlib.import_module('lupa.' + runtime)
        if records is None and table_ids is None:
            records, table_ids = self.vehicle_world()
        self.mem = FakeMemory(records or [], table_ids)
        self.mem.hostile = hostile
        self.mem.fail_writes = fail_writes
        self.clock = [0.0]
        self.root = tempfile.mkdtemp(prefix='vc_sandbox_')
        self.log_path = os.path.join(self.root, 'CowboyBingus', 'Helldivers2', 'Logs',
                                     'VehicleCooldown.log')
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self.cfg_dir = os.path.join(self.root, 'CowboyBingus', 'Helldivers2', 'VehicleCooldown')
        os.makedirs(self.cfg_dir, exist_ok=True)
        if config is not False:
            lines = {'cooldown': 'yes', 'cooldown_s': 390, 'stable_s': 6, 'uptime_s': 60}
            lines.update(config or {})
            with open(os.path.join(self.cfg_dir, 'config.txt'), 'w') as fh:
                fh.write(''.join('%s=%s\n' % kv for kv in lines.items()))
        self.rt = self.mod.LuaRuntime()
        self.pcall_errors = []
        self._install(chain=chain, loader=loader, ffi=ffi, module=module,
                      capture_pcall=capture_pcall)
        self.frames = 0

    # -- world fixtures ----------------------------------------------------
    @staticmethod
    def vehicle_world(poison=True, include_records=True):
        """Bastion (1) + Maelstrom (50) + one non-vehicle record, optionally
        one poison record whose name pointer is 0xFFFFFFFFFFFFFFFF."""
        records = []
        table_ids = {}
        if include_records:
            records = [
                {'id': 1, 'name': 'VEHICLES. BASTION(TANK)', 'cooldown': VANILLA},
                # mission stratagems are out of scope by default (missions=no)
                {'id': 3, 'name': 'MISSIONS. EXTRACTION BEACON', 'cooldown': 180.0},
                {'id': 50, 'name': 'VEHICLES. STORM(TANK)', 'cooldown': VANILLA},
            ]
            if poison:
                # a readable record whose name pointer is the classic "-1"
                # filler: not an address any 64-bit pointer can hold
                records.append({'id': 2, 'name': None, 'name_ptr': POISON,
                                'cooldown': VANILLA})
            for entry in records:
                table_ids[entry['id']] = HEAP_BASE + entry['id'] * RECORD_STRIDE
        return records, table_ids

    # -- environment -------------------------------------------------------
    def _install(self, chain=True, loader=True, ffi=True, module=True, capture_pcall=False):
        rt, g = self.rt, self.rt.globals()
        if capture_pcall:
            # the deployed 1.5.1 build swallowed its own errors with
            # pcall(tick_cooldown); this wrapper records them so a test can
            # report what the game never showed
            self.capture_pcall = True
            rt.execute("""
                __vc_pcall_log = {}
                local real_pcall = pcall
                local log = __vc_pcall_log
                pcall = function(f, ...)
                    local r = {real_pcall(f, ...)}
                    if not r[1] then log[#log+1] = tostring(r[2]) end
                    return unpack(r)
                end
            """)
        g['py_read'] = self.mem.read
        g['py_write'] = self.mem.write
        g['py_ptr_seen'] = self.mem.casts.append
        g['py_image_base'] = IMAGE_BASE
        g['py_module_base'] = IMAGE_BASE if module else None
        g['py_f32_bits'] = lambda v: struct.unpack('<I', _f32(v))[0]
        g['py_bits_f32'] = lambda b: struct.unpack('<f', struct.pack('<I', int(b) & 0xFFFFFFFF))[0]
        g.os['clock'] = lambda: self.clock[0]
        g.os['getenv'] = lambda name: self.root if name == 'LOCALAPPDATA' else None
        g.os['execute'] = lambda cmd: 0
        if chain:
            rt.execute("update = function() return 'chain' end")
        if loader:
            rt.execute("CowboyBingusModLoader = {api=1, version=18}")
        if ffi:
            rt.execute(LUA_SHIM, self.mem.read, self.mem.write, self.mem.casts.append,
                       IMAGE_BASE)
        else:
            rt.execute("package.preload['ffi'] = nil package.loaded['ffi'] = nil")

    # -- driving -----------------------------------------------------------
    def load(self):
        loader = 'loadstring' if self.runtime_name in ('lua51', 'luajit20', 'luajit21') else 'load'
        self.rt.globals()['__vc_src'] = self.source
        self.rt.execute("local fn = %s(__vc_src) if fn then fn() end" % loader)
        return self.rt.globals()['HD2VehicleCooldown']

    def load_backdoor(self):
        """Load with the test backdoor instead of installing the update hook."""
        loader = 'loadstring' if self.runtime_name in ('lua51', 'luajit20', 'luajit21') else 'load'
        self.rt.globals()['__vc_src'] = self.source
        self.rt.execute('__HD2_VC_TEST = true')
        self.rt.execute('HD2VehicleCooldownTest = %s(__vc_src)()' % loader)
        return self.rt.globals()['HD2VehicleCooldownTest']

    def eval(self, expression):
        return self.rt.eval(expression)

    def pcall_log(self):
        """Errors the loaded build swallowed (only when capture_pcall=True)."""
        if not getattr(self, 'capture_pcall', False):
            return []
        table = self.rt.eval('__vc_pcall_log')
        return [str(table[i]) for i in range(1, len(table) + 1)]

    def pcall_log_unique(self):
        seen = []
        for err in self.pcall_log():
            if err not in seen:
                seen.append(err)
        return seen

    def step(self, dt=0.05, frames=1):
        for _ in range(frames):
            self.clock[0] += dt
            self.rt.execute("if type(update)=='function' then update() end")
            self.frames += 1

    def run_for(self, seconds, dt=0.05):
        self.step(dt=dt, frames=int(round(seconds / dt)))

    def run_until(self, predicate, max_seconds=300.0, dt=0.05):
        waited = 0.0
        while waited < max_seconds:
            if predicate():
                return True
            self.step(dt=dt)
            waited += dt
        return predicate()

    # -- observation -------------------------------------------------------
    def state(self):
        return self.rt.globals()['HD2VehicleCooldown']

    def field(self, name):
        st = self.state()
        return st[name] if st is not None else None

    def log_text(self):
        if not os.path.exists(self.log_path):
            return ''
        with open(self.log_path, 'r') as fh:
            return fh.read()

    def log_lines(self):
        return [ln for ln in self.log_text().splitlines() if ln.strip()]

    def find(self, pattern):
        return [ln for ln in self.log_lines() if re.search(pattern, ln)]

    def cleanup(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
