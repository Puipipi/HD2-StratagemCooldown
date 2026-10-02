-- HD2-Addon: mods/codex/vehicle_cooldown
-- HD2 Vehicle Cooldown 1.6.0 (internal name v1.2) - safe rewrite of the
-- Tank Cooldown v2 family for ALL stratagem vehicles.
--
-- What it does
--   * cooldown: shortens the redeploy cooldown of EVERY stratagem vehicle
--     (tanks, exos, FRV - identified by name at runtime), not just two tanks.
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
--   cooldown_s=390         target cooldown in seconds (default 390 = 50%)
--   stable_s=6             pointer stability window before writing
--   uptime_s=60            minimum process uptime before the first write
--   (clutch/clutch_s are accepted for compatibility with the 1.5.x config
--    file; this build does not implement the clutch feature and says so.)
--
-- Diagnostics (readable from the game's SmoothBoot runtime snapshot too):
--   M.status / M.phase / M.version / M.errors / M.last_error / M.slots /
--   M.records / M.matched / M.rejects / M.bad_slots / M.scans / M.relocates
local KEY='HD2VehicleCooldown'
if rawget(_G,KEY) then return rawget(_G,KEY) end
local M={version='1.6.0',status='starting',errors=0}
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
    local d={cooldown=true,cooldown_s=390,stable_s=6,uptime_s=60}
    local ok,text=pcall(function()
        local f=io.open(CFG,'r') if not f then return nil end
        local t=f:read('*a') f:close() return t
    end)
    if not ok or not text then
        pcall(function()
            os.execute('mkdir "'..HOME:gsub('/','\\')..'VehicleCooldown" 2>nul')
            local w=io.open(CFG,'w')
            if w then
                w:write('cooldown=yes\ncooldown_s=390\nstable_s=6\nuptime_s=60\n')
                w:close()
            end
        end)
        return d
    end
    for line in text:gmatch('[^\r\n]+') do
        local v=line:match('^%s*cooldown%s*=%s*(%a+)%s*$')
        if v then d.cooldown=(v=='yes' or v=='true' or v=='on') end
        for _,k in ipairs({'cooldown_s','stable_s','uptime_s'}) do
            v=line:match('^%s*'..k..'%s*=%s*(%d+%.?%d*)%s*$')
            if v then d[k]=tonumber(v) end
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
local OFF_ID,OFF_STR1,OFF_STR2,OFF_STR3=0x00,0x10,0x18,0x20
local OFF_COOLDOWN,REC_READ=0x68,0xB0
local VEHICLE_WORDS={'BASTION','MAELSTROM','TD-','EXO-','EMANCIPATOR','PATRIOT','OBSIDIAN','STEWARD','FRV'}
local function is_vehicle_name(name)
    if not name then return false end
    for _,w in ipairs(VEHICLE_WORDS) do
        if name:find(w,1,true) then return true end
    end
    return false
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
        is_vehicle_name=is_vehicle_name, u32_bytes=u32_bytes, sane_ptr=sane_ptr,
        f32_bits=f32_bits, f32_from_bits=f32_from_bits, conf=conf,
    }
end
local cfg=conf()
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
-- clamp the configured target: a typo like cooldown_s=0 would otherwise mean
-- "vehicles are always available", which is not what this addon promises
do
    local want=tonumber(cfg.cooldown_s) or 390
    if want<30 then want=30 elseif want>7200 then want=7200 end
    if want~=cfg.cooldown_s then
        log(string.format('cooldown_s=%s out of range - using %s',tostring(cfg.cooldown_s),tostring(want)))
    end
    cfg.cooldown_s=want
