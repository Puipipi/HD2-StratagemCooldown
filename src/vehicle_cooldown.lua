-- HD2-Addon: mods/codex/vehicle_cooldown
-- HD2 Stratagem Cooldown 1.9.0 - one addon for every stratagem colour, on top
-- of the resolver/safety core that is already verified in game:
--   * red   : ORBITAL. (orbital) and EAGLE. (eagle). EAGLE. REARM is the real
--             Eagle cycle: Eagle stratagems spend charges and one rearm
--             restores all of them, so its cooldown paces the whole family.
--   * blue  : TEAM WEAPONS. / BACKPACK. / CONSUMABLES. plus a mutually
--             exclusive choice of vehicles / mechs / both / all
--   * green : SENTRYS. / SENTRIES. / EMPLACEMENTS.
--   * charges: the uses field at +0x50 (int32, -1 = unlimited) can be scaled or
--             fixed, so Orbital Laser (3), the mechs (3) and the Eagle entries
--             (1..4) can be changed too.
-- Scope lives in VehicleCooldown/config.txt; the guide is at the bottom.
--
-- 1.7.0 (diagnostic build, after the first real in-game run of 1.6.0)
--   The 1.6.0 fix works mechanically - the game log shows
--     vehicle records appeared: 3 target(s) [1=VEHICLES. BASTION(TANK)/780,
--       10=VEHICLES. COMBAT WALKER OBSIDIAN/420,
--       105=VEHICLES. FAST RECON VEHICLE (FRV)/480]
--     cooldown applied to 3 target(s) [...]      errors=0   state=watch
--   and the field stays patched (the watch loop never has to re-apply it), yet
--   the in-game cooldown did not change. So the write lands, but +0x68 of that
--   record is not (or no longer) what the stratagem recharge uses.
--   This build therefore, in one session:
--     * writes much earlier (default uptime gate 15s instead of 120s) - if the
--       engine snapshots the definition during boot, a late write is useless;
--     * patches the cooldown field AND every 4-byte field in the same record
--       that currently mirrors that exact value (a "remaining = full" copy is
--       the classic mirror), and logs every offset it patched;
--     * logs a one-shot float map of each vehicle record, so the field that
--       carries the live cooldown can be identified from the log alone;
--     * logs all name-matched candidates (including ones whose cooldown is out
--       of range) and scans ids 0..511, so duplicates/templates show up;
--     * logs whenever the engine itself changes a patched field (that proves
--       the field is live state rather than a dead copy).
--   Nothing else changed: same stability gate, readback verification, rollback,
--   error accounting and heartbeat as 1.6.0.
--
-- What it does
--   * cooldown: shortens the redeploy cooldown of EVERY stratagem vehicle
--     (tanks, exos, FRV - identified by name at runtime).
--
-- Why the old mods crashed (and this one must not)
--   The old family wrote live engine records during the boot window, exactly
--   when the engine rebuilds those tables; writes landed on stale or
--   half-initialised records and the consumer code died at fixed offsets
--   (0x66d1ff/d26c/d646). This rewrite never writes during instability:
--     LOCATE -> OBSERVE (record pointers stable for stable_s x 1s AND process
--              uptime over uptime_s) -> WRITE (each field verified by
--              readback) -> WATCH (read-only every 5s; a moved pointer means
--              the engine is rebuilding - go back to OBSERVE and only re-write
--              once stable; any write/verify failure restores every original
--              value and disables the feature for the rest of the session).
--
-- 1.6.0 root cause fix (1.5.1-fixed / internal v1.1 NEVER applied anything)
--   The game evidence is unambiguous: 99 sessions reached the uptime gate and
--   logged exactly one line ("uptime gate passed - observing table stability");
--   across 351 runtime-state snapshots the addon never logged a scan result,
--   never changed M.phase again, never wrote a cooldown and never reported an
--   error. Three independent defects produced that, all of them invisible
--   because pcall(tick_cooldown) swallowed the exceptions:
--
--   1) SHADOWED TABLE BASE (the killer, identical in v1.0 and v1.1)
--        local table_base,locate_err=locate_table()   -- new local!
--      declares a second local that shadows the `table_base` upvalue already
--      captured by slot_ptr()/rec_info(). The resolver's result went into a
--      local nobody read, the functions kept seeing nil, and the very first
--      slot read of the very first scan raised
--        "attempt to perform arithmetic on upvalue 'table_base' (a nil value)"
--      => permanent silence, in every session, at the first sweep.
--      Now: the existing upvalue is assigned (see `table_base=table_base_at_load`)
--      and the resolved base is published as M.table_base for verification.
--   2) WRONG SELF SIGNATURE ON THE STABILITY GATE
--      `cd:snapshot_ok(now,cfg)` (method call) against
--      `F.snapshot_ok=function(now,cfg)` put the feature table into `now`, so
--      `now-F.last_sample` raised. Even with (1) fixed the addon could never
--      reach a write. Now declared as `function(F,now,cfg)`.
--   3) UNGUARDED 146-SLOT SWEEP (defence in depth, not the observed crash)
--      every 8-byte slot value was treated as a pointer and every record's
--      name pointer was followed. A non-address filler (0xFFFFFFFFFFFFFFFF)
--      becomes a double >= 2^64 that ffi.cast cannot represent, and one bad
--      slot aborted the whole sweep. Now every pointer is range-checked before
--      it reaches the FFI, every slot read is contained, and any unexpected
--      fault is logged and counted instead of vanishing.
--
--   Remaining hardening in 1.6.0:
--     * the scan publishes what it saw (slots / readable records / candidates
--       / rejects / contained faults) plus a 60s heartbeat, so "no effect" is
--       always answerable from the log;
--     * the resolver is re-run (bounded, 2 min apart) while the table yields no
--       readable record, so a stale base can heal itself;
--     * an empty target set is never cached (v1.1 fix, kept).
--
-- Config: %LOCALAPPDATA%/CowboyBingus/Helldivers2/VehicleCooldown/config.txt
--   cooldown=yes/no        vehicle cooldown feature (default yes)
--   percent=50             cooldown as a percentage of each stratagem's own
--                          vanilla value (50 = halve the tank's 780 to 390,
--                          the FRV's 480 to 240, a mech's 420 to 210).
--                          percent=0 switches to the fixed cooldown_s below.
--   cooldown_s=390         fixed target in seconds, only used when percent=0
--   stable_s=6             pointer stability window before writing
--   uptime_s=0             minimum process uptime before the first write
--                          (1.7.1: write at load, like the v2 mod that worked;
--                           1.6.0's 120s delay was too late - the game had
--                           already built its runtime stratagem state)
--   (clutch/clutch_s are accepted for compatibility with the 1.5.x config
--    file; this build does not implement the clutch feature and says so.)
--
-- Diagnostics (readable from the game's SmoothBoot runtime snapshot too):
--   M.status / M.phase / M.version / M.errors / M.last_error / M.slots /
--   M.records / M.matched / M.rejects / M.bad_slots / M.scans / M.relocates
local KEY='HD2VehicleCooldown'
if rawget(_G,KEY) then return rawget(_G,KEY) end
local M={version='2.1.6',status='starting',errors=0}
-- BAKED is injected by work/standalone/build_vc.py when a manager option was
-- chosen. It only supplies DEFAULTS: any key the player leaves uncommented in
-- config.txt still wins, so the manager preset and the file can be combined.
-- Injected by the build: ROLE is 'core' (patches) or 'provider' (only records
-- the player's choice for one manager block, then stays dormant).
local ROLE='core'
local MARKER=nil
local MARKER_VALUE=nil
local BAKED=nil
rawset(_G,KEY,M)

local HOME=(os.getenv('LOCALAPPDATA') or os.getenv('TEMP') or '.')..'/CowboyBingus/Helldivers2/'
local LOG=HOME..'Logs/VehicleCooldown.log'
local CFG=HOME..'VehicleCooldown/config.txt'
local function log(s)
    M.status=s
    pcall(function()
        local f=io.open(LOG,'a')
        if f then f:write(os.date('!%Y-%m-%dT%H:%M:%SZ')..' '..s..'\n');f:close() end
    end)
end

-- A swallowed error is what hid this bug for 165 sessions: every unexpected
-- failure is recorded in M and written to the log (rate limited).
local function note_error(where,err)
    M.errors=(M.errors or 0)+1
    M.last_error=tostring(where)..': '..tostring(err)
    local now=os.clock()
    if not M.err_logged or now-M.err_logged>=10 then
        M.err_logged=now
        log('error: '..M.last_error)
    end
end

local function conf()
    local d={cooldown=true,percent=50,min_cooldown=60,uses_add=0,uses_unlimited=false,
             stable_s=1,uptime_s=0,probe=false,
             red=true,orbital=true,eagle=true,
             blue=true,blue_scope='all',
             green=true,missions=false}
    if type(BAKED)=='table' then
        for k,v in pairs(BAKED) do d[k]=v end
    end
    local ok,text=pcall(function()
        local f=io.open(CFG,'r') if not f then return nil end
        local t=f:read('*a') f:close() return t
    end)
    if not ok or not text then
        pcall(function()
            os.execute('mkdir "'..HOME:gsub('/','\\')..'VehicleCooldown" 2>nul')
            local w=io.open(CFG,'w')
            if w then
                w:write('cooldown=yes\npercent=50\nmin_cooldown=60\nuses_add=0\nuses_unlimited=no\n')
                w:write('red=yes\norbital=yes\neagle=yes\n')
                w:write('blue=yes\nblue_scope=all\ngreen=yes\nmissions=no\n')
                w:write('stable_s=1\nuptime_s=0\nprobe=no\n')
                w:close()
            end
        end)
        return d
    end
    for line in text:gmatch('[^\r\n]+') do
        local v=line:match('^%s*cooldown%s*=%s*(%a+)%s*$')
        if v then d.cooldown=(v=='yes' or v=='true' or v=='on') end
        v=line:match('^%s*probe%s*=%s*(%a+)%s*$')
        if v then d.probe=(v=='yes' or v=='true' or v=='on') end
        for _,k in ipairs({'red','orbital','eagle','blue','green','missions','uses_unlimited'}) do
            v=line:match('^%s*'..k..'%s*=%s*(%a+)%s*$')
            if v then
                d[k]=(v=='yes' or v=='true' or v=='on')
                d.explicit=d.explicit or {} d.explicit[k]=true
                d.explicit_vals=d.explicit_vals or {} d.explicit_vals[k]=d[k]
            end
        end
        v=line:match('^%s*manager_db%s*=%s*(.+)$')
        if v then d.manager_db=v:gsub('%s+$','') end
        v=line:match('^%s*scan_dir%s*=%s*(.+)$')
        if v then d.scan_dir=v:gsub('%s+$','') end
        v=line:match('^%s*blue_scope%s*=%s*(%a+)%s*$')
        if v then
            d.blue_scope=v
            d.explicit=d.explicit or {}
            d.explicit.blue_scope=true
            d.explicit_vals=d.explicit_vals or {}
            d.explicit_vals.blue_scope=v
        end
        for _,k in ipairs({'percent','min_cooldown','uses_add','stable_s','uptime_s'}) do
            v=line:match('^%s*'..k..'%s*=%s*(%d+%.?%d*)%s*$')
            if v then
                d[k]=tonumber(v)
                d.explicit=d.explicit or {}
                d.explicit[k]=true
                d.explicit_vals=d.explicit_vals or {}
                d.explicit_vals[k]=tonumber(v)
            end
        end
    end
    return d
end

local ok_ffi,ffi=pcall(require,'ffi')
if not ok_ffi or not ffi then
    M.status='no ffi'; log('FFI unavailable - dormant')
    return M
end
local loader=rawget(_G,'CowboyBingusModLoader')
if not loader then
    M.status='no bingus loader'; log('no Bingus loader - dormant')
    return M
end
ffi.cdef[[
    void *GetCurrentProcess(void);
    void *GetModuleHandleA(const char *module_name);
    int ReadProcessMemory(void *process,const void *address,void *buffer,size_t size,size_t *read);
    int WriteProcessMemory(void *process,void *address,const void *buffer,size_t size,size_t *written);
    int VirtualProtect(void *address,size_t size,uint32_t new_protect,uint32_t *old_protect);
]]
local kernel=ffi.load('kernel32')
local process=kernel.GetCurrentProcess()
local function ptr(n) return ffi.cast('uint8_t *',n) end
local function addr_num(p) return tonumber(ffi.cast('uintptr_t',p)) end

-- 1.6.0: nothing may reach ffi.cast() unless it is a value a x64 user-mode
-- pointer can actually hold. A double >= 2^64 (or a negative / fractional one)
-- cannot be represented as a pointer and makes the FFI layer raise; that was
-- the silent killer of 1.5.1-fixed.
local MIN_PTR,MAX_PTR=0x10000,0x00007FFFFFFFFFFF
local function sane_ptr(v)
    if type(v)~='number' then return false end
    if v<MIN_PTR or v>MAX_PTR then return false end
    return v==math.floor(v)
end

-- string.format('%X', <address>) is not portable across the runtimes this addon
-- family is loaded by (PUC Lua 5.1 truncates large doubles), so addresses are
-- rendered with double-safe integer maths instead.
local function hex(n)
    if type(n)~='number' then return tostring(n) end
    n=math.floor(n)
    if n<=0 then return '0x0' end
    local digits,out='0123456789ABCDEF',''
    while n>0 do
        local r=n%16
        out=digits:sub(r+1,r+1)..out
        n=(n-r)/16
    end
    return '0x'..out
end

local function read_at(address,size)
    if not sane_ptr(address) then return nil end
    if type(size)~='number' or size<=0 or size>0x100000 then return nil end
    local buf=ffi.new('uint8_t[?]',size)
    local got=ffi.new('size_t[1]')
    if kernel.ReadProcessMemory(process,ptr(address),buf,size,got)==0 or tonumber(got[0])~=size then return nil end
    return ffi.string(buf,size)
end
local function u32_at(s,pos)
    if not s or pos+3>#s then return nil end
    local a,b,c,d=s:byte(pos,pos+3)
    return a+b*256+c*65536+d*16777216
end
local function i32_at(s,pos)
    local v=u32_at(s,pos)
    if not v then return nil end
    if v>=0x80000000 then return v-0x100000000 end
    return v
end
local function u64_at(s,pos)
    local lo,hi=u32_at(s,pos),u32_at(s,pos+4)
    if not lo or not hi then return nil end
    return lo+hi*4294967296
end
local function u32_bytes(v)
    v=v%4294967296
    return string.char(v%256,math.floor(v/256)%256,math.floor(v/65536)%256,math.floor(v/16777216)%256)
end
local function write4(address,value)
    if not sane_ptr(address) then return false end
    local old=ffi.new('uint32_t[1]')
    if kernel.VirtualProtect(ptr(address),4,0x04,old)==0 then return false end
    local bytes=u32_bytes(value)
    local wrote=ffi.new('size_t[1]')
    local ok=kernel.WriteProcessMemory(process,ptr(address),bytes,4,wrote)~=0 and tonumber(wrote[0])==4
    local ign=ffi.new('uint32_t[1]')
    kernel.VirtualProtect(ptr(address),4,old[0],ign)
    return ok and read_at(address,4)==bytes
end
local fbuf=ffi.new('float[1]')
local function f32_bits(v) fbuf[0]=v return tonumber(ffi.cast('uint32_t *',fbuf)[0]) end
local function f32_from_bits(bits) ffi.cast('uint32_t *',fbuf)[0]=bits return tonumber(fbuf[0]) end
local function read_cstr(address,maxlen)
    if not sane_ptr(address) then return nil end
    local s=read_at(address,maxlen or 160)
    if not s then return nil end
    local z=s:find('\0',1,true)
    if z then s=s:sub(1,z-1) end
    if #s<2 then return nil end
    local printable=0
    for i=1,#s do local b=s:byte(i) if b>=32 and b<=126 then printable=printable+1 end end
    if printable<math.floor(#s*0.8) then return nil end
    return s:upper()
end

-- ============ phase 1: locate the authoritative StratagemInfo table =======
-- Same resolver family as Tank Cooldown v2 (AOB pair -> consumer -> table).
local table_base=nil
local function locate_table()
    local game=kernel.GetModuleHandleA('game.dll')
    if game==nil or game==ffi.NULL then return nil,'game.dll unavailable' end
    local game_base=addr_num(game)
    local dos=read_at(game_base,0x1000)
    if not dos or dos:sub(1,2)~='MZ' then return nil,'bad DOS header' end
    local peoff=u32_at(dos,0x3C+1)
    local pe=peoff and read_at(game_base+peoff,0x200) or nil
    if not pe or pe:sub(1,4)~='PE\0\0' then return nil,'bad PE header' end
    local image_size=u32_at(pe,24+0x38+1)
    if not image_size or image_size<0x100000 or image_size>0x10000000 then return nil,'bad image size' end
    local fixed1=string.char(0x49,0x8B,0x84,0xC7)
    local fixed2=string.char(0x44,0x8B,0x80,0xC8,0x00,0x00,0x00,0x8B,0xC2,0x45,0x85,0xC0)
    local matches={}
    local chunk,overlap,off,carry=0x100000,0x40,0,''
    while off<image_size do
        local amount=math.min(chunk,image_size-off)
        local data=read_at(game_base+off,amount)
        if data then
            local w=carry..data
            local wb=game_base+off-#carry
            local from=1
            while true do
                local p=w:find(fixed1,from,true)
                if not p then break end
                if p+7+#fixed2<=#w and w:sub(p+8,p+8+#fixed2-1)==fixed2 then
                    local a=wb+p-1
                    local dup=false
                    for _,m in ipairs(matches) do
                        if m==a then dup=true break end
                    end
                    if not dup then matches[#matches+1]=a end
                    if #matches>1 then return nil,'resolver ambiguous ('..#matches..')' end
                end
                from=p+1
            end
            carry=data:sub(-overlap)
        else carry='' end
        off=off+amount
    end
    if #matches~=1 then return nil,'resolver match='..#matches end
    local consumer=matches[1]
    local inst=read_at(consumer,0x20)
    local disp=i32_at(inst,5)
    if not disp then return nil,'disp decode failed' end
    local back_start=math.max(game_base,consumer-0x1000)
    local back=read_at(back_start,consumer-back_start)
    local r15_base=nil
    if back then
        for i=#back-6,1,-1 do
            if back:byte(i)==0x4C and back:byte(i+1)==0x8D and back:byte(i+2)==0x3D then
                local ds=i32_at(back,i+3)
                if ds then
                    local abs=back_start+i-1
                    local target=abs+7+ds
                    if target>=game_base and target<game_base+0x100000 then r15_base=target break end
                end
            end
        end
    end
    if not r15_base then return nil,'base anchor missing' end
    local base=r15_base+disp
    if not sane_ptr(base) then return nil,'resolved base outside the address range' end
    return base
end

-- record layout (validated by Tank Cooldown v2)
local OFF_ID,OFF_HASH,OFF_STR1,OFF_STR2,OFF_STR3=0x00,0x04,0x10,0x18,0x20
local OFF_USES=0x50          -- int32 charges; -1 = unlimited (verified live)
local OFF_COOLDOWN,REC_READ=0x68,0xB0
-- 1.9.0: the stratagem category lives in the name prefix, which follows the
-- in-game colour coding. Charges live at +0x50 (int32, -1 = unlimited).
--   ORBITAL.                                   -> orbital (red)
--   EAGLE.                                     -> eagle   (red; REARM included)
--   TEAM WEAPONS. / BACKPACK. / CONSUMABLES.   -> support (blue)
--   SENTRYS. / SENTRIES. / EMPLACEMENTS.       -> green
--   VEHICLES. <tank|FRV>                       -> vehicle (blue scope)
--   VEHICLES. COMBAT WALKER*                   -> mech    (blue scope)
--   MISSIONS.*                                 -> mission (off by default)
--   PRESIDENT REWARDS.*                        -> mapped by keyword
local cfg                     -- assigned from conf() below; declared early so
                              -- the classification helpers close over it
local function prefix_of(name)
    local dot=name:find('.',1,true)
    return dot and name:sub(1,dot-1) or name
end

local function classify(name)
    if not name then return nil end
    if name:find('COMBAT WALKER',1,true) then return 'mech' end
    -- green also covers the mine family (minefield, incendiary mines, anti-tank
    -- mines) and the defensive structures, whichever prefix the game files them
    -- under - checked before the prefix table so a mine under MISSIONS. or with
    -- no prefix at all still lands in green
    if name:find('MINE',1,true) or name:find('TESLA',1,true)
       or name:find('SHIELD GENERATOR',1,true) or name:find('RELAY',1,true) then
        return 'green'
    end
    local p=prefix_of(name)
    if p=='ORBITAL' then return 'orbital' end
    if p=='EAGLE' then return 'eagle' end
    if p=='TEAM WEAPONS' or p=='BACKPACK' or p=='CONSUMABLES' then return 'support' end
    if p=='SENTRYS' or p=='SENTRIES' or p=='EMPLACEMENTS' then return 'green' end
    if p=='VEHICLES' then return 'vehicle' end
    if p=='MISSIONS' or p=='MISSIONS CLAN STATION' then return 'mission' end
    if p=='PRESIDENT REWARDS' then
        if name:find('MACHINEGUN',1,true) or name:find('BACKPACK',1,true) then return 'support' end
        if name:find('SENTRY',1,true) then return 'green' end
        return 'other'
    end
    if p=='TANK' then return 'tank_action' end
    return 'other'
end

local function in_scope(kind)
    if kind==nil or not cfg.cooldown then return false end
    local scope=cfg.blue_scope or 'all'
    if kind=='orbital' then return cfg.red==true and cfg.orbital==true end
    if kind=='eagle'   then return cfg.red==true and cfg.eagle==true end
    if kind=='support' then return cfg.blue==true and scope=='all' end
    if kind=='vehicle' then
        return cfg.blue==true and (scope=='vehicles' or scope=='both' or scope=='all')
    end
    if kind=='mech' then
        return cfg.blue==true and (scope=='mechs' or scope=='both' or scope=='all')
    end
    if kind=='green'   then return cfg.green==true end
    if kind=='mission' then return cfg.missions==true end
    return false
end

-- 1.9.1 charges: +0x50, int32, -1 = unlimited.
--   uses_add=1|2|3  add that many charges to every limited stratagem
--   uses_unlimited=yes  remove the limit entirely (finite -> -1)
-- A record that is already unlimited is never touched (there is nothing to add)
-- and a limit is never invented where the game has none.
local function uses_target(orig)
    if type(orig)~='number' then return nil end
    if orig<0 then return nil end                      -- already unlimited
    if cfg.uses_unlimited==true then return -1 end
    local add=math.floor(tonumber(cfg.uses_add) or 0)
    if add<=0 then return nil end
    if add>3 then add=3 end
    local want=orig+add
    if want>99 then want=99 end
    if want==orig then return nil end
    return want
end
local function slot_ptr(id)
    local b=read_at(table_base+id*8,8)
    if not b then return nil end
    local p=u64_at(b,1)
    if not sane_ptr(p) then return nil end
    return p
end
local function rec_info(id)
    local p=slot_ptr(id)
    if not p then return nil end
    local rec=read_at(p,REC_READ)
    if not rec then return nil end
    return {
        ptr=p,
        id=u32_at(rec,OFF_ID+1) or 0,
        cooldown_bits=u32_at(rec,OFF_COOLDOWN+1) or 0,
        hash=u32_at(rec,OFF_HASH+1) or 0,
        name=read_cstr(u64_at(rec,OFF_STR1+1) or 0,160),
    }
end

-- ============ safe writer state machine (per feature) =====================
-- state: 'observe' | 'writing' | 'watch' | 'disabled'
-- 1.6.0: the stability gate is called as `cd:snapshot_ok(now,cfg)` (method
-- syntax) but every 1.5.x build declared it as `function(now,cfg)`, so `now`
-- received the feature table and `now-F.last_sample` raised on the first
-- stability sample. pcall(tick_cooldown) turned that into permanent silence -
-- this is the second fatal defect fixed in 1.6.0.
local function make_feature(name,enabled_check)
    local F={name=name,state='observe',written={},disabled_reason=nil}
    F.last_sample=0
    F.snapshot_ok=function(F,now,cfg)
        -- memory reads at most once per second, never per frame
        if now-F.last_sample<1 then return F.stable_enough==true end
        F.last_sample=now
        local changed=false
        for id,rec in pairs(F.targets or {}) do
            local p=slot_ptr(id)
            if p~=rec.ptr then changed=true rec.ptr=p end
        end
        if changed or not F.stable_since then
            F.stable_since=now
            F.stable_enough=false
        end
        F.stable_enough=(now-F.stable_since)>=(cfg.stable_s or 6)
        return F.stable_enough
    end
    return F
end

if rawget(_G,'__HD2_VC_TEST')==true then
    return {
        make_feature=make_feature, locate_table=function() return locate_table() end,
        classify=classify, in_scope=in_scope, uses_target=uses_target,
        u32_bytes=u32_bytes, sane_ptr=sane_ptr,
        f32_bits=f32_bits, f32_from_bits=f32_from_bits, conf=conf,
    }
end
cfg=conf()
-- Resolve the table ONCE at load, exactly like the original TankCooldown:
-- a failed resolver means the build is unknown - retrying per frame would scan
-- game.dll's whole image every frame (that mistake cost ~54ms/frame).
--
-- 1.6.0 ROOT CAUSE: every 1.5.x build wrote
--     local table_base,locate_err=locate_table()
-- which declares a SECOND local that shadows the `table_base` upvalue already
-- captured by slot_ptr()/rec_info()/locate_table(). The resolver therefore
-- stored the base into a local nobody read, while the functions kept seeing
-- nil - so the first sweep of the first scan died on
--     "attempt to perform arithmetic on upvalue 'table_base' (a nil value)"
-- inside pcall(tick_cooldown), and the addon stayed silent for the whole
-- session. That single shadowing line is why 99 gated sessions, v1.0 and v1.1
-- alike, never logged a scan result and never changed a cooldown value.
-- The resolved value must be assigned to the existing upvalue:
local table_base_at_load,locate_err=locate_table()
table_base=table_base_at_load
if not table_base then
    M.status='locate failed: '..tostring(locate_err)
    log('STOPPED at load: '..M.status)
    return M
end
M.table_base=table_base
log('table located at load: base='..hex(table_base)..' (single pass)')
local function desired_bits() return f32_bits(cfg.cooldown_s or 390) end

-- 1.9.1: the cooldown choice is one of three presets - 100 (unchanged),
-- 80 (20% shorter) or 50 (half). Anything else is snapped to the nearest preset
-- and logged, so a typo cannot silently produce a different gameplay setting.
do
    local allowed={100,80,50}
    local want=tonumber(cfg.percent) or 50
    local best=allowed[1]
    for _,value in ipairs(allowed) do
        if math.abs(value-want)<math.abs(best-want) then best=value end
    end
    if want~=best then
        log(string.format('percent=%s is not one of 100/80/50 - using %s',
            tostring(cfg.percent),tostring(best)))
    end
    cfg.percent=best
end

-- 1.7.2/1.9.0: percent = 50 means "half of THIS stratagem's own cooldown" (the
-- v2 mod called the same option Default50). percent=0 falls back to the fixed
-- cooldown_s. A percentage never lengthens a stratagem unless it is above 100.
-- The floor is 1s, not 30s: Eagle entries legitimately sit at 15s.
local function target_bits_for(orig)
    local pct=tonumber(cfg.percent) or 50
    local want=orig*pct/100
    if pct<=100 and want>orig then want=orig end
    if want<1 then want=1 elseif want>7200 then want=7200 end
    return f32_bits(want),want
end
-- ---------------------------------------------------------------------------
-- 1.9.4 manager blocks
--   red / blue / green / charges: a PROVIDER addon writes opt_<axis>.txt and
--   stays dormant. The CORE (shipped with the cooldown block) merges those
--   markers, so five independent groups can be ticked at once without two
--   addons fighting over one field. Uncommented config.txt keys still win.
-- ---------------------------------------------------------------------------
local OPT_DIR=HOME..'VehicleCooldown/'

if ROLE=='provider' then
    local f=io.open(OPT_DIR..tostring(MARKER)..'.txt','w')
    if f then
        f:write(tostring(MARKER_VALUE)..' '..tostring(os.time())..'\n')
        f:close()
        M.status='manager option recorded: '..tostring(MARKER)..'='..tostring(MARKER_VALUE)
        log(M.status..' (dormant; the cooldown block applies it)')
    else
        M.status='manager option could not be recorded: '..tostring(MARKER)
        log(M.status)
    end
    return M
end

local SESSION_START=os.time()

local function apply_marker(name,value)
    if not value or value=='' then return end
    if name=='opt_red' then
        if value=='off' then cfg.red=false
        elseif value=='orbital' then cfg.red=true cfg.orbital=true cfg.eagle=false
        elseif value=='eagle' then cfg.red=true cfg.orbital=false cfg.eagle=true
        elseif value=='both' then cfg.red=true cfg.orbital=true cfg.eagle=true end
    elseif name=='opt_blue' then
        if value=='off' then cfg.blue=false
        else
            cfg.blue=true
            if value=='vehicles' or value=='mechs' or value=='both' or value=='all' then
                cfg.blue_scope=value
            end
        end
    elseif name=='opt_green' then
        cfg.green=(value=='on' or value=='yes' or value=='true')
    elseif name=='opt_uses' then
        if value=='unlimited' then
            cfg.uses_unlimited=true cfg.uses_add=0
        else
            cfg.uses_unlimited=false
            cfg.uses_add=math.floor(tonumber(value) or 0)
        end
    end
    cfg.markers_read=(cfg.markers_read or '')..name..'='..value..' '
end

-- A marker is only trusted if the provider wrote it in THIS session. Unticking
-- a block means its addon is no longer deployed, so its marker stops being
-- refreshed and is ignored - that is what makes the outer checkbox the on/off
-- switch without an "off" entry inside the submenu.
local MARKER_TRUST_S=180

-- ---------------------------------------------------------------------------
-- Design A: the manager UI state is the source of truth. Only the core addon is
-- deployed (from the cooldown block), the other blocks hold no files at all, so
-- the core reads Arsenal's own database: each option group carries "enabled" and
-- each suboption carries "enabled". Unticked = false = that block is off.
-- ---------------------------------------------------------------------------
local function manager_db_path()
    if cfg.manager_db and cfg.manager_db~='' then return cfg.manager_db end
    local la=os.getenv('LOCALAPPDATA')
    if not la then return nil end
    return la:gsub('\\','/')..'/hd2arsenal/hd2a_data.json'
end

local GROUPS={ {'red','红战备'}, {'blue','蓝战备'}, {'green','绿战备'},
               {'cooldown','冷却时间'}, {'uses','次数增加'} }

local function group_segment(text,label,all_labels)
    local i=text:find(label,1,true)
    if not i then return nil end
    local stop=math.min(#text,i+6000)
    for _,l in ipairs(all_labels) do
        if l~=label then
            local j=text:find(l,i+#label,true)
            if j and j<stop then stop=j end
        end
    end
    return text:sub(i,stop)
end

local function flag_after(seg,pos)
    local i=seg:find('"enabled":',pos,true)
    if not i then return nil end
    return seg:sub(i+10,i+22):find('true',1,true)~=nil, i
end

local function chosen_sub(seg)
    local s0=seg:find('"suboptions"',1,true)
    if not s0 then return nil end
    local region=seg:sub(s0)
    local pos=1
    while true do
        local ni=region:find('"name":',pos,true)
        if not ni then return nil end
        local name=region:sub(ni):match('^"name":%s*"([^"]*)"')
        local on=flag_after(region,ni)
        if name and on then return name:lower() end
        pos=ni+6
    end
end

local function apply_manager_ticks()
    local path=manager_db_path()
    if not path then return false,'no db path' end
    local f=io.open(path,'rb')
    if not f then return false,'db missing' end
    local size=f:seek('end')
    f:seek('set',0)
    if not size or size>16777216 then f:close() return false,'db too large' end
    local text=f:read('*a')
    f:close()
    if not text then return false,'db unreadable' end
    local labels={}
    for _,g in ipairs(GROUPS) do labels[#labels+1]=g[2] end
    local ticks={}
    for _,g in ipairs(GROUPS) do
        local seg=group_segment(text,g[2],labels)
        if seg then
            local on=flag_after(seg,1)
            ticks[g[1]]={on=on, pick=chosen_sub(seg)}
        end
    end
    if not (ticks.cooldown and ticks.cooldown.pick) then return false,'groups not found' end
    cfg.red=false cfg.orbital=false cfg.eagle=false
    cfg.blue=false cfg.green=false
    cfg.uses_add=0 cfg.uses_unlimited=false
    local picks={}
    if ticks.red and ticks.red.on and ticks.red.pick then
        local n=ticks.red.pick
        if n:find('关闭',1,true) or n:find('off',1,true) then
            cfg.red=false cfg.orbital=false cfg.eagle=false
        elseif n:find('orbital + eagle',1,true) then
            cfg.red=true cfg.orbital=true cfg.eagle=true picks[#picks+1]='red=both'
        elseif n:find('orbital only',1,true) then
            cfg.red=true cfg.orbital=true picks[#picks+1]='red=orbital'
        elseif n:find('eagle only',1,true) then
            cfg.red=true cfg.eagle=true picks[#picks+1]='red=eagle'
        end
    end
    if ticks.blue and ticks.blue.on and ticks.blue.pick then
        local n=ticks.blue.pick
        if n:find('关闭',1,true) or n:find('off',1,true) then
            cfg.blue=false
        else
        cfg.blue=true
        if n:find('all',1,true) then cfg.blue_scope='all' picks[#picks+1]='blue=all'
        elseif n:find('vehicles + mechs',1,true) then cfg.blue_scope='both' picks[#picks+1]='blue=both'
        elseif n:find('vehicles only',1,true) then cfg.blue_scope='vehicles' picks[#picks+1]='blue=vehicles'
        elseif n:find('mechs only',1,true) then cfg.blue_scope='mechs' picks[#picks+1]='blue=mechs' end
        end
    end
    if ticks.green and ticks.green.on then
        local n=ticks.green.pick or ''
        if not (n:find('关闭',1,true) or n:find('off',1,true)) then
            cfg.green=true picks[#picks+1]='green=on'
        end
    end
    if ticks.uses and ticks.uses.on and ticks.uses.pick then
        local n=ticks.uses.pick
        if n:find('不添加',1,true) or n:find('none',1,true) or n:find('关闭',1,true) then
            cfg.uses_add=0 cfg.uses_unlimited=false
        elseif n:find('unlimited',1,true) then
            cfg.uses_unlimited=true picks[#picks+1]='uses=unlimited'
        else
            local k=n:match('%+(%d)')
            if k then cfg.uses_add=tonumber(k) picks[#picks+1]='uses=+'..k end
        end
    end
    local cd=ticks.cooldown.pick:match('(%d+)%%')
    if cd then cfg.percent=tonumber(cd) picks[#picks+1]='cooldown='..cd..'%' end
    return true,table.concat(picks,' ')
end
local MAX_LAYER_BYTES=1048576

-- Method 1: which blocks did Arsenal actually deploy? Unticked means not
-- deployed, so the signature is simply absent - no stale state to reason about.
local function game_dir()
    if cfg.scan_dir and cfg.scan_dir~='' then return cfg.scan_dir end
    local ok,dir=pcall(function()
        local buf=ffi.new('char[512]')
        local n=ffi.C.GetModuleFileNameA(nil,buf,512)
        if not n or n<=0 then return nil end
        local path=ffi.string(buf,n)
        return path:match('^(.*)[\\/][^\\/]*$')
    end)
    if ok and dir and dir~='' then return dir end
    return nil
end

local function read_layer(path)
    local f=io.open(path,'rb')
    if not f then return nil end
    local size=f:seek('end')
    if not size or size>MAX_LAYER_BYTES then f:close() return nil end
    f:seek('set',0)
    local data=f:read('*a')
    f:close()
    if not data then return nil end
    local name=data:match("local MARKER='([^']+)'")
    local value=data:match("local MARKER_VALUE='([^']+)'")
    if not value then
        local n2,v2=data:match('VCBLOCK%s+([%w_]+)%s*=%s*([%w_]+)')
        name,value=n2,v2
    end
    if name and value and name:sub(1,4)=='opt_' then return name,value end
    return nil
end

local function scan_deployed(dir)
    if not dir then return {} end
    local found={}
    local dd=dir..'\\data'
    local names={}
    local ok,pipe=pcall(function() return nil end, 'dir /b /o-d "'..dd..'\\9ba*.patch_*" 2>nul')
    if ok and pipe then
        for line in pipe:lines() do names[#names+1]=line end
        pipe:close()
    end
    -- also try the flat .patch_N pattern the game uses for its own data dir
    if #names==0 then
        local ok2,pipe2=pcall(function() return nil end, 'dir /b /o-d "'..dir..'\\data\\*.patch_*" 2>nul')
        if ok2 and pipe2 then
            for line in pipe2:lines() do
                names[#names+1]=line
                if #names>=400 then break end
            end
            pipe2:close()
        end
    end
    local read=0
    for _,fn in ipairs(names) do
        if read<400 then
            local name,value=read_layer(dd..'\\'..fn)
            if name then found[name]=value read=read+1 end
        end
    end
    return found,read
end

local function read_markers(now)
    if cfg.markers_done then return true end
    local fresh,fresh_names={},{}
    for _,name in ipairs({'opt_red','opt_blue','opt_green','opt_uses'}) do
        local f=io.open(OPT_DIR..name..'.txt','r')
        if f then
            local v=f:read('*l')
            f:close()
            if v then
                v=v:gsub('%s+$','')
                local value,ts=v:match('^(%S+)%s+(%d+)$')
                if not value then value=v end
                local age=ts and (SESSION_START-tonumber(ts)) or nil
                if value and value~='' and age and age<=MARKER_TRUST_S and age>=-MARKER_TRUST_S then
                    fresh[#fresh+1]=name
                    fresh_names[name]=value
                elseif value and value~='' then
                    log(string.format('manager block %s ignored: marker is stale (%s)',
                        name,tostring(age and (age..'s old') or 'no timestamp')))
                end
            end
        end
    end
    local source='markers'
    local dbok,dbnote=pcall(apply_manager_ticks)
    if dbok and dbnote then
        source='manager DB'
        cfg.markers_done=true
        local vals=cfg.explicit_vals or {}
        for k,v in pairs(vals) do cfg[k]=v end
        log(string.format('blocks(from manager DB): %s | explicit: %s | effective: %s',
            tostring(dbnote), next(vals) and 'config.txt overrides applied' or 'none',
            string.format('percent=%s red=%s(orbital=%s,eagle=%s) blue=%s(%s) green=%s uses_add=%s uses_unlimited=%s',
                tostring(cfg.percent),tostring(cfg.red),tostring(cfg.orbital),tostring(cfg.eagle),
                tostring(cfg.blue),tostring(cfg.blue_scope),tostring(cfg.green),
                tostring(cfg.uses_add),tostring(cfg.uses_unlimited))))
        return true
    elseif dbnote and dbnote~='db missing' then
        log('manager DB not used: '..tostring(dbnote))
    end
    if #fresh==0 then
        -- Method 1: read the deployed layers (works even if no second addon ran)
        local dir=game_dir()
        local found,count=scan_deployed(dir)
        local n=0
        for name,value in pairs(found or {}) do
            fresh[#fresh+1]=name
            fresh_names[name]=value
            n=n+1
        end
        if n>0 then
            source='deployed layers'
            log(string.format('deploy scan: %s -> %d block(s) found in %d layer file(s)',
                tostring(dir),n,count or 0))
        end
    end
    if #fresh>0 then
        -- start from "every block off" so an unticked block really is off, then
        -- let the deployed blocks switch things on
        cfg.red=false cfg.orbital=false cfg.eagle=false
        cfg.blue=false cfg.green=false
        cfg.uses_add=0 cfg.uses_unlimited=false
        for _,name in ipairs(fresh) do apply_marker(name,fresh_names[name]) end
        -- and finally the keys the player left uncommented in config.txt
        local vals=cfg.explicit_vals or {}
        for k,v in pairs(vals) do cfg[k]=v end
        cfg.markers_done=true
        log('blocks(from '..source..'): '..tostring(cfg.markers_read or '')..'| explicit: '..
            tostring(next(vals) and 'config.txt overrides applied' or 'none')..
            ' | effective: '..string.format('red=%s(orbital=%s,eagle=%s) blue=%s(%s) green=%s uses_add=%s uses_unlimited=%s',
                tostring(cfg.red),tostring(cfg.orbital),tostring(cfg.eagle),tostring(cfg.blue),
                tostring(cfg.blue_scope),tostring(cfg.green),tostring(cfg.uses_add),
                tostring(cfg.uses_unlimited)))
    elseif now>5 then
        cfg.markers_done=true
        log('manager blocks: none deployed (single-addon mode)')
    end
    return #fresh>0
end

local born=os.clock()
local cd=make_feature('cooldown')
local frames=0
local RE_LOCATE_MAX=5
local SCAN_IDS=255

local function target_count()
    local n=0
    for _ in pairs(cd.targets or {}) do n=n+1 end
    return n
end

local function target_summary(limit)
    local parts,n={},0
    for id,rec in pairs(cd.targets or {}) do
        n=n+1
        if n<=(limit or 6) then
            parts[#parts+1]=string.format('%d=%s[%s] %s->%s%s',id,tostring(rec.name or '?'),
                tostring(rec.kind or '?'),tostring(rec.vanilla or '?'),
                tostring(rec.target or 'kept'),
                rec.uses_target and string.format(' charges %s->%s',tostring(rec.uses_vanilla),
                    tostring(rec.uses_target)) or '')
        end
    end
    return n..' target(s) ['..table.concat(parts,', ')..']'
end

-- v1.2: the sweep can no longer be killed by one hostile slot. Every slot read
-- is contained, the reason for every reject is published, and the counters stay
-- in M so the next runtime snapshot explains what happened.
-- 1.7.0 additions: every name-matched record is reported (even when its
-- cooldown is out of range), a one-shot float map of each record is logged, and
-- every target carries the offsets the writer must hold at the target value
-- (the cooldown field plus any field that mirrors it exactly).
local function float_at(rec,off)
    local bits=u32_at(rec,off+1)
    if not bits then return nil end
    local f=f32_from_bits(bits)
    if f~=f then return nil end
    return f,bits
end

local function field_map(rec)
    local parts={}
    for off=0,REC_READ-4,4 do
        local f=float_at(rec,off)
        if f and f>0.5 and f<200000 then
            parts[#parts+1]=string.format('%X=%.4g',off,f)
            if #parts>=24 then break end
        end
    end
    return table.concat(parts,' ')
end

-- every aligned 4-byte field that currently holds exactly the cooldown value
local function cooldown_offsets(rec,base_off,base_bits)
    local offs={base_off}
    for off=0,REC_READ-4,4 do
        if off~=base_off and u32_at(rec,off+1)==base_bits then offs[#offs+1]=off end
    end
    return offs
end

-- 1.7.1: the v2 mod that demonstrably worked wrote at load and validated the
-- two tanks by id + hash before touching anything. The same anchors are used
-- here as a "the table is fully built" witness; a failure is reported and the
-- name-based targets are still patched, so a game patch that changes a hash
-- cannot silently disable the feature.
local ANCHORS={ {id=1,hash=0x7756F32C,label='Bastion'},
                {id=50,hash=0x1B7853AC,label='Storm'} }
local function check_anchors()
    local ok,notes=0,{}
    for _,a in ipairs(ANCHORS) do
        local r=rec_info(a.id)
        if r and r.id==a.id and r.hash==a.hash then
            ok=ok+1
        else
            notes[#notes+1]=string.format('%s(id=%d) hash=%s want=0x%08X',
                a.label,a.id,r and string.format('0x%08X',r.hash) or 'none',a.hash)
        end
    end
    return ok,table.concat(notes,'; ')
end

local function cooldown_targets()
    local t={}
    local slots,records,matched,rejects,bad=0,0,0,0,0
    local cand={}
    for id=0,SCAN_IDS do
        slots=slots+1
        local ok,r=pcall(rec_info,id)
        if not ok then
            bad=bad+1
            note_error('read slot '..id,r)
        elseif r then
            records=records+1
            local kind=classify(r.name)
            if r.id==id and in_scope(kind) then
                local cd_s=f32_from_bits(r.cooldown_bits)
                local uses=u32_at(r.raw_uses and r.raw_uses or '',1)
                if #cand<16 then
                    cand[#cand+1]=string.format('%d=%s[%s]%s/%s',id,tostring(r.name),
                        tostring(kind),tostring(cd_s),'?')
                end
                if cd_s==cd_s and cd_s>=1 and cd_s<=7200 then
                    local raw=read_at(r.ptr,REC_READ)
                    cd.vanilla=cd.vanilla or {}
                    local vanilla=cd.vanilla[id]
                    if not vanilla and raw then
                        -- remember the untouched value (and the fields that
                        -- mirror it) once, so a later re-scan cannot mistake
                        -- our own target for the vanilla number
                        vanilla={bits=r.cooldown_bits,value=cd_s,
                                 offs=cooldown_offsets(raw,OFF_COOLDOWN,r.cooldown_bits)}
                        cd.vanilla[id]=vanilla
                        r.offs=vanilla.offs
                        local names={}
                        for _,off in ipairs(r.offs) do
                            names[#names+1]=string.format('0x%X',off)
                        end
                        r.offsets_str=table.concat(names,',')
                        if not (cd.mapped and cd.mapped[id]) then
                            cd.mapped=cd.mapped or {}
                            cd.mapped[id]=true
                            log(string.format('record id=%d ptr=%s name=%s offsets=%s fields: %s',
                                id,hex(r.ptr),tostring(r.name),r.offsets_str,field_map(raw)))
                        end
                    elseif vanilla then
                        r.offs=vanilla.offs
                    else
                        r.offs={OFF_COOLDOWN}
                        r.offsets_str='0x68'
                    end
                    r.vanilla=(vanilla and vanilla.value) or cd_s
                    -- 1.9.2: small +0x68 values are not cooldowns. Eagle entries
                    -- carry their strike/drop delay there (15s), the tank entries
                    -- the 6s reload - rescaling those changes how fast the strike
                    -- arrives, which is not what this addon promises. The real
                    -- Eagle cycle is EAGLE. REARM (150s), which is above the bar.
                    local mincd=tonumber(cfg.min_cooldown) or 60
                    if r.vanilla<mincd then
                        r.target_bits,r.target=nil,nil
                        cd.low_logged=cd.low_logged or {}
                        if not cd.low_logged[id] then
                            cd.low_logged[id]=true
                            log(string.format(
                                'id=%d %s cooldown %s < min_cooldown %s - left alone (timing field)',
                                id,tostring(r.name),tostring(r.vanilla),tostring(mincd)))
                        end
                    else
                        r.target_bits,r.target=target_bits_for(r.vanilla)
                    end
                    r.kind=kind
                    -- charges: +0x50 int32, -1 = unlimited
                    local cur_uses=raw and i32_at(raw,OFF_USES+1) or nil
                    if cd.vanilla_uses==nil then cd.vanilla_uses={} end
                    if cd.vanilla_uses[id]==nil and cur_uses~=nil then
                        cd.vanilla_uses[id]=cur_uses
                    end
                    r.uses_vanilla=cd.vanilla_uses[id]
                    r.uses_target=uses_target(r.uses_vanilla)
                    t[id]=r matched=matched+1
                else
                    rejects=rejects+1
                end
            end
        end
    end
    if not cd.cand_logged and #cand>0 then
        cd.cand_logged=true
        log('vehicle candidates: '..table.concat(cand,', '))
    end
    M.slots,M.records,M.matched,M.rejects,M.bad_slots=slots,records,matched,rejects,bad
    return t
end

-- ============ 1.7.0 probe: who else holds this cooldown? ==================
-- Read-only and bounded: a window is read in 1MB chunks (read_at fails safely
-- on unmapped pages), hits are kept only when the neighbourhood points at a
-- string carrying the record's own name fragment. That distinguishes the
-- definition record the addon already patches from a copy used elsewhere
-- (per-player / per-mission state), which is the prime suspect now that the
-- patched definition has no in-game effect.
local function looks_like_record(addr,frag)
    if frag=='' then return false end
    for delta=-0x80,0x80,8 do
        local q=u64_at(read_at(addr+delta,8) or '',1)
        if sane_ptr(q) then
            local s=read_cstr(q,48)
            if s and s:find(frag,1,true) then return true end
        end
    end
    return false
end

local function scan_window(centre,span,needle,frag,out,cap)
    local start=centre-math.floor(span/2)
    if start<MIN_PTR then start=MIN_PTR end
    local step,off=0x100000,0
    while off<span and #out<cap do
        local data=read_at(start+off,step)
        if data then
            local from=1
            while true do
                local p=data:find(needle,from,true)
                if not p then break end
                local addr=start+off+p-1
                if addr~=centre and looks_like_record(addr,frag) then
                    out[#out+1]=addr
                    if #out>=cap then break end
                end
                from=p+1
            end
        end
        off=off+step
    end
end

local COPY_SPAN=0x1000000        -- +/- 8MB around the table and around the record
local function probe_copies()
    if cd.probed then return end
    cd.probed=true
    if not cfg.probe then return end
    for id,rec in pairs(cd.targets or {}) do
        local vanilla=(cd.vanilla and cd.vanilla[id] and cd.vanilla[id].bits) or rec.cooldown_bits
        local needle=u32_bytes(vanilla)
        local frag=string.sub(tostring(rec.name or ''),1,12)
        local out={}
        scan_window(table_base,COPY_SPAN,needle,frag,out,5)
        if #out<5 then scan_window(rec.ptr,COPY_SPAN,needle,frag,out,5) end
        local hits={}
        for _,addr in ipairs(out) do
            hits[#hits+1]=hex(addr)..'(d='..hex(math.abs(addr-rec.ptr))..')'
        end
        log(string.format('copy probe id=%d name=%s original=%s hits=%d %s',
            id,tostring(rec.name),tostring(f32_from_bits(vanilla)),#out,
            table.concat(hits,' ')))
    end
end

local function try_relocate(now)
    if cd.state~='observe' then return end
    if (cd.relocates or 0)>=RE_LOCATE_MAX then return end
    if cd.next_relocate and now<cd.next_relocate then return end
    cd.relocates=(cd.relocates or 0)+1
    cd.next_relocate=now+120
    M.relocates=cd.relocates
    local base,err=locate_table()
    if base then
        table_base=base
        cd.targets=nil cd.stable_since=nil cd.last_sample=0
        log(string.format('re-resolved table base (attempt %d): %s',cd.relocates,hex(base)))
    else
        log(string.format('re-resolve failed (attempt %d): %s',cd.relocates,tostring(err)))
    end
end

-- 1.7.0: patch every offset the target carries (cooldown field + exact mirrors)
-- and remember each original value for an exact rollback.
local function cooldown_write(cfg)
    local patched={}
    for id,rec in pairs(cd.targets) do
        local desired=rec.target_bits or desired_bits()
        local cur=rec_info(id)
        if not cur or cur.ptr~=rec.ptr then return false,'record moved during write @'..id end
        local raw=read_at(cur.ptr,REC_READ)
        if not raw then return false,'record unreadable during write @'..id end
        local offs=(rec.target_bits and rec.offs) or {}
        for _,off in ipairs(offs) do
            local bits=u32_at(raw,off+1)
            if bits~=desired then
                if not write4(cur.ptr+off,desired) then
                    return false,string.format('write/verify failed @%d+0x%X',id,off)
                end
                cd.written[#cd.written+1]={ptr=cur.ptr,off=off,bits=bits,id=id}
                patched[#patched+1]=string.format('%d+0x%X',id,off)
            end
        end
        -- charges (+0x50): only for records that really are limited
        if rec.uses_target then
            local cur_uses=i32_at(raw,OFF_USES+1)
            if cur_uses~=rec.uses_target then
                if not write4(cur.ptr+OFF_USES,rec.uses_target) then
                    return false,string.format('charges write failed @%d+0x%X',id,OFF_USES)
                end
                cd.written[#cd.written+1]={ptr=cur.ptr,off=OFF_USES,bits=cur_uses,id=id}
                patched[#patched+1]=string.format('%d+0x%X(charges %s->%s)',id,OFF_USES,
                    tostring(rec.uses_vanilla),tostring(rec.uses_target))
            end
        end
    end
    if #patched>0 then
        log('patched offsets: '..table.concat(patched,', '))
    end
    return true
end

local function tick_cooldown()
    if not cfg.cooldown then
        if cd.state~='disabled' then
            cd.state='disabled'; cd.disabled_reason='config off'
            log('cooldown disabled: config says cooldown=no')
        end
        return
    end
    local now=os.clock()
    local up=now-born
    -- the manager blocks (red/blue/green/charges) are recorded by their own tiny
    -- addons; pick them up before any scope decision is made
    pcall(read_markers,up)
    if up<(cfg.uptime_s or 0) then
        local ph='uptime '..math.floor(up)..'s'
        if M.phase~=ph then M.phase=ph end
        if frames%1800==0 then log('waiting uptime: '..ph) end
        return
    end
    if not cd.gate_logged then
        cd.gate_logged=true
        log(string.format('uptime gate passed (%ds) - observing stability; cooldown_s=%s stable_s=%s',
            math.floor(up),tostring(cfg.cooldown_s),tostring(cfg.stable_s)))
    end
    if now-(cd.last_beat or 0)>=60 then
        cd.last_beat=now
        log(string.format('heartbeat: state=%s phase=%s targets=%d scans=%d errors=%d uptime=%ds frames=%d',
            tostring(cd.state),tostring(M.phase),target_count(),cd.scans or 0,M.errors or 0,math.floor(up),frames))
    end
    if cd.state=='observe' then
        if not cd.targets or not next(cd.targets) then
            -- an EMPTY target set must never be cached: vehicle records and the
            -- table itself can be rebuilt, so keep re-enumerating on a cadence.
            if not cd.next_scan or now>=cd.next_scan then
                cd.next_scan=now+10
                cd.scans=(cd.scans or 0)+1
                local t=cooldown_targets()
                cd.targets=next(t) and t or nil
                if not cd.targets then
                    M.phase='no vehicle records yet'
                    if not cd.scan_note or now-cd.scan_note>=60 then
                        cd.scan_note=now
                        log(string.format('no vehicle records yet: slots=%s records=%s matched=%s rejects=%s contained_faults=%s - re-scanning every 10s',
                            tostring(M.slots),tostring(M.records),tostring(M.matched),tostring(M.rejects),tostring(M.bad_slots)))
                    end
                    -- Nothing readable at all is the one case where the table
                    -- base itself is suspect: re-resolve, bounded and slow.
                    if (M.records or 0)==0 then try_relocate(now) end
                    return
                end
                log('vehicle records appeared: '..target_summary())
                if not cd.anchor_logged then
                    cd.anchor_logged=true
                    local n,note=check_anchors()
                    log(string.format('identity anchors: %d/%d ok %s',n,#ANCHORS,note~='' and ('('..note..')') or ''))
                end
                cd.stable_since=nil cd.stable_enough=false cd.last_sample=0
            else
                return
            end
        end
        if cd:snapshot_ok(now,cfg) then
            cd.state='writing'
            local ok,err=cooldown_write(cfg)
            if ok then
                cd.state='watch'; cd.last_watch=now
                log('cooldown applied to '..target_summary())
            pcall(M.refresh_mode)
                pcall(probe_copies)
            else
                -- restore everything we touched this pass, then stand down
                for _,w in ipairs(cd.written) do pcall(write4,w.ptr+w.off,w.bits) end
                cd.written={}
                cd.state='disabled'; cd.disabled_reason=err
                log('cooldown ABORTED + rolled back: '..tostring(err))
            end
            return
        end
        local ph='observing stability ('..target_count()..' target(s))'
        if M.phase~=ph then M.phase=ph end
    elseif cd.state=='watch' then
        if now-(cd.last_watch or 0)<5 then return end
        cd.last_watch=now
        local moved=false
        for id,rec in pairs(cd.targets) do
            local desired=rec.target_bits or desired_bits()
            local cur=rec_info(id)
            if not cur or cur.ptr~=rec.ptr then
                moved=true
            else
                local raw=read_at(cur.ptr,REC_READ)
                if raw then
                    local watches={}
                    for _,off in ipairs((rec.target_bits and rec.offs) or {}) do watches[#watches+1]=off end
                    if rec.uses_target then watches[#watches+1]=OFF_USES end
                    for _,off in ipairs(watches) do
                        local want=(off==OFF_USES) and rec.uses_target or desired
                        local bits=u32_at(raw,off+1)
                        if off==OFF_USES then bits=i32_at(raw,off+1) end
                        if bits~=want then
                            rec.needs_rewrite=true
                            -- the engine wrote this field itself - it is live
                            -- state, not a dead copy. Report it once.
                            local key=id..':'..off
                            if not (cd.changed and cd.changed[key]) then
                                cd.changed=cd.changed or {}
                                cd.changed[key]=true
                                log(string.format('engine changed patched field id=%d off=0x%X now=%s',
                                    id,off,tostring(f32_from_bits(bits or 0))))
                            end
                        end
                    end
                end
            end
        end
        if moved then
            -- engine rebuilt the table: never write mid-rebuild, re-observe
            cd.state='observe'; cd.targets=nil; cd.stable_since=nil; cd.written={}
            log('table rebuilt - back to observe')
        else
            local ph='watch ('..target_count()..' target(s))'
            if M.phase~=ph then M.phase=ph end
            for id,rec in pairs(cd.targets) do
                if rec.needs_rewrite then
                    rec.needs_rewrite=nil
                    -- only rewrite after the whole set has been stable again
                    if cd:snapshot_ok(now,cfg) then
                        local want=rec.target_bits or desired_bits()
                        local cur=rec_info(id)
                        local raw=cur and read_at(cur.ptr,REC_READ)
                        local ok=true
                        if raw then
                            local rewrites={}
                            for _,off in ipairs((rec.target_bits and rec.offs) or {}) do rewrites[#rewrites+1]=off end
                            if rec.uses_target then rewrites[#rewrites+1]=OFF_USES end
                            for _,off in ipairs(rewrites) do
                                local target=(off==OFF_USES) and rec.uses_target or want
                                local bits=(off==OFF_USES) and i32_at(raw,off+1) or u32_at(raw,off+1)
                                if bits~=target and not write4(cur.ptr+off,target) then ok=false break end
                            end
                        else
                            ok=false
                        end
                        if ok then
                            log('cooldown re-applied to record '..id)
                        else
                            cd.state='disabled'; cd.disabled_reason='rewrite failed'
                            log('cooldown disabled: rewrite failed')
                            break
                        end
                    end
                end
            end
        end
    end
end

local previous=rawget(_G,'update')
local unpack=rawget(_G,'unpack') or table.unpack
if type(previous)~='function' then
    M.status='no update chain'; log('global update missing - dormant')
    return M
end
local function pack(...) return {n=select('#',...),...} end
local pr_t,pr_n,pr_last=0,0,0
local function frame()
    local t0=os.clock()
    frames=frames+1
    local ok,err=pcall(tick_cooldown)
    if not ok then note_error('tick',err) end
    -- scalar mirrors for third-party runtime snapshots (string/number fields only)
    M.state=cd.state
    M.targets=target_count()
    local d=os.clock()-t0
    pr_t=pr_t+d; pr_n=pr_n+1
    if os.clock()-pr_last>=1 then
        pr_last=os.clock()
        local p=rawget(_G,'HD2Perf')
        if not p then p={} rawset(_G,'HD2Perf',p) end
        p['vehicle_cooldown']={t=pr_t,n=pr_n}
        pr_t,pr_n=0,0
    end
end
update=function(...)
    local r=pack(previous(...))
    frame()
    if unpack then return unpack(r,1,r.n) end
end
M.cd=cd
-- scalar mirrors so third-party runtime snapshots (which publish string/number
-- fields only) can show the effective configuration without a debug session
M.uptime_s,M.stable_s,M.cooldown_s=cfg.uptime_s or 0,cfg.stable_s or 1,cfg.cooldown_s
M.cooldown_enabled=cfg.cooldown and 1 or 0
M.scan_ids=SCAN_IDS
local function mode_string()
    return string.format('percent=%s min_cooldown=%s uses_add=%s uses_unlimited=%s red=%s(orbital=%s,eagle=%s) '..
        'blue=%s(%s) green=%s missions=%s blocks=%s',
        tostring(cfg.percent),tostring(cfg.min_cooldown),tostring(cfg.uses_add),tostring(cfg.uses_unlimited),
        tostring(cfg.red),tostring(cfg.orbital),tostring(cfg.eagle),
        tostring(cfg.blue),tostring(cfg.blue_scope),tostring(cfg.green),tostring(cfg.missions),
        tostring(cfg.markers_read or '-'))
end
M.mode=mode_string()
M.refresh_mode=function() M.mode=mode_string() return M.mode end
log(string.format('v%s installed: all-stratagem cooldown, uptime gate %ss, stable gate %ss%s',
    M.version,tostring(cfg.uptime_s or 0),tostring(cfg.stable_s or 1),
    BAKED and (' [profile: '..tostring(BAKED.profile or 'manager option')..']') or ' [profile: none]'))
return M

-- [guide:begin]
-- 战备冷却 / Stratagem Cooldown 2.2.0 - quick guide / 快速指南
--
-- What it does / 作用
--   Shortens stratagem cooldowns by a percentage of each stratagem's OWN value
--   (default 50%) and can change how many charges a limited stratagem has.
--   按每条战备自己的原值乘以百分比缩短冷却（默认 50%），并可修改有限次数战备的次数。
--
-- Layering / 两层设置
--   1) In the mod manager, pick one entry from the "Profile / 方案" group.
--      It ships as a complete build (all profiles share the same addon GUID, so
--      exactly one can ever be deployed).
--      在管理器里从“方案 / Profile”里选一个，方案是完整构建，共用同一个 GUID，
--      永远只会生效一个。
--   2) config.txt still wins for any key you leave uncommented - use it to
--      fine-tune whatever the chosen profile does not set.
--      config.txt 里“未注释”的键优先级最高，可用来微调。
--
-- Config / 配置（键都被注释掉时使用方案里的值）
--   %LOCALAPPDATA%\CowboyBingus\Helldivers2\VehicleCooldown\config.txt
--     percent=50             cooldown: 100 = unchanged, 80 = 20% shorter,
--                            50 = half (exactly these three)
--     min_cooldown=60        only rescale +0x68 values of at least this many
--                            seconds. Smaller values are strike/drop timings,
--                            not cooldowns (the Eagle entries' 15s, the tank 6s
--                            reload), and are left alone. Set 1 to rescale all.
--     uses_add=0             charges: 0 = unchanged, 1 / 2 / 3 = that many more
--                            charges on every limited stratagem
--     uses_unlimited=no      yes = remove the charge limit entirely (finite -> -1)
--     red=yes                red stratagems (offensive)
--     orbital=yes              - ORBITAL. series
--     eagle=yes                - EAGLE. series incl. EAGLE. REARM
--     blue=yes               blue stratagems (support equipment)
--     blue_scope=all           - vehicles | mechs | both | all
--     green=yes              green stratagems (sentries, emplacements)
--     missions=no            mission stratagems (reinforce/extraction/...) - off
--     stable_s=1             pointer-stability window before writing
--     uptime_s=0             write as soon as the records are valid
--     probe=no               opt-in diagnostic memory search
--
-- Categories / 分类
--   red   : ORBITAL. and EAGLE. (EAGLE. REARM is the real Eagle cycle: Eagle
--           stratagems spend charges and one rearm restores them all, so its
--           cooldown is what paces the family)
--   blue  : TEAM WEAPONS. BACKPACK. CONSUMABLES., plus vehicles/mechs according
--           to blue_scope (VEHICLES. tanks and FRV = vehicles, VEHICLES.
--           COMBAT WALKER = mechs). blue_scope is mutually exclusive:
--             就载具=vehicles  就机甲=mechs  就载具和机甲=both  全部=all
--   green : SENTRYS. SENTRIES. EMPLACEMENTS.
--   Charges: Orbital Laser 3, mechs 3, Eagle 1..4; -1 means unlimited and is
--   never turned into a limit.
--   次数：激光轨道 3、机甲 3、飞鹰 1..4；-1 表示无限，不会被改成有限。
--
-- Log / 日志
--   %LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\VehicleCooldown.log
--   Healthy session: located -> installed -> mode=... -> records appeared ->
--   patched offsets -> cooldown applied -> heartbeat every 60s.
--   健康会话：定位 -> 安装 -> 模式 -> 发现记录 -> 写入偏移 -> 应用成功 -> 心跳。
-- [guide:end]
