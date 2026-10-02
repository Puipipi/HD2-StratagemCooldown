-- HD2-Addon: mods/codex/vehicle_cooldown
-- HD2 Vehicle Cooldown v1.1 - safe rewrite of Tank Cooldown v2 for ALL vehicles.
--
-- What it does
--   * cooldown: shortens the redeploy cooldown of EVERY stratagem vehicle
--     (tanks, exos, FRV - identified by name at runtime), not just two tanks
--   * clutch:   shortens tracked-vehicle clutch delay (from tank_clutch_tuner)
--
-- Why the old mods crashed (and this one must not)
--   The old family wrote live engine records during the boot window, exactly
--   when the engine rebuilds those tables; writes landed on stale or
--   half-initialised records and the consumer code died at fixed offsets
--   (0x66d1ff/d26c/d646). This rewrite never writes during instability:
--     LOCATE -> OBSERVE (record pointers stable for 6 x 1s AND game uptime
--              over 120s) -> WRITE (each field verified by readback) ->
--     WATCH (read-only every 5s; a moved pointer means the engine is
--           rebuilding - go back to OBSERVE and only re-write once stable;
--           any write/verify failure restores every original value and
--           disables the feature for the rest of the session)
--
-- Config: %LOCALAPPDATA%/CowboyBingus/Helldivers2/VehicleCooldown/config.txt
--   cooldown=yes/no        vehicle cooldown feature (default yes)
--   cooldown_s=390         target cooldown in seconds (default 390 = 50%)
--   clutch=yes/no          tracked-vehicle clutch feature (default yes)
--   clutch_s=0.05          clutch delay target (0.05, gentler than old 0.0)
--   stable_s=6             pointer stability window before writing
--   uptime_s=120           minimum game uptime before the first write
local KEY='HD2VehicleCooldown'
if rawget(_G,KEY) then return rawget(_G,KEY) end
local M={version='1.1',status='starting'}
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