end
local function desired_bits() return f32_bits(cfg.cooldown_s) end
local born=os.clock()
local cd=make_feature('cooldown')
local frames=0
local RE_LOCATE_MAX=5
local SCAN_IDS=145

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
            parts[#parts+1]=id..'='..tostring(rec.name or '?')..'/'..tostring(f32_from_bits(rec.cooldown_bits))
        end
    end
    return n..' target(s) ['..table.concat(parts,', ')..']'
end

-- v1.2: the sweep can no longer be killed by one hostile slot. Every slot read
-- is contained, the reason for every reject is published, and the counters stay
-- in M so the next runtime snapshot explains what happened.
local function cooldown_targets()
    local t={}
    local slots,records,matched,rejects,bad=0,0,0,0,0
    for id=0,SCAN_IDS do
        slots=slots+1
        local ok,r=pcall(rec_info,id)
        if not ok then
            bad=bad+1
            note_error('read slot '..id,r)
        elseif r then
            records=records+1
            if r.id==id and is_vehicle_name(r.name) then
                local cd_s=f32_from_bits(r.cooldown_bits)
                if cd_s==cd_s and cd_s>=120 and cd_s<=7200 then
                    t[id]=r matched=matched+1
                else
                    rejects=rejects+1
                end
            end
        end
    end
    M.slots,M.records,M.matched,M.rejects,M.bad_slots=slots,records,matched,rejects,bad
    return t
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

local function cooldown_write(cfg)
    local desired=desired_bits()
    for id,rec in pairs(cd.targets) do
        local cur=rec_info(id)
        if not cur or cur.ptr~=rec.ptr then return false,'record moved during write' end
        if cur.cooldown_bits~=desired then
            if not write4(cur.ptr+OFF_COOLDOWN,desired) then return false,'write/verify failed @'..id end
            cd.written[cur.ptr]=cur.cooldown_bits   -- original bits for rollback
        end
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
    if up<(cfg.uptime_s or 60) then
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
            else
                -- restore everything we touched this pass, then stand down
                for p,orig in pairs(cd.written) do pcall(write4,p+OFF_COOLDOWN,orig) end
                cd.written={}
                cd.state='disabled'; cd.disabled_reason=err
                log('cooldown ABORTED + rolled back: '..tostring(err))
            end
            return
        end
        M.phase='observing stability ('..target_count()..' target(s))'
    elseif cd.state=='watch' then
        if now-(cd.last_watch or 0)<5 then return end
        cd.last_watch=now
        local moved=false
        local desired=desired_bits()
        for id,rec in pairs(cd.targets) do
            local cur=rec_info(id)
            if not cur or cur.ptr~=rec.ptr then moved=true
            elseif cur.cooldown_bits~=desired then rec.needs_rewrite=true end
        end
        if moved then
            -- engine rebuilt the table: never write mid-rebuild, re-observe
            cd.state='observe'; cd.targets=nil; cd.stable_since=nil; cd.written={}
            log('table rebuilt - back to observe')
        else
            M.phase='watch ('..target_count()..' target(s))'
            for id,rec in pairs(cd.targets) do
                if rec.needs_rewrite then
                    rec.needs_rewrite=nil
                    -- only rewrite after the whole set has been stable again
                    if cd:snapshot_ok(now,cfg) then
                        local cur=rec_info(id)
                        if cur and write4(cur.ptr+OFF_COOLDOWN,desired) then
                            cd.written[cur.ptr]=cur.cooldown_bits
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
M.uptime_s,M.stable_s,M.cooldown_s=cfg.uptime_s or 60,cfg.stable_s or 6,cfg.cooldown_s
M.cooldown_enabled=cfg.cooldown and 1 or 0
log(string.format('v%s installed: all-vehicle cooldown, uptime gate %ss, stable gate %ss, cooldown_s=%s',
    M.version,tostring(cfg.uptime_s or 60),tostring(cfg.stable_s or 6),tostring(cfg.cooldown_s)))
return M

-- [guide:begin]
-- HD2 Vehicle Cooldown 1.6.0 - quick guide / 快速指南
--
-- What it does / 作用
--   Shortens the redeploy cooldown of every stratagem vehicle (tanks, exos,
--   FRV). Default target: 390 s instead of the vanilla 780 s.
--   缩短所有载具战略配备（坦克、机甲、FRV）的重新部署冷却，默认 390 秒（原版 780 秒）。
--
-- Requirements / 依赖
--   Bingus Shared Loader v15+ (API 1). Enable both and deploy.
--   需要 Bingus Shared Loader v15+（API 1），两个都要启用并部署。
--   Do not run Tank Cooldown v2 next to this one: both write the same field.
--   不要与 Tank Cooldown v2 同时启用，两者写同一个字段。
--
-- Config / 配置
--   %LOCALAPPDATA%\CowboyBingus\Helldivers2\VehicleCooldown\config.txt
--     cooldown=yes|no      feature switch (default yes)
--     cooldown_s=390       target cooldown in seconds (vanilla 780)
--     stable_s=6           pointer-stability window before any write
--     uptime_s=60          minimum process uptime before the first write
--   The file is created on first run; edit it and restart the game.
--   首次运行自动生成；改完需重启游戏。uptime_s 越大越保守。
--
-- Log / 日志
--   %LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\VehicleCooldown.log
--   A healthy session shows, in order:
--     table located at load -> v1.6.0 installed -> uptime gate passed
--     -> vehicle records appeared: N target(s) -> cooldown applied to N ...
--     -> heartbeat every 60 s (state / targets / errors)
--   正常一次会话依次出现：定位成功、安装、通过开机门槛、发现记录、写入成功，
--   之后每 60 秒一条心跳（状态/目标数/错误数）。
--   "no vehicle records yet" means the table is readable but no vehicle record
--   matched (wrong game build, or the field moved) - the log then prints the
--   counters: slots / records / matched / rejects / contained_faults.
--   出现 no vehicle records yet 表示表可读但没有匹配到载具记录，日志会同时给出计数。
--
-- 1.6.0 fixed three real defects of 1.5.x (see the header of this file):
--   the table base was stored in a shadowing local (every scan died on a nil
--   upvalue), the stability gate's self signature was wrong, and the 146-slot
--   sweep followed unvalidated pointers. Any unexpected error is now logged
--   and counted in M.errors / M.last_error instead of disappearing.
--   1.6.0 修掉 1.5.x 的三个真实缺陷：表基址被同名局部变量遮蔽（每次扫描都因
--   nil 上值中断）、稳定门槛的自参数签名错误、146 槽扫描跟随未校验指针；
--   现在任何异常都会写日志并计入 M.errors / M.last_error，不再静默消失。
--
-- This guide is shipped inside the package as README.txt. It is generated from
-- this comment block by work/standalone/build_vc.py, so it can never drift.
-- 本指南由构建脚本从源码注释生成，与代码不会脱节。
-- [guide:end]