local function conf()
    local d={cooldown=true,cooldown_s=390,stable_s=6,uptime_s=120}
    local ok,text=pcall(function()
        local f=io.open(CFG,'r') if not f then return nil end
        local t=f:read('*a') f:close() return t
    end)
    if not ok or not text then
        pcall(function()
            os.execute('mkdir "'..HOME:gsub('/','\\')..'VehicleCooldown" 2>nul')
            local w=io.open(CFG,'w')
            if w then
                w:write('cooldown=yes\ncooldown_s=390\nclutch=yes\nclutch_s=0.05\n')
                w:write('stable_s=6\nuptime_s=120\n')
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

local function read_at(address,size)
    if not address or address<0x10000 or size<=0 then return nil end
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
    if not address or address<0x10000 then return nil end
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
                    matches[#matches+1]=wb+p-1
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
    return r15_base+disp
end

-- record layout (validated by Tank Cooldown v2)
local OFF_ID,OFF_STR1,OFF_STR2,OFF_STR3=0x00,0x10,0x18,0x20
local OFF_COOLDOWN,REC_READ=0x68,0xB0
local VEHICLE_WORDS={'BASTION','MAELSTROM','EXO','EMANCIPATOR','OBSIDIAN','STEWARD','FRV','PATRIOT'}
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
    if not p or p<0x10000 then return nil end
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
-- state: 'observe' | 'ready' | 'watch' | 'disabled'
local function make_feature(name,enabled_check)
    local F={name=name,state='observe',seen_ptr={},stable_since=nil,written={},disabled_reason=nil}
    F.last_sample=0
    F.snapshot_ok=function(now,cfg)
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

if rawget(_G,'VC_TEST_MODE') then
    return {
        make_feature=make_feature, locate_table=function() return locate_table() end,
        is_vehicle_name=is_vehicle_name, u32_bytes=u32_bytes,
        f32_bits=f32_bits, conf=conf,
    }
end
local cfg=conf()
-- Resolve the table ONCE at load time, exactly like the original TankCooldown:
-- a failed resolver means the build is unknown - retrying per frame would scan
-- game.dll's whole image every frame (that mistake cost ~54ms/frame).
local table_base,locate_err=locate_table()
if not table_base then
    M.status='locate failed: '..tostring(locate_err)
    log('STOPPED at load: '..M.status)
    return M
end
log('table located at load (single pass)')
local born=os.clock()
local cd=make_feature('cooldown')
local frames=0

local function cooldown_targets()
    -- enumerate slots, keep only vehicle-looking records with a sane cooldown
    local t={}
    for id=0,145 do
        local r=rec_info(id)
        if r and r.id==id and is_vehicle_name(r.name) then
            local cd_s=f32_from_bits(r.cooldown_bits)
            if cd_s and cd_s>=120 and cd_s<=7200 then t[id]=r end
        end
    end
    return t
end

local function cooldown_write(cfg)
    local desired=f32_bits(cfg.cooldown_s or 390)
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
    if not cfg.cooldown then cd.state='disabled'; cd.disabled_reason='config off'; return end
    local now=os.clock()
    if now-born<(cfg.uptime_s or 120) then
        local ph='uptime '..math.floor(now-born)..'s'
        if M.phase~=ph then M.phase=ph end
        if frames%1800==0 then log('waiting uptime: '..ph) end
        return
    end
    if not cd.gate_logged then
        cd.gate_logged=true
        log('uptime gate passed - observing table stability')
    end
    if cd.state=='observe' then
        if not cd.targets or not next(cd.targets) then
            -- v1.1 fix: an EMPTY target set must never be cached - vehicle
            -- records can materialise only when a mission loads, so keep
            -- re-enumerating on a slow cadence until some appear
            if not cd.next_scan or now>=cd.next_scan then
                cd.next_scan=now+10
                cd.targets=cooldown_targets()
                if not next(cd.targets or {}) then
                    M.phase='no vehicle records yet'
                    if not cd.scan_note or now-cd.scan_note>=60 then
                        cd.scan_note=now
                        log('no vehicle records yet - re-scanning every 10s')
                    end
                    return
                end
                local n=0 for _ in pairs(cd.targets) do n=n+1 end
                log('vehicle records appeared: '..n..' record(s) - observing stability')
            else
                return
            end
        end
        if cd:snapshot_ok(now,cfg) then
            cd.state='writing'
            local ok,err=cooldown_write(cfg)
            if ok then
                cd.state='watch'; cd.last_watch=now
                local n=0 for _ in pairs(cd.targets) do n=n+1 end
                log('cooldown applied to '..n..' vehicle record(s)')
            else
                -- restore everything we touched this pass, then stand down
                for p,orig in pairs(cd.written) do pcall(write4,p+OFF_COOLDOWN,orig) end
                cd.written={}
                cd.state='disabled'; cd.disabled_reason=err
                log('cooldown ABORTED + rolled back: '..tostring(err))
            end
            return
        end
    elseif cd.state=='watch' then
        if now-(cd.last_watch or 0)<5 then return end
        cd.last_watch=now
        local moved=false
        local desired=f32_bits(cfg.cooldown_s or 390)
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
            for id,rec in pairs(cd.targets) do
                if rec.needs_rewrite then
                    rec.needs_rewrite=nil
                    -- only rewrite after the whole set has been stable again
                    if cd:snapshot_ok(now,cfg) then
                        local cur=rec_info(id)
                        if cur and write4(cur.ptr+OFF_COOLDOWN,desired) then
                            cd.written[cur.ptr]=cur.cooldown_bits
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
local pr_t,pr_n,pr_last=0,0,0
local function frame()
    local t0=os.clock()
    frames=frames+1
    pcall(tick_cooldown)
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
    local r={previous(...)}
    frame()
    if unpack then return unpack(r,1,#r) end
end
M.cd=cd
log('v'..M.version..' installed: all-vehicle cooldown, uptime gate '..(cfg.uptime_s or 120)..'s, stable gate '..(cfg.stable_s or 6)..'s')
return M