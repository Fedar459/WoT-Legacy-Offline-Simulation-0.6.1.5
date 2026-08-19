import BigWorld
import Math
import GUI
import math
import random
import game
import Keys
import cPickle
import weakref
from functools import partial
import constants
from ClientArena import ClientArena
from Event import Event, EventManager
from AreaDestructibles import g_destructiblesManager
from items import vehicles
from debug_utils import LOG_NOTE, LOG_ERROR
from PlayerEvents import g_playerEvents
from helpers.DecalMap import DecalMap
from gui.WindowsManager import g_windowsManager

if not getattr(BigWorld, '_offline_serverTime_patched', False):
    try:
        BigWorld.serverTime = BigWorld.time
        BigWorld._offline_serverTime_patched = True
        LOG_NOTE("[BATTLE] BigWorld.serverTime() patched to BigWorld.time() - prebattle timer will be stable")
    except Exception as e:
        LOG_NOTE("[BATTLE] Failed to patch BigWorld.serverTime: %s" % e)

class _FakePositionControl(object):
    def bindToVehicle(self, flag): pass
    def followCamera(self, flag):  pass
    def moveTo(self, pos):         pass

import Vehicle
if hasattr(Vehicle, 'DumbFilter'):
    Vehicle.DumbFilter = BigWorld.WGVehicleFilter
    LOG_NOTE("[BATTLE] DumbFilter replaced with WGVehicleFilter")

_CFG = {
    'basic': {
        'v_start_angles': Math.Vector3(0, 0, 0),
        'v_start_pos':    Math.Vector3(50, 0, 50),
        'cam_start_dist': 9.0,
        'cam_start_angles':     [-25.0, 110.0],
        'cam_start_target_pos': Math.Vector3(50, 0, 50),
        'cam_dist_constr':  [6.0, 11.0],
        'cam_pitch_constr': [-70.0, -5.0],
        'cam_sens':       0.005,
        'cam_pivot_pos':  Math.Vector3(0, 1, 0),
        'cam_fluency':    0.05,
        'shadow_light_dir': (0.55, -1, -1.7)
    }
}

_V_START_ANGLES   = None
_V_START_POS      = None
_CAM_START_DIST   = None
_CAM_START_ANGLES = None
_CAM_START_TARGET_POS = None
_CAM_PIVOT_POS    = None
_CAM_FLUENCY      = None
_SHADOW_LIGHT_DIR = None

_SOUND_EVENTS = {
    'battle_start':     '/GUI/notifications_FX/battle_start',
    'hit_penetration':  '/hits/explosions',
    'hit_no_damage':    '/hits/hits',
    'vehicle_destroyed': '/hits/tank_death',
}

def _play_sound_event(eventKey, pos=None):
    eventPath = _SOUND_EVENTS.get(eventKey)
    if not eventPath:
        return
    try:
        import SoundGroups
        if SoundGroups.g_instance:
            if pos is not None and hasattr(SoundGroups.g_instance, 'playSound3D'):
                SoundGroups.g_instance.playSound3D(eventPath, pos)
            else:
                SoundGroups.g_instance.playSound2D(eventPath)
            return
    except Exception as e:
        LOG_NOTE("[SOUND] playSound2D/3D('%s') failed: %s" % (eventPath, e))
    try:
        import FMOD
        snd = FMOD.getSound(eventPath)
        if snd:
            snd.play()
    except Exception as e:
        LOG_NOTE("[SOUND] FMOD fallback for '%s' failed: %s" % (eventPath, e))

_MAP_SPAWNS = {
    '01_karelia': {
        2: [[-405.14, 53.26, -398.27], [-391.14, 53.26, -398.27], [-419.14, 53.28, -398.27], [-405.14, 53.26, -384.27], [-405.14, 53.26, -412.27], [-395.14, 53.24, -388.27], [-415.14, 53.26, -388.27], [-395.14, 53.26, -408.27], [-415.14, 53.26, -408.27]],
        1: [[396.27, 53.63, 402.37], [410.27, 53.72, 402.37], [382.27, 53.58, 402.37], [396.27, 54.20, 416.37], [396.27, 53.28, 388.37], [406.27, 54.15, 412.37], [386.27, 53.86, 412.37], [406.27, 53.40, 392.37], [386.27, 53.42, 392.37]],
    },
    '02_malinovka': {
        2: [[75.6, 15.0, -391.92], [89.6, 15.0, -391.92], [61.6, 15.0, -391.92], [75.6, 15.0, -377.92], [75.6, 15.0, -405.92], [85.6, 15.0, -381.92], [65.6, 15.0, -381.92], [85.6, 15.0, -401.92], [65.6, 15.0, -401.92]],
        1: [[-372.7, 17.0, 108.1], [-358.7, 17.0, 108.1], [-386.7, 17.0, 108.1], [-372.7, 17.0, 122.1], [-372.7, 17.0, 94.1], [-362.7, 17.0, 118.1], [-382.7, 17.0, 118.1], [-362.7, 17.0, 98.1], [-382.7, 17.0, 98.1]],
    },
    '04_himmelsdorf': {
        2: [[70.0,-0.0,350.0], [70.0,-0.0,370.0], [70.0,-0.0,330.0], [50.0,-0.0,330.0], [50.0,-0.0,350.0], [50.0,-0.0,370.0], [30.0,-0.0,370.0], [30.0,-0.0,350.0], [30.0,-0.0,330.0], [90.0,-0.0,330.0], [90.0,-0.0,350.0], [90.0,-0.0,370.0], [100.0,-0.0,350.0], [100.0,-0.0,370.0], [100.0,-0.0,330.0]],
        1: [[0.0, 0.0, -250.0], [-20.0, 0.0, -250.0], [20.0, 0.0, -250.0], [10.0, 0.0, -240.0], [-10.0, 0.0, -240.0], [-40.0, 0.0, -250.0], [-40.0, 0.0, -230.0], [40.0, 0.0, -230.0], [-20.0, 0.0, -230.0], [20.0, 0.0, -230.0], [-40.0, 0.0, -270.0], [-20.0, 0.0, -270.0], [40.0, 0.0, -250.0], [0.0, 0.0, -260.0], [0.0, 0.0, -230.0]],
    },
    '05_prohorovka': {
        1: [[50.0,5.3,-445.0], [30.0,5.3,-445.0], [10.0,5.3,-445.0], [70.0,5.3,-445.0], [90.0,5.3,-445.0], [50.0,5.3,-465.0], [30.0,5.3,-465.0], [10.0,5.3,-465.0], [70.0,5.3,-465.0], [90.0,5.3,-465.0], [50.0,5.3,-425.0], [70.0,5.3,-425.0], [90.0,5.3,-425.0], [30.0,5.3,-425.0], [10.0,5.3,-425.0]],
        2: [[-125.0,5.0,450.0], [-145.0,5.0,450.0], [-165.0,5.0,450.0], [-105.0,5.0,450.0], [-85.0,5.0,450.0], [-125.0,5.0,430.0], [-105.0,5.0,430.0], [-85.0,5.0,430.0], [-145.0,5.0,430.0], [-165.0,5.0,430.0], [-125.0,5.0,470.0], [-105.0,5.0,470.0], [-85.0,5.0,470.0], [-165.0,5.0,470.0], [-145.0,5.0,470.0]],
    },
    '06_ensk': {
        1: [[20.0,-0.0,-250.0], [20.0,-0.0,-270.0], [20.0,-0.0,-230.0], [0.0,-0.0,-250.0], [40.0,-0.0,-250.0], [60.0,-0.0,-250.0], [-20.0,-0.0,-250.0], [20.0,-0.0,-290.0], [20.0,-0.0,-210.0], [0.0,-0.0,-270.0], [40.0,-0.0,-270.0], [0.0,-0.0,-230.0], [40.0,-0.0,-230.0]],
        2: [[20.0,0.0,250.0], [20.0,0.0,230.0], [0.0,0.0,230.0], [20.0,0.0,270.0], [0.0,0.0,250.0], [0.0,0.0,270.0], [-20.0,0.0,250.0], [-20.0,0.0,270.0], [-20.0,0.0,230.0], [40.0,0.0,250.0], [40.0,0.0,270.0], [40.0,0.0,230.0], [60.0,0.0,250.0], [60.0,0.0,270.0], [60.0,0.0,230.0]],
    },
    '07_lakeville': {
        1: [[-170.0,12.0,-320.0], [-170.0,12.0,-340.0], [-150.0,12.0,-340.0], [-130.0,12.0,-340.0], [-190.0,12.0,-340.0], [-210.0,12.0,-340.0], [-170.0,12.0,-300.0], [-150.0,12.0,-300.0], [-130.0,12.0,-300.0], [-190.0,12.0,-300.0], [-210.0,12.0,-300.0], [-190.0,12.0,-320.0], [-210.0,12.0,-320.0], [-150.0,12.0,-320.0], [-130.0,12.0,-320.0]],
        2: [[-170.0,12.0,320.0], [-170.0,12.0,340.0], [-150.0,12.0,340.0], [-130.0,12.0,340.0], [-190.0,12.0,340.0], [-210.0,12.0,340.0], [-170.0,12.0,300.0], [-150.0,12.0,300.0], [-130.0,12.0,300.0], [-190.0,12.0,300.0], [-210.0,12.0,300.0], [-190.0,12.0,320.0], [-210.0,12.0,320.0], [-150.0,12.0,320.0], [-130.0,12.0,320.0]],
    },
    '11_murovanka': {
        1: [[-205.0,0.0,-290.0], [-195.0,0.0,-290.0], [-215.0,0.0,-290.0], [-215.0,0.0,-300.0], [-215.0,0.0,-280.0], [-195.0,0.0,-280.0], [-195.0,0.0,-300.0], [-185.0,0.0,-290.0], [-225.0,0.0,-290.0], [-225.0,0.0,-280.0], [-225.0,0.0,-300.0], [-205.0,0.0,-300.0], [-185.0,0.0,-280.0], [-185.0,0.0,-300.0], [-205.0,0.0,-280.0]],
        2: [[200.5,0.0,295.0], [210.5,0.0,295.0], [190.5,0.0,295.0], [190.5,0.0,285.0], [190.5,0.0,305.0], [210.5,0.0,285.0], [210.5,0.0,305.0], [220.5,0.0,295.0], [220.5,0.0,285.0], [220.5,0.0,305.0], [180.5,0.0,295.0], [180.5,0.0,285.0], [180.5,0.0,305.0], [200.5,0.0,305.0], [200.5,0.0,285.0]],
    },
}

BOTS_PER_TEAM = 15

_DESTROYED_VEH_IDS = set()

_SAFE_BOT_POOL = ["ussr:IS-7", "ussr:MS-1", "ussr:ISU-152", "ussr:SU-26", "ussr:IS-4", "ussr:T-26"]

_RANDOM_BOT_POOL = [
    "ussr:MS-1", "ussr:T-26", "ussr:BT-7", "ussr:A-20", "ussr:T-28",
    "ussr:T-34", "ussr:T-43",
    "ussr:KV-1", "ussr:KV-3", "ussr:IS", "ussr:IS-3", "ussr:IS-4", "ussr:IS-7",
    "ussr:SU-26", "ussr:SU-85", "ussr:SU-100", "ussr:ISU-152",
    "germany:PzII", "germany:PzIII", "germany:PzIV", "germany:VK3001P",
    "germany:Panther",
    "germany:PzVI_Tiger_I", "germany:VK4502P", "germany:Maus",
    "germany:StuG_III", "germany:Hetzer", "germany:Ferdinand", "germany:JagdTiger",
    "usa:M2_lt", "usa:M3_Stuart", "usa:M3_Lee", "usa:M4_Sherman",
    "usa:T20",
    "usa:M6", "usa:T29", "usa:T32", "usa:T34_usa",
    "usa:M18_Hellcat", "usa:M36_Slugger", "usa:T28",
]

MAX_UNIQUE_BOT_TYPES_PER_BATTLE = 10

CAPTURE_RADIUS = 30.0                
CAPTURE_POINTS_TO_WIN = 100.0        
CAPTURE_RATE_PER_VEHICLE = 1.0       
CAPTURE_MAX_VEHICLES_COUNTED = 5     
CAPTURE_RESET_RATE = 2.0             

def _random_shell_damage(shotDescr):
    try:
        shellDmg = shotDescr['shell']['damage']
        if isinstance(shellDmg, (tuple, list)) and len(shellDmg) >= 2:
            return random.randint(int(shellDmg[0]), int(shellDmg[1]))
        elif isinstance(shellDmg, dict):
            lo = int(shellDmg.get('min', shellDmg.get('armorPiercing', 100)))
            hi = int(shellDmg.get('max', lo))
            return random.randint(min(lo, hi), max(lo, hi))
        else:
            return int(shellDmg)
    except Exception:
        return random.randint(90, 150)

def _ballistic_flight_time(launchPos, initVelocity, gravityMag, targetPos):
    vy0 = initVelocity.y
    dy = launchPos.y - targetPos.y
    g = abs(gravityMag)
    if g < 0.001:
        dist = (targetPos - launchPos).length
        speed = initVelocity.length
        return max(0.05, dist / max(speed, 1.0))
    disc = vy0 * vy0 + 2.0 * g * dy
    if disc < 0.0:
        dist = (targetPos - launchPos).length
        speed = initVelocity.length
        return max(0.05, dist / max(speed, 1.0))
    t = (vy0 + math.sqrt(disc)) / g
    return max(0.05, t)

def _calc_shot_penetration(shotData, targetDescr, targetYaw, shotDirWorld):
    try:
        hull_pa = targetDescr.hull.get('primaryArmor', (20, 20, 20))
        if isinstance(hull_pa, (int, float)):
            hull_pa = (hull_pa, hull_pa, hull_pa)

        shot_dir_local = math.atan2(shotDirWorld.x, shotDirWorld.z) - targetYaw
        shot_dir_local = (shot_dir_local + math.pi) % (2 * math.pi) - math.pi
        abs_ang = abs(shot_dir_local)

        if abs_ang < math.radians(60):
            thickness = hull_pa[0]
        elif abs_ang > math.radians(120):
            thickness = hull_pa[1]
        else:
            thickness = hull_pa[2]

        cosAngle = max(0.35, math.cos(min(abs_ang, math.radians(75))))

        shellInfo = shotData.get('shell', {}) if shotData else {}
        cosForCalc = max(abs(cosAngle), 0.02)

        ricochetAngleCos = shellInfo.get('ricochetAngleCos')
        if ricochetAngleCos is not None and cosForCalc < ricochetAngleCos:
            return (False, True, thickness, cosAngle)

        normAngle = shellInfo.get('normalizationAngle', 0.0)
        effAngleRad = max(0.0, math.acos(cosForCalc) - normAngle)
        effCos = max(math.cos(effAngleRad), 0.02)
        effectiveArmor = thickness / effCos

        pierce = shotData.get('piercingPower', (50, 50)) if shotData else (50, 50)
        pierce_val = pierce[0] if isinstance(pierce, (list, tuple)) else float(pierce)
        actualPiercing = pierce_val * random.uniform(0.875, 1.125)

        isPenetration = (thickness <= 0) or (actualPiercing >= effectiveArmor)
        return (isPenetration, False, thickness, cosAngle)
    except Exception:
        return (True, False, 0.0, 1.0)

def _hit_test_bot_hull(shotPos, rayDir, bot, maxDist):
    try:
        descr = bot.get('descr')
        if descr is None:
            return None
        hullBboxMin, hullBboxMax, _ = descr.hull['hitTester'].bbox
    except Exception:
        return None

    botPos = bot.get('pos')
    yaw = bot.get('yaw', 0.0)
    if botPos is None:
        return None

    cosY = math.cos(yaw)
    sinY = math.sin(yaw)

    dx = shotPos.x - botPos.x
    dz = shotPos.z - botPos.z
    localOx = dx * cosY - dz * sinY
    localOy = shotPos.y - botPos.y
    localOz = dx * sinY + dz * cosY

    localDx = rayDir.x * cosY - rayDir.z * sinY
    localDy = rayDir.y
    localDz = rayDir.x * sinY + rayDir.z * cosY

    tmin, tmax = 0.0, maxDist
    axes = ((localOx, localDx, hullBboxMin.x, hullBboxMax.x),
            (localOy, localDy, hullBboxMin.y, hullBboxMax.y),
            (localOz, localDz, hullBboxMin.z, hullBboxMax.z))
    for o, d, lo, hi in axes:
        if abs(d) < 1e-9:
            if o < lo or o > hi:
                return None
        else:
            t1 = (lo - o) / d
            t2 = (hi - o) / d
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > tmin:
                tmin = t1
            if t2 < tmax:
                tmax = t2
            if tmin > tmax:
                return None
    if tmin > maxDist:
        return None
    return tmin

def _make_bot_descr(pool=None, cache=None):
    sourcePool = pool if pool else _RANDOM_BOT_POOL
    candidates = list(sourcePool)
    random.shuffle(candidates)
    for typeName in candidates[:12]:
        if cache is not None and typeName in cache:
            return typeName, cache[typeName]
        try:
            descr = vehicles.VehicleDescr(typeName=typeName)
            if cache is not None:
                cache[typeName] = descr
            return typeName, descr
        except Exception:
            continue
    safe = list(_SAFE_BOT_POOL)
    random.shuffle(safe)
    for typeName in safe:
        if cache is not None and typeName in cache:
            return typeName, cache[typeName]
        try:
            descr = vehicles.VehicleDescr(typeName=typeName)
            if cache is not None:
                cache[typeName] = descr
            return typeName, descr
        except Exception as e:
            LOG_ERROR("[BATTLE] Even safe bot type failed '%s': %s" % (typeName, e))
            continue
    return None, None

def _load_cfg(mapName):
    global _V_START_ANGLES, _V_START_POS, _CAM_START_DIST, _CAM_START_ANGLES
    global _CAM_START_TARGET_POS, _CAM_PIVOT_POS, _CAM_FLUENCY, _SHADOW_LIGHT_DIR
    cfg = _CFG['basic']
    _V_START_ANGLES       = cfg['v_start_angles']
    _V_START_POS          = cfg['v_start_pos']
    _CAM_START_DIST       = cfg['cam_start_dist']
    _CAM_START_ANGLES     = cfg['cam_start_angles']
    _CAM_START_TARGET_POS = cfg['cam_start_target_pos']
    _CAM_PIVOT_POS        = cfg['cam_pivot_pos']
    _CAM_FLUENCY          = cfg['cam_fluency']
    _SHADOW_LIGHT_DIR     = cfg['shadow_light_dir']
    LOG_NOTE("[BATTLE][CFG] Loaded config for map: %s" % mapName)

def load_arena_type(arenaTypeID):
    from ArenaType import g_cache
    result = g_cache.get(arenaTypeID)
    if result is None:
        LOG_ERROR("[BATTLE] load_arena_type: UNKNOWN arenaTypeID=%s" % arenaTypeID)
    else:
        LOG_NOTE("[BATTLE] load_arena_type: OK id=%s name=%s" % (arenaTypeID, getattr(result, 'name', arenaTypeID)))
    return result

def get_ground_height(spaceID, pos):
    res = BigWorld.wg_collideSegment(spaceID,
                                     Math.Vector3(pos.x, 500.0, pos.z),
                                     Math.Vector3(pos.x, -500.0, pos.z), 18)
    if res is not None:
        return res[0].y
    res = BigWorld.wg_collideSegment(spaceID,
                                     Math.Vector3(pos.x, 500.0, pos.z),
                                     Math.Vector3(pos.x, -500.0, pos.z), 128)
    if res is not None:
        return res[0].y
    return 0.0

def has_line_of_sight(spaceID, fromPos, toPos, eyeHeight=1.4, targetMargin=2.5):
    try:
        start = Math.Vector3(fromPos.x, fromPos.y + eyeHeight, fromPos.z)
        end = Math.Vector3(toPos.x, toPos.y + eyeHeight, toPos.z)
        dx = end.x - start.x
        dy = end.y - start.y
        dz = end.z - start.z
        segLen = math.sqrt(dx * dx + dy * dy + dz * dz)
        if segLen < 0.5:
            return True

        closestHit = None
        for flag in (0, 18, 128):
            try:
                res = BigWorld.wg_collideSegment(spaceID, start, end, flag)
            except Exception:
                res = None
            if res is not None:
                hp = res[0]
                hd = math.sqrt((hp.x - start.x) ** 2 + (hp.y - start.y) ** 2 + (hp.z - start.z) ** 2)
                if closestHit is None or hd < closestHit:
                    closestHit = hd

        if closestHit is None:
            return True
        return closestHit >= segLen - targetMargin
    except Exception as e:
        LOG_NOTE("[BOT-AI] LOS check failed: %s" % e)
        return True

def _generate_positions(basePositions, count, spacing=22.0):
    positions = [Math.Vector3(p[0], p[1], p[2]) for p in basePositions]
    if len(positions) >= count:
        return positions[:count]

    if positions:
        cx = sum(p.x for p in positions) / len(positions)
        cy = positions[0].y
        cz = sum(p.z for p in positions) / len(positions)
    else:
        cx, cy, cz = 0.0, 0.0, 0.0

    ring = 1
    while len(positions) < count:
        for gx in range(-ring, ring + 1):
            for gz in range(-ring, ring + 1):
                if len(positions) >= count:
                    break
                if abs(gx) != ring and abs(gz) != ring:
                    continue
                positions.append(Math.Vector3(cx + gx * spacing, cy, cz + gz * spacing))
            if len(positions) >= count:
                break
        ring += 1
    return positions[:count]

_FALLBACK_SPAWN_OFFSET = 230.0

def _fallback_team_positions(get_pos_on_ground):
    p1 = get_pos_on_ground(-_FALLBACK_SPAWN_OFFSET, -_FALLBACK_SPAWN_OFFSET)
    p2 = get_pos_on_ground(_FALLBACK_SPAWN_OFFSET, _FALLBACK_SPAWN_OFFSET)
    return p1, p2

class OfflineVehicleFilter(object):
    def __init__(self, startPos, startYaw=0.0):
        self.position = Math.Vector3(startPos.x, startPos.y, startPos.z)
        self.yaw      = float(startYaw)
        self.pitch    = 0.0
        self.roll     = 0.0
        self.velocity = Math.Vector3(0.0, 0.0, 0.0)
        self.speed    = 0.0
        self.rotationSpeed = 0.0
        self.movementInfo  = None
        self.enableClientFilters = False

    def reset(self, pos):
        self.position = Math.Vector3(pos.x, pos.y, pos.z)

    def setMovement(self, speed, rotSpeed):
        self.speed = speed
        self.rotationSpeed = rotSpeed
        self.velocity = Math.Vector3(
            math.sin(self.yaw) * speed,
            0.0,
            math.cos(self.yaw) * speed
        )

    def getVehicleSpeed(self):
        return self.speed

class DummyGunRotator:
    def __init__(self):
        self.turretMatrix = Math.WGAdaptiveMatrixProvider()
        self.gunMatrix = Math.WGAdaptiveMatrixProvider()
        self.__loftedTrajectory = False
        self.__turretYaw = 0.0
        self.__gunPitch = 0.0
        self.__updateMatrices()
    def setLoftedTrajectory(self, flag):    pass
    def switchLoftedTrajectory(self):       pass
    def shoot(self):                        pass
    def update(self, *a, **kw):             pass
    def setGunMarker(self, *a, **kw):       pass
    def destroy(self):                      pass
    def onVehicleCollision(self, *a):       pass
    def setShotPosition(self, *a):          pass
    def __updateMatrices(self):
        m = Math.Matrix()
        m.setRotateY(self.__turretYaw)
        self.turretMatrix.setStaticTransform(m)
        m2 = Math.Matrix()
        m2.setRotateX(self.__gunPitch)
        self.gunMatrix.setStaticTransform(m2)

    def start(self): pass
    def stop(self): pass

    def getLoftedTrajectory(self):
        return self.__loftedTrajectory

    def attachToFilter(self, vehicleFilter):
        vehicleFilter.turretMatrix.target = self.turretMatrix
        vehicleFilter.gunMatrix.target = self.gunMatrix

    def updateRotation(self, deltaYaw, deltaPitch):
        self.__turretYaw += deltaYaw
        self.__gunPitch += deltaPitch
        self.__gunPitch = max(-0.3, min(0.3, self.__gunPitch))
        self.__updateMatrices()

class BotTurretRotator(object):
    def __init__(self):
        self.turretMatrix = Math.WGAdaptiveMatrixProvider()
        self.gunMatrix = Math.WGAdaptiveMatrixProvider()
        self.yaw = 0.0
        self.pitch = 0.0
        self._apply()

    def _apply(self):
        m = Math.Matrix()
        m.setRotateY(self.yaw)
        self.turretMatrix.setStaticTransform(m)
        m2 = Math.Matrix()
        m2.setRotateX(self.pitch)
        self.gunMatrix.setStaticTransform(m2)

    def turnTowards(self, localYawTarget, maxYawStep, localPitchTarget=0.0, maxPitchStep=0.5):
        yawDiff = (localYawTarget - self.yaw + math.pi) % (2.0 * math.pi) - math.pi
        yawStep = max(-maxYawStep, min(maxYawStep, yawDiff))
        self.yaw += yawStep

        pitchDiff = localPitchTarget - self.pitch
        pitchStep = max(-maxPitchStep, min(maxPitchStep, pitchDiff))
        self.pitch = max(-0.3, min(0.15, self.pitch + pitchStep))

        self._apply()
        return abs(yawDiff) < 0.06 and abs(pitchDiff) < 0.05

class _DummyCell:
    def trackPointWithGun(self, *a): pass
    def stopTrackingWithGun(self, *a): pass
    def __getattr__(self, name):
        return lambda *a, **kw: None

class SimpleAvatar:
    def __init__(self, name, team, spaceID):
        self.name = name
        self.team = team
        self.spaceID = spaceID
        self.playerVehicleID = None
        self.vehicleTypeDescriptor = None
        self.isOnArena = True
        self.isVehicleAlive = True
        self.inputHandler = None
        self.gunRotator = None
        self.hitTesters = set()
        self.initialVehicleSpeeds = {}
        self._ownVehicleMProv = Math.WGAdaptiveMatrixProvider()
        self._arena = None
        self._minimap = None
        self._terrainEffects = None
        self._projectileMover = None
        self.__guiConfig = {'silhouetteColors': {'self': (0,0,0,0), 'enemy': (0,0,0,0), 'friend': (0,0,0,0)}}
        self.turretMatrix = Math.WGAdaptiveMatrixProvider()
        self.gunMatrix = Math.WGAdaptiveMatrixProvider()
        self._moveForward = False
        self._moveBack = False
        self._turnLeft = False
        self._turnRight = False
        self.getCurrentShots = lambda: (0, None)
        self.currentMove = 0.0
        self.currentTurn = 0.0
        self._reloadReadyTime = 0.0
        self._currentShellIndex = 0
        self.onSpaceLoaded = lambda: None
        self.onVehicleLeaveWorld = Event()
        self.cell = _DummyCell()
        self.base = _DummyCell()
        self.enableOwnVehicleAutorotation = False
        self._flyCam         = None
        self.positionControl = _FakePositionControl()
        class _FakeModel(object):
            def getSound(self, *a): return None
            def attach(self, *a): pass
            def detach(self, *a): pass
        self.newFakeModel = lambda *a, **k: _FakeModel()
        self.onGunShotChanged        = Event()
        self.onGunReloadTimeSet      = Event()
        self.onAutoAimVehicleEnter   = Event()
        self.onAutoAimVehicleLeave   = Event()
        self.onShootingStateChanged  = Event()
        self.onCameraChanged         = Event()
        self.onVehicleEnterWorld     = Event()
        self.autoAim = lambda target: None
        self.enableOwnVehicleAutorotation = lambda flag: None
        self.showTracer = lambda *a, **kw: None
        self.explodeProjectile = lambda *a, **kw: None
        self.showDamageFromShot = lambda *a, **kw: None
        self.showDamageFromExplosion = lambda *a, **kw: None
        LOG_NOTE("[BATTLE][AVATAR] SimpleAvatar created: name=%s team=%d" % (name, team))

    def initSpace(self): pass
    def vehicle_onEnterWorld(self, vehicle):
        LOG_NOTE("[BATTLE][AVATAR] vehicle_onEnterWorld: vehID=%s" % getattr(vehicle, 'id', '?'))
    def vehicle_onLeaveWorld(self, vehicle):
        LOG_NOTE("[BATTLE][AVATAR] vehicle_onLeaveWorld: vehID=%s" % getattr(vehicle, 'id', '?'))
    def bindToVehicle(self, doBind, vehicleID=None):
        LOG_NOTE("[BATTLE][AVATAR] bindToVehicle: doBind=%s vehicleID=%s" % (doBind, vehicleID))
        if doBind and vehicleID is not None:
            veh = BigWorld.entity(vehicleID)
            if veh:
                self._ownVehicleMProv.target = veh.matrix
                LOG_NOTE("[BATTLE][AVATAR] bindToVehicle: matrix linked OK")
            else:
                LOG_ERROR("[BATTLE][AVATAR] bindToVehicle: entity %s not found!" % vehicleID)
        else:
            self._ownVehicleMProv.target = None
    def getVehicleAttached(self):
        return BigWorld.entity(self.playerVehicleID) if self.playerVehicleID else None
    def getOwnVehicleMatrix(self):
        return self._ownVehicleMProv
    def getOwnVehiclePosition(self):
        target = self._ownVehicleMProv.target
        if target is not None:
            return Math.Matrix(target).translation
        veh = BigWorld.entity(self.playerVehicleID) if self.playerVehicleID else None
        if veh is not None:
            return veh.position
        return Math.Vector3(0, 0, 0)
    def getOwnVehicleSpeeds(self):
        return (0.0, 0.0)
    def getOwnVehicleShotDispersionAngle(self, turretRotationSpeed, isShot=False):
        return 0.01
    def handleKey(self, isDown, key, mods):
        if not getattr(self, 'inputHandler', None): return False
        try:
            return self.inputHandler.handleKeyEvent(key, isDown)
        except:
            return False
    def handleKeyEvent(self, event):
        if not getattr(self, 'inputHandler', None): return False
        isDown, key, mods, isRepeat = game.convertKeyEvent(event)

        veh = self.getVehicleAttached()
        if veh and hasattr(veh, 'filter') and veh.filter:
            if key == Keys.KEY_W:   self._moveForward = isDown
            elif key == Keys.KEY_S: self._moveBack    = isDown
            elif key == Keys.KEY_A: self._turnLeft    = isDown
            elif key == Keys.KEY_D: self._turnRight   = isDown

            move = (1.0 if self._moveForward else 0.0) - (1.0 if self._moveBack else 0.0)
            turn = (1.0 if self._turnRight else 0.0) - (1.0 if self._turnLeft else 0.0)

            self.currentMove = move
            self.currentTurn = turn

        try:
            return self.inputHandler.handleKeyEvent(event)
        except:
            return False

    def handleMouseEvent(self, dx, dy, dz):
        if getattr(self, 'inputHandler', None):
            try:
                if self.inputHandler.handleMouseEvent(dx, dy, dz):
                    return True
            except:
                pass
        if self.gunRotator:
            self.gunRotator.updateRotation(dx * 0.005, dy * 0.005)
            return True
        return False

    def prerequisites(self):
        return []
    def onRecreateDevice(self): pass
    def leaveArena(self): pass
    def setForcedGuiControlMode(self, enable, stopVehicle=True):
        from gui.Cursor import forceShowCursor
        forceShowCursor(enable)
    def addModel(self, model): BigWorld.addModel(model)
    def delModel(self, model): BigWorld.delModel(model)
    def handleVehicleCollidedVehicle(self, vehA, vehB, hitPt, time): pass
    def shoot(self):
        veh = self.getVehicleAttached()
        if not veh:
            LOG_NOTE("[BATTLE][AVATAR] shoot: no vehicle attached")
            return
        _battle_ref = getattr(self, '_offline_battle', None)
        if _battle_ref is not None and not getattr(_battle_ref, '_battleStarted', True):
            LOG_NOTE("[BATTLE][AVATAR] shoot: blocked, prebattle countdown still running")
            return

        now = BigWorld.time()
        reloadReadyTime = getattr(self, '_reloadReadyTime', 0.0)
        if now < reloadReadyTime:
            LOG_NOTE("[BATTLE][AVATAR] shoot: blocked, gun still reloading (%.2fs left)" % (reloadReadyTime - now))
            return

        _ammoIdx = getattr(self, '_currentShellIndex', 0)
        _ammoList = getattr(self, '_ammo', None)
        if _ammoList and 0 <= _ammoIdx < len(_ammoList) and _ammoList[_ammoIdx][1] <= 0:
            LOG_NOTE("[BATTLE][AVATAR] shoot: blocked, no ammo of shell idx=%d" % _ammoIdx)
            return

        if hasattr(veh, 'showShooting'):
            try:
                _wasPlayer = getattr(veh, 'isPlayer', None)
                try:
                    if _wasPlayer:
                        veh.isPlayer = False
                    veh.showShooting(1)
                finally:
                    if _wasPlayer is not None:
                        veh.isPlayer = _wasPlayer
                LOG_NOTE("[BATTLE] showShooting OK (isPlayer temporarily toggled)")
            except Exception as e:
                LOG_NOTE("[BATTLE] showShooting failed: %s" % e)
        try:
            import Math, random
            descr = self.vehicleTypeDescriptor
            if descr is None:
                return
            shotDescr = descr.shot
            speed   = shotDescr['speed']
            gravity = shotDescr['gravity']

            if hasattr(self, '_offline_matrix'):
                vehMat = Math.Matrix(self._offline_matrix)
            else:
                vehMat = Math.Matrix(veh.matrix)

            turretMat = Math.Matrix(self.turretMatrix)
            gunMat    = Math.Matrix(self.gunMatrix)

            worldDir = Math.Matrix()
            worldDir.setIdentity()
            worldDir.postMultiply(gunMat)
            worldDir.postMultiply(turretMat)
            worldDir.postMultiply(vehMat)
            gunWorldDir = worldDir.applyVector(Math.Vector3(0, 0, 1))

            descr_turret = descr.turret
            gunOffsetLocal = Math.Vector3(descr_turret['gunPosition'])
            turretOffs = Math.Vector3(descr.hull['turretPositions'][0]) + Math.Vector3(descr.chassis['hullPosition'])
            turretWorld = Math.Matrix(turretMat)
            turretWorld.translation = turretOffs
            turretWorld.postMultiply(vehMat)
            gunWorldPos = turretWorld.applyPoint(gunOffsetLocal)
            shotPos = gunWorldPos
            refVelocity = gunWorldDir * speed
            shotID      = random.randint(1, 999999)

            pm = self.projectileMover
            try:
                shotEffectsIndex = descr.shot['shell']['effectsIndex']
                effectsDescr = vehicles.g_cache.shotEffects[shotEffectsIndex]
            except Exception as e:
                LOG_NOTE("[BATTLE] shotEffects lookup failed: %s, trying index 0" % e)
                try:
                    effectsDescr = vehicles.g_cache.shotEffects[0]
                except:
                    effectsDescr = None
            if effectsDescr is None:
                LOG_NOTE("[BATTLE] shoot: no effectsDescr, skipping projectile")
                return

            pm.add(
                shotID,
                effectsDescr,
                gravity,
                shotPos,
                refVelocity,
                shotPos,
                True
            )
            LOG_NOTE("[BATTLE] Projectile launched: shotID=%d speed=%.1f" % (shotID, speed))

            try:
                _ammoList = getattr(self, '_ammo', None)
                if _ammoList and 0 <= _ammoIdx < len(_ammoList):
                    if _ammoList[_ammoIdx][1] > 0:
                        _ammoList[_ammoIdx][1] -= 1
                    _newCount = _ammoList[_ammoIdx][1]
                    _bw = getattr(getattr(self, '_offline_battle', None), 'battleWindow', None)
                    for _panelName in ('consumablesPanel', 'ammoPanel'):
                        _panel = getattr(_bw, _panelName, None) if _bw else None
                        if _panel is None:
                            continue
                        try:
                            _panel.setItemQuantityInSlot(_ammoIdx, _newCount)
                        except Exception as e:
                            LOG_NOTE("[BATTLE] shoot: %s.setItemQuantityInSlot failed: %s" % (_panelName, e))
                    try:
                        if self.inputHandler is not None:
                            aim = getattr(self.inputHandler, 'aim', None)
                            if aim is not None:
                                aim.setAmmoStock(_newCount)
                    except Exception as e:
                        LOG_NOTE("[BATTLE] shoot: aim.setAmmoStock failed: %s" % e)
                    LOG_NOTE("[BATTLE] Ammo: shell idx=%d left=%d" % (_ammoIdx, _newCount))
            except Exception as e:
                LOG_NOTE("[BATTLE] shoot: ammo decrement failed: %s" % e)

            try:
                from ProjectileMover import collideDynamic
                battle = getattr(self, '_offline_battle', None)
                maxDist = shotDescr.get('maxDistance', 700.0)

                exceptIDs = set()
                if self.playerVehicleID is not None:
                    exceptIDs.add(self.playerVehicleID)

                farPoint = shotPos + gunWorldDir * maxDist
                staticRes = BigWorld.wg_collideSegment(self.spaceID, shotPos, farPoint, 128)
                if staticRes is not None:
                    staticPoint = staticRes[0]
                    staticDist  = (staticPoint - shotPos).length
                else:
                    staticPoint = farPoint
                    staticDist  = maxDist

                dynCheckEnd = shotPos + gunWorldDir * staticDist
                dynRes = collideDynamic(shotPos, dynCheckEnd, exceptIDs)

                hitVehicle  = None   
                hitBot      = None   
                impactPoint = staticPoint
                effectMat   = 'ground'
                hitCos      = 1.0
                hitThick    = 0
                bestDist    = staticDist

                if dynRes is not None:
                    _hitEntity, hitDist, _hitCos, _hitThick = dynRes
                    if hitDist < bestDist:
                        hitVehicle = _hitEntity
                        hitCos     = _hitCos
                        hitThick   = _hitThick
                        bestDist   = hitDist

                if battle is not None:
                    for _bot in battle._bot_ai:
                        if _bot.get('dead'):
                            continue
                        try:
                            tHit = _hit_test_bot_hull(shotPos, gunWorldDir, _bot, bestDist)
                        except Exception:
                            tHit = None
                        if tHit is not None and tHit < bestDist:
                            hitBot     = _bot
                            hitVehicle = None
                            bestDist   = tHit

                if hitVehicle is not None or hitBot is not None:
                    impactPoint = shotPos + gunWorldDir * bestDist
                    effectMat   = 'armor'

                pm.hide(shotID, impactPoint)

                flightTime = _ballistic_flight_time(shotPos, refVelocity, gravity, impactPoint)

                def _do_explode(sid=shotID, p=pm, ed=effectsDescr, pt=impactPoint, d=gunWorldDir,
                                 mat=effectMat, hitVeh=hitVehicle, hitBotRef=hitBot,
                                 thickness=hitThick, cosA=hitCos,
                                 shellData=shotDescr, b=battle, av=self):
                    try:
                        p.explode(sid, ed, mat, pt, d)
                    except Exception as e:
                        LOG_NOTE("[BATTLE][FX] pm.explode failed (%s) - using manual fallback" % e)
                        try:
                            effectTypeStr = mat + 'Hit'
                            stages, effects, _junk = ed[effectTypeStr]
                            av.terrainEffects.addNew(
                                pt, effects, stages, None, dir=d,
                                start=pt + d.scale(-1.0), end=pt + d.scale(1.0))
                            LOG_NOTE("[BATTLE][FX] manual explosion fallback OK at %s (mat=%s)" % (pt, mat))
                        except Exception as e2:
                            LOG_NOTE("[BATTLE][FX] manual explosion fallback also failed: %s" % e2)
                    if b is None:
                        return
                    bot = hitBotRef
                    if bot is None and hitVeh is not None:
                        try:
                            hitID = hitVeh.id
                        except Exception:
                            hitID = None
                        if hitID is not None:
                            for _b in b._bot_ai:
                                if _b.get('vehID') == hitID:
                                    bot = _b
                                    break
                    if bot is None or bot.get('dead'):
                        return
                    try:
                        isPen, isRic, _th, _cs = _calc_shot_penetration(
                            shellData, bot['descr'], bot.get('yaw', 0.0), d)
                    except Exception:
                        isPen, isRic = True, False
                    if not isPen:
                        LOG_NOTE("[BATTLE] Shot did NOT penetrate bot %s (%s)" %
                                 (bot.get('vehID'), 'ricochet' if isRic else 'no-pen'))
                        _play_sound_event('hit_no_damage', pos=bot.get('pos'))
                        return
                    dmg = _random_shell_damage(shellData)
                    b.apply_damage_to_bot(bot, dmg)
                    LOG_NOTE("[BATTLE] Real shell hit bot %s for %d dmg (flight=%.2fs)" %
                             (bot.get('vehID'), dmg, flightTime))

                BigWorld.callback(flightTime, _do_explode)
            except Exception as e:
                LOG_NOTE("[BATTLE] real-shell ballistic trace failed: %s" % e)

            self._startGunReload(descr)
        except Exception as e:
            LOG_NOTE("[BATTLE] shoot() failed: %s" % e)

    def _getGunReloadTime(self, descr):
        default_reload = 5.0
        try:
            shots = descr.gun['shots']
            idx = getattr(self, '_currentShellIndex', 0)
            if shots and 0 <= idx < len(shots):
                shot = shots[idx]
                try:
                    rt = shot['reloadTime']
                    if rt:
                        return float(rt)
                except Exception:
                    pass
            try:
                rt = descr.gun['reloadTime']
                if rt:
                    return float(rt)
            except Exception:
                pass
            try:
                rt = descr.gun.reloadTime
                if rt:
                    return float(rt)
            except Exception:
                pass
        except Exception as e:
            LOG_NOTE("[BATTLE] _getGunReloadTime failed, using default: %s" % e)
        return default_reload

    def _startGunReload(self, descr):
        try:
            reloadTime = self._getGunReloadTime(descr)
            now = BigWorld.time()
            self._reloadReadyTime = now + reloadTime

            try:
                self.onGunReloadTimeSet(reloadTime)
            except Exception as e:
                LOG_NOTE("[BATTLE] onGunReloadTimeSet failed: %s" % e)

            try:
                if self.inputHandler is not None:
                    self.inputHandler.setReloading(reloadTime)
            except Exception as e:
                LOG_NOTE("[BATTLE] _startGunReload: setReloading(reloadTime) failed: %s" % e)

            def _onReloadComplete():
                try:
                    from AvatarInputHandler import aims
                    if aims._g_aimState:
                        aims._g_aimState['reload']['isReloading'] = False
                except Exception:
                    pass
                try:
                    if self.inputHandler is not None:
                        self.inputHandler.setReloading(0)
                except Exception:
                    pass
                LOG_NOTE("[BATTLE] Gun reload complete")

            BigWorld.callback(reloadTime, _onReloadComplete)
            LOG_NOTE("[BATTLE] Gun reload started: %.2fs (per vehicle spec)" % reloadTime)
        except Exception as e:
            LOG_NOTE("[BATTLE] _startGunReload failed: %s" % e)

    def lockOn(self, target): pass
    def onAmmoButtonPressed(self, index):
        try:
            descr = self.vehicleTypeDescriptor
            if not descr:
                return
            shots = descr.gun['shots']
            if index >= len(shots):
                return
            self._currentShellIndex = index

            try:
                descr.activeGunShotIndex = index
            except Exception as e:
                LOG_NOTE("[BATTLE] onAmmoButtonPressed: descr.activeGunShotIndex failed: %s" % e)

            veh = self.getVehicleAttached()
            if veh is not None:
                try:
                    veh.typeDescriptor.activeGunShotIndex = index
                except Exception as e:
                    LOG_NOTE("[BATTLE] onAmmoButtonPressed: veh.typeDescriptor.activeGunShotIndex failed: %s" % e)

            try:
                self.onGunShotChanged()
            except Exception as e:
                LOG_NOTE("[BATTLE] onAmmoButtonPressed: onGunShotChanged failed: %s" % e)

            bw = getattr(self._offline_battle, 'battleWindow', None)
            if bw and hasattr(bw, 'ammoPanel'):
                for i in range(len(shots)):
                    bw.ammoPanel.setSelectedAsCurrent(i, i == index)

            try:
                _ammoList = getattr(self, '_ammo', None)
                if _ammoList and 0 <= index < len(_ammoList) and self.inputHandler is not None:
                    aim = getattr(self.inputHandler, 'aim', None)
                    if aim is not None:
                        aim.setAmmoStock(_ammoList[index][1])
            except Exception as e:
                LOG_NOTE("[BATTLE] onAmmoButtonPressed: setAmmoStock failed: %s" % e)

            LOG_NOTE("[BATTLE] Shell switched to index %d (descr.shot kind=%s)" % (
                index, shots[index]['shell'].get('kind', '?') if index < len(shots) else '?'))
        except Exception as e:
            LOG_NOTE("[BATTLE] onAmmoButtonPressed failed: %s" % e)
    def onAvatarReady(self): pass
    def getCurrentVehicleId(self):
        return self.playerVehicleID
    @property
    def minimap(self):
        if self._minimap is None:
            from gui.Minimap import Minimap
            self._minimap = Minimap()
        return self._minimap
    @property
    def terrainEffects(self):
        if self._terrainEffects is None:
            from helpers import bound_effects
            self._terrainEffects = bound_effects.StaticSceneBoundEffects()
        return self._terrainEffects
    @property
    def projectileMover(self):
        if self._projectileMover is None:
            from ProjectileMover import ProjectileMover
            self._projectileMover = ProjectileMover()
        return self._projectileMover
    @property
    def guiConfig(self):
        return self.__guiConfig

class OfflineBattle:

    def _patch_vehicle(self):
        import Vehicle as V
        if hasattr(V.Vehicle, '_patched_alive'):
            return
        V.Vehicle.onLeaveWorld   = lambda self: setattr(self, 'isStarted', False)

        def _offline_isAlive(self_veh):
            try:
                avatar = BigWorld.player()
                arena = getattr(avatar, 'arena', None)
                if arena is not None:
                    vdata = arena.vehicles.get(self_veh.id)
                    if vdata is not None:
                        return bool(vdata.get('isAlive', True))
            except Exception:
                pass
            return True
        V.Vehicle.isAlive        = _offline_isAlive
        V.Vehicle.set_isCrewActive = lambda self, prev=None: None
        V.Vehicle.set_health     = lambda self, prev=None: None
        def safe_collideDynamic(self_veh, mass, damage, direction):
            pass
        V.Vehicle.collideDynamic = safe_collideDynamic
        V.Vehicle._patched_alive = True
        LOG_NOTE("[BATTLE] Vehicle patched (alive/health/leave)")

    def __init__(self):
        self.spaceID = None
        self.arena = None
        self.playerAvatar = None
        self.vehicles = []
        self._oldPlayer = None
        self.battleWindow = None
        self._prebattleStartTime = None
        self._bot_ai = []
        self._battleStarted = False  
        self._stopped = False
        self._finish_called = False
        self._periodSwitchSent = False
        self._periodChangeBattleHandled = False
        self._arenaTypeName = None
        self._runtime_spawn_idx = {1: 0, 2: 0}
        self._marker_frame = None
        self._marker_target_vehID = None
        self._capture_bar_gui = None
        self._capture_result_text = None
        self._bot_pool = None
        self._bot_descr_cache = {}
        self._accountEntityID = None
        self._battleAmbientSound = None
        self._battleMusicSound = None
        try:
            from gui.Scaleform.Battle import Battle
            if not hasattr(Battle, '_patched_for_offline_cleanup'):
                if hasattr(Battle, 'beforeDelete'):
                    orig_beforeDelete = Battle.beforeDelete
                    def safe_beforeDelete(self_window, *a, **kw):
                        try: orig_beforeDelete(self_window, *a, **kw)
                        except: pass
                    Battle.beforeDelete = safe_beforeDelete
                if hasattr(Battle, 'destroy'):
                    orig_destroy = Battle.destroy
                    def safe_destroy(self_window, *a, **kw):
                        try: orig_destroy(self_window, *a, **kw)
                        except: pass
                    Battle.destroy = safe_destroy
                Battle._patched_for_offline_cleanup = True
        except: pass
        LOG_NOTE("[BATTLE] OfflineBattle instance created")

    def start(self, arenaTypeID=None, playerVehicleName=None, botCount=1):
        LOG_NOTE("[BATTLE] start() called: arenaTypeID=%s playerVehicleName=%s botCount=%d" % (arenaTypeID, playerVehicleName, botCount))
        _DESTROYED_VEH_IDS.clear()

        poolSize = min(len(_RANDOM_BOT_POOL), MAX_UNIQUE_BOT_TYPES_PER_BATTLE)
        self._bot_pool = random.sample(_RANDOM_BOT_POOL, poolSize)
        self._bot_descr_cache = {}
        LOG_NOTE("[BATTLE] Bot pool for this battle (%d/%d unique types): %s" %
                 (poolSize, len(_RANDOM_BOT_POOL), self._bot_pool))

        if playerVehicleName is None:
            try:
                from CurrentVehicle import g_currentVehicle
                veh = g_currentVehicle.vehicle
                if veh and veh.descriptor:
                    playerDescr = veh.descriptor
                    playerCompDescr = playerDescr.makeCompactDescr()
                    LOG_NOTE("[BATTLE] Using garage vehicle: %s" % playerDescr.type.name)
                else:
                    LOG_NOTE("[BATTLE] g_currentVehicle.vehicle is None or has no descriptor!")
                    playerCompDescr = None
            except Exception as e:
                LOG_NOTE("[BATTLE] Can't get garage vehicle: %s" % e)
                playerCompDescr = None
        else:
            playerCompDescr = None

        if isinstance(arenaTypeID, (tuple, list)):
            arenaTypeID = arenaTypeID[0]

        LOG_NOTE("[BATTLE] Final arenaTypeID='%s'" % arenaTypeID)
        self._patch_decalmap()
        self._patch_gui()
        try:
            from gui.Scaleform.Waiting import Waiting
            Waiting.hide()
        except: pass

        _load_cfg(arenaTypeID)

        DecalMap.g_instance = None
        try:
            BigWorld.wg_addDecal = lambda *a, **k: 0
        except: pass

        self._oldPlayer = BigWorld.player()
        LOG_NOTE("[BATTLE] Old player saved: %s" % type(self._oldPlayer).__name__)

        try:
            from Offline import Manager
            playerName = Manager._player_name
            LOG_NOTE("[BATTLE] Player name from Manager: '%s'" % playerName)
        except Exception as e:
            LOG_NOTE("[BATTLE] Could not get player name from Manager: %s" % e)
            playerName = "Commander"

        self.playerAvatar = SimpleAvatar(playerName, 1, -1)
        self.playerAvatar._offline_battle = self
        BigWorld.player = lambda: self.playerAvatar
        LOG_NOTE("[BATTLE] BigWorld.player() now returns SimpleAvatar")

        arenaType = load_arena_type(arenaTypeID)
        if arenaType is None:
            LOG_ERROR("[BATTLE] arenaType is None, aborting!")
            return
        
        arenaTypeName = arenaTypeID
        LOG_NOTE("[BATTLE] arenaTypeID resolved: name=%s" % (arenaTypeName,))
        self._arenaTypeName = arenaTypeName

        self._arenaBBox = None
        try:
            bbox = getattr(arenaType, 'boundingBox', None)
            if bbox and len(bbox) >= 2:
                p0, p1 = bbox[0], bbox[1]
                minX, minZ = min(p0[0], p1[0]), min(p0[1], p1[1])
                maxX, maxZ = max(p0[0], p1[0]), max(p0[1], p1[1])
                margin = 40.0  
                if maxX - minX > 2 * margin and maxZ - minZ > 2 * margin:
                    self._arenaBBox = (minX + margin, minZ + margin, maxX - margin, maxZ - margin)
                    LOG_NOTE("[BATTLE] Map bounds for bot AI: %s" % (self._arenaBBox,))
        except Exception as e:
            LOG_NOTE("[BATTLE] Could not read arenaType.boundingBox: %s" % e)
        if self._arenaBBox is None:
            self._arenaBBox = (-480.0, -480.0, 480.0, 480.0)
            LOG_NOTE("[BATTLE] Map bounds fallback used: %s" % (self._arenaBBox,))

        BigWorld.worldDrawEnabled(False)
        BigWorld.wg_useAttachmentBboxesInShadowCasting(True)
        BigWorld.wg_setIndoorMainLightDir(_SHADOW_LIGHT_DIR)

        self.spaceID = BigWorld.createSpace()
        LOG_NOTE("[BATTLE] Created spaceID=%s" % self.spaceID)
        BigWorld.addSpaceGeometryMapping(self.spaceID, None, 'spaces/' + arenaTypeName)
        LOG_NOTE("[BATTLE] Geometry mapped: spaces/%s" % arenaTypeName)

        import ResMgr
        geomDir = 'spaces/' + arenaTypeName
        try:
            for file in ResMgr.listFiles(geomDir):
                if file.endswith('.bsp'):
                    BigWorld.addSpaceGeometryMapping(self.spaceID, None, geomDir + '/' + file)
        except:
            pass

        self.playerAvatar.spaceID = self.spaceID
        self._accountEntityID = BigWorld.createEntity("Account", self.spaceID, 0,
            _V_START_POS,
            (math.radians(_V_START_ANGLES[2]),
             math.radians(_V_START_ANGLES[1]),
             math.radians(_V_START_ANGLES[0])), {})
        LOG_NOTE("[BATTLE] Account entity created: ID=%s" % self._accountEntityID)

        cam = BigWorld.CursorCamera()
        cam.spaceID       = self.spaceID
        cam.pivotMaxDist  = _CAM_START_DIST
        cam.maxDistHalfLife  = _CAM_FLUENCY
        cam.turningHalfLife  = _CAM_FLUENCY
        cam.movementHalfLife = 0.0
        cam.pivotPosition    = _CAM_PIVOT_POS

        matSrc = Math.Matrix()
        matSrc.setRotateYPR((math.radians(_CAM_START_ANGLES[1]),
                             math.radians(_CAM_START_ANGLES[0]), 0.0))
        cam.source = matSrc
        matTgt = Math.Matrix()
        matTgt.setTranslate(_CAM_START_TARGET_POS)
        cam.target = matTgt

        BigWorld.camera(cam)
        BigWorld.worldDrawEnabled(True)
        g_destructiblesManager.startSpace(self.spaceID)

        self.arena = ClientArena(arenaTypeID, 0, 0)
        self.playerAvatar.arena = self.arena
        LOG_NOTE("[BATTLE] ClientArena created OK")

        try:
            g_playerEvents.onAvatarBecomePlayer()
            LOG_NOTE("[BATTLE] onAvatarBecomePlayer fired OK")
        except Exception as e:
            LOG_NOTE("[BATTLE] onAvatarBecomePlayer failed: %s" % e)

        def get_pos_on_ground(x, z):
            groundY = get_ground_height(self.spaceID, Math.Vector3(x, 0, z))
            if groundY <= 0.0:
                groundY = 10.0
            return Math.Vector3(x, groundY + 1.0, z)

        if playerCompDescr:
            playerDescr = vehicles.VehicleDescr(compactDescr=playerCompDescr)
        else:
            playerDescr = vehicles.VehicleDescr(typeName=playerVehicleName or "ussr:T-26")

        LOG_NOTE("[BATTLE] Player vehicle descriptor: %s" % playerDescr.type.name)

        _spawns_pre = _MAP_SPAWNS.get(arenaTypeName, None)
        if _spawns_pre and 1 in _spawns_pre and len(_spawns_pre[1]) > 0:
            _sp = _spawns_pre[1][0]
            playerPos = Math.Vector3(_sp[0], _sp[1], _sp[2])
            LOG_NOTE("[BATTLE] Player spawn from _MAP_SPAWNS: %s" % playerPos)
        else:
            playerPos, _ = _fallback_team_positions(get_pos_on_ground)
            LOG_NOTE("[BATTLE] No real base coords for '%s' yet, player using diagonal "
                      "fallback spawn (press F8 on your base's minimap circle to capture "
                      "the real point): %s" % (arenaTypeName, playerPos))
        LOG_NOTE("[BATTLE] Player spawn pos: %s" % playerPos)

        playerVehID = BigWorld.createEntity("Vehicle", self.spaceID, 0,
                                            playerPos, (0,0,0),
                                            {"publicInfo": {
                                                "health": playerDescr.maxHealth,
                                                "compDescr": playerDescr.makeCompactDescr(),
                                                "name": self.playerAvatar.name,
                                                "team": 1,
                                                "isAlive": True,
                                                "isAvatarReady": True
                                            }})
        LOG_NOTE("[BATTLE] Player Vehicle entity created: ID=%s" % playerVehID)
        self.playerAvatar.playerVehicleID = playerVehID
        self.playerAvatar.vehicleTypeDescriptor = playerDescr
        self.vehicles.append((playerVehID, playerDescr, True))

        self.arena.vehicles[playerVehID] = {
            'vehicleType': playerDescr,
            'name': self.playerAvatar.name,
            'team': 1,
            'isAlive': True,
            'isAvatarReady': True,
            'health': playerDescr.maxHealth,
            'frags': 0,
            'clanAbbrev': '',
            'prebattleID': 0,
            'vehicleID': playerVehID
        }

        botsPerTeam = botCount if botCount and botCount > 1 else BOTS_PER_TEAM
        allyBotsPerTeam = max(0, botsPerTeam - 1)

        spawns = _MAP_SPAWNS.get(arenaTypeName, None)
        if spawns:
            LOG_NOTE("[BATTLE] Using map spawns for '%s'" % arenaTypeName)
            base1 = spawns[1][1:]
            base2 = spawns[2]
        else:
            LOG_NOTE("[BATTLE] Map '%s' not in _MAP_SPAWNS yet - using diagonal fallback "
                      "(press F8 while standing on your base's minimap circle to log real "
                      "coordinates, see _capture_spawn_point)" % arenaTypeName)
            _fb1, _fb2 = _fallback_team_positions(get_pos_on_ground)
            base1 = [[_fb1.x, _fb1.y, _fb1.z]]
            base2 = [[_fb2.x, _fb2.y, _fb2.z]]

        positions1 = _generate_positions(base1, allyBotsPerTeam)
        positions2 = _generate_positions(base2, botsPerTeam)
        LOG_NOTE("[BATTLE] Team sizes: team1=%d (%d bots + player), team2=%d bots" % (
            allyBotsPerTeam + 1, allyBotsPerTeam, botsPerTeam))


        def _spawn_team_bots(team, positions):
            for i, pos in enumerate(positions):
                typeName, botDescr = _make_bot_descr(self._bot_pool, self._bot_descr_cache)
                if botDescr is None:
                    LOG_ERROR("[BATTLE] Could not create ANY bot descriptor for slot #%d (team %d)" % (i, team))
                    continue
                spawnPos = get_pos_on_ground(pos.x, pos.z)
                botName = "Bot_%s_%d" % (typeName.split(':')[-1], i + 1)
                try:
                    botID = BigWorld.createEntity("Vehicle", self.spaceID, 0,
                                                  spawnPos, (0, 0, 0),
                                                  {"publicInfo": {
                                                      "compDescr": botDescr.makeCompactDescr(),
                                                      "name": botName,
                                                      "team": team,
                                                      "isAlive": True,
                                                      "isAvatarReady": True
                                                  }})
                    self.vehicles.append((botID, botDescr, False))
                    self.arena.vehicles[botID] = {
                        'vehicleType': botDescr,
                        'name': botName,
                        'team': team,
                        'isAlive': True,
                        'isAvatarReady': True,
                        'health': botDescr.maxHealth,
                        'frags': 0,
                        'clanAbbrev': '',
                        'clanDBID': 0,
                        'accountDBID': 0,
                        'prebattleID': 0,
                        'vehicleID': botID
                    }
                    LOG_NOTE("[BATTLE] Bot spawned: %s team=%d pos=%s" % (typeName, team, spawnPos))

                    ang = random.uniform(0.0, 2.0 * math.pi)
                    wanderPoint = self._random_wander_point()
                    self._bot_ai.append({
                        'vehID': botID,
                        'team': team,
                        'descr': botDescr,
                        'pos': Math.Vector3(spawnPos),
                        'yaw': ang,
                        'wp': wanderPoint,
                        'engageID': None,
                        'matrix': None,
                        'servo': None,
                        'turret': BotTurretRotator(),
                        'turretLinked': False,
                    })
                except Exception as e:
                    LOG_ERROR("[BATTLE] Bot spawn failed '%s' #%d: %s" % (typeName, i, e))

        _spawn_team_bots(1, positions1)
        _spawn_team_bots(2, positions2)
        self._runtime_spawn_idx = {1: len(positions1), 2: len(positions2)}

        _base_pts_1 = spawns.get(1, base1) if spawns else base1
        _base_pts_2 = spawns.get(2, base2) if spawns else base2

        def _centroid_pos(pts):
            if not pts:
                return None
            cx = sum(p[0] for p in pts) / float(len(pts))
            cz = sum(p[2] for p in pts) / float(len(pts))
            return get_pos_on_ground(cx, cz)

        self._teamBaseCenter = {
            1: _centroid_pos(_base_pts_1),
            2: _centroid_pos(_base_pts_2),
        }
        self._captureState = {
            1: {'points': 0.0, 'attackers': 0, 'defenders': 0},
            2: {'points': 0.0, 'attackers': 0, 'defenders': 0},
        }
        self._battleResultShown = False
        LOG_NOTE("[CAPTURE] Base centers: team1=%s team2=%s (radius=%.1f)" % (
            self._teamBaseCenter[1], self._teamBaseCenter[2], CAPTURE_RADIUS))

        LOG_NOTE("[BATTLE] Total vehicles in scene: %d (bots with AI: %d)" % (len(self.vehicles), len(self._bot_ai)))

        def _add_destroyed_model(part):
            try:
                dm = part.get('models', {}).get('destroyed')
                if dm:
                    prereqs.append(dm)
            except Exception:
                pass

        prereqs = []
        for vehID, descr, _ in self.vehicles:
            prereqs.append(descr.chassis['models']['undamaged'])
            prereqs.append(descr.hull['models']['undamaged'])
            prereqs.append(descr.turret['models']['undamaged'])
            prereqs.append(descr.gun['models']['undamaged'])
            _add_destroyed_model(descr.chassis)
            _add_destroyed_model(descr.hull)
            _add_destroyed_model(descr.turret)
            _add_destroyed_model(descr.gun)
            prereqs += descr.prerequisites()
            for ht in descr.getHitTesters():
                if ht.bspModelName and not ht.isBspModelLoaded():
                    prereqs.append(ht.bspModelName)

        from Settings import g_instance as settings
        fakeModel = settings.scriptConfig.readString('fakeModel', 'objects/fake_model.model')
        prereqs.append(fakeModel)

        _seen = set()
        _deduped = []
        for _r in prereqs:
            if _r not in _seen:
                _seen.add(_r)
                _deduped.append(_r)
        prereqs = _deduped

        self._patch_startVisual()
        LOG_NOTE("[BATTLE] Loading %d resources (deduplicated)..." % len(prereqs))
        BigWorld.loadResourceListBG(prereqs, partial(self._onResourcesLoaded))


    def _get_pos_on_ground(self, x, z):
        groundY = get_ground_height(self.spaceID, Math.Vector3(x, 0, z))
        if groundY <= 0.0:
            groundY = 10.0
        return Math.Vector3(x, groundY + 1.0, z)

    def _random_wander_point(self):
        minX, minZ, maxX, maxZ = self._arenaBBox
        x = random.uniform(minX, maxX)
        z = random.uniform(minZ, maxZ)
        return self._get_pos_on_ground(x, z)

    def _capture_spawn_point(self):
        try:
            pos = getattr(self, '_cur_pos', None)
            if pos is None:
                veh = BigWorld.entity(self.playerAvatar.playerVehicleID)
                pos = veh.position if veh else None
            if pos is None:
                LOG_NOTE("[CAPTURE] Could not determine player position")
                return
            mapName = self._arenaTypeName or '?'
            line = "[%.2f, %.2f, %.2f]," % (pos.x, pos.y, pos.z)
            LOG_NOTE("[CAPTURE] map='%s' point=%s  -> paste into _MAP_SPAWNS['%s'][1] "
                      "if this is YOUR base, or [2] if this is the ENEMY base" %
                      (mapName, line, mapName))
            try:
                with open('spawn_points_captured.txt', 'a') as f:
                    f.write("%s  # map=%s (team 1=your base, team 2=enemy base)\n" % (line, mapName))
            except Exception as e:
                LOG_NOTE("[CAPTURE] Could not write spawn_points_captured.txt: %s" % e)
        except Exception as e:
            LOG_NOTE("[CAPTURE] _capture_spawn_point failed: %s" % e)

    def _get_base_spawn_pos(self, team, index):
        spawns = _MAP_SPAWNS.get(self._arenaTypeName, None)
        if spawns and team in spawns and len(spawns[team]) > 0:
            pts = spawns[team]
            p = pts[index % len(pts)]
            return self._get_pos_on_ground(p[0], p[2])

        playerVeh = BigWorld.entity(self.playerAvatar.playerVehicleID) if self.playerAvatar else None
        basePos = playerVeh.position if playerVeh else Math.Vector3(0, 0, 0)
        ang = random.uniform(0.0, 2.0 * math.pi)
        dist = 15.0 + 6.0 * (index % 10)
        if team == 2:
            dist += 40.0  
        x = basePos.x + math.sin(ang) * dist
        z = basePos.z + math.cos(ang) * dist
        return self._get_pos_on_ground(x, z)

    def spawn_bot_at_base(self, team):
        if not self.playerAvatar or self.spaceID is None:
            LOG_NOTE("[BATTLE] spawn_bot_at_base: battle not ready, ignored")
            return
        LOG_NOTE("[BATTLE] spawn_bot_at_base: requested team=%d" % team)

        typeName, botDescr = _make_bot_descr(self._bot_pool, self._bot_descr_cache)
        if botDescr is None:
            LOG_ERROR("[BATTLE] spawn_bot_at_base: could not create ANY bot descriptor")
            return

        idx = self._runtime_spawn_idx.get(team, 0)
        self._runtime_spawn_idx[team] = idx + 1
        spawnPos = self._get_base_spawn_pos(team, idx)
        botName = "Bot_%s_%d" % (typeName.split(':')[-1], idx + 1)

        try:
            botID = BigWorld.createEntity("Vehicle", self.spaceID, 0,
                                          spawnPos, (0, 0, 0),
                                          {"publicInfo": {
                                              "compDescr": botDescr.makeCompactDescr(),
                                              "name": botName,
                                              "team": team,
                                              "isAlive": True,
                                              "isAvatarReady": True
                                          }})
        except Exception as e:
            LOG_ERROR("[BATTLE] spawn_bot_at_base: createEntity failed: %s" % e)
            return

        self.vehicles.append((botID, botDescr, False))
        self.arena.vehicles[botID] = {
            'vehicleType': botDescr,
            'name': botName,
            'team': team,
            'isAlive': True,
            'isAvatarReady': True,
            'health': botDescr.maxHealth,
            'frags': 0,
            'clanAbbrev': '',
            'clanDBID': 0,
            'accountDBID': 0,
            'prebattleID': 0,
            'vehicleID': botID
        }
        LOG_NOTE("[BATTLE] spawn_bot_at_base: bot created %s team=%d pos=%s" % (typeName, team, spawnPos))

        ang = random.uniform(0.0, 2.0 * math.pi)
        wanderPoint = self._random_wander_point()
        self._bot_ai.append({
            'vehID': botID,
            'team': team,
            'descr': botDescr,
            'pos': Math.Vector3(spawnPos),
            'yaw': ang,
            'wp': wanderPoint,
            'engageID': None,
            'matrix': None,
            'servo': None,
            'turret': BotTurretRotator(),
            'turretLinked': False,
        })

        prereqs = [botDescr.chassis['models']['undamaged'],
                   botDescr.hull['models']['undamaged'],
                   botDescr.turret['models']['undamaged'],
                   botDescr.gun['models']['undamaged']]
        prereqs += botDescr.prerequisites()
        for ht in botDescr.getHitTesters():
            if ht.bspModelName and not ht.isBspModelLoaded():
                prereqs.append(ht.bspModelName)

        _seen = set()
        _deduped = []
        for _r in prereqs:
            if _r not in _seen:
                _seen.add(_r)
                _deduped.append(_r)
        prereqs = _deduped

        self._patch_startVisual()
        LOG_NOTE("[BATTLE] spawn_bot_at_base: loading %d resources for vehID=%d..." % (len(prereqs), botID))
        BigWorld.loadResourceListBG(prereqs, partial(self._onRuntimeBotResourcesLoaded, botID, botDescr))

    def _linkBotTurret(self, vehID, veh):
        """Подключает независимую матрицу поворота башни бота (BotTurretRotator)
        к его appearance, чтобы башня могла поворачиваться отдельно от корпуса."""
        try:
            botEntry = None
            for _b in self._bot_ai:
                if _b['vehID'] == vehID:
                    botEntry = _b
                    break
            if botEntry is None:
                return
            turretRot = botEntry.get('turret')
            if turretRot is None:
                turretRot = BotTurretRotator()
                botEntry['turret'] = turretRot
            veh.appearance.turretMatrix.target = turretRot.turretMatrix
            veh.appearance.gunMatrix.target = turretRot.gunMatrix
            botEntry['turretLinked'] = True
            LOG_NOTE("[BOT-AI] Turret matrix linked for bot vehID=%d" % vehID)
        except Exception as e:
            LOG_NOTE("[BOT-AI] _linkBotTurret failed for vehID=%d: %s" % (vehID, e))

    def _onRuntimeBotResourcesLoaded(self, vehID, descr, resourceRefs):
        failed = [k for k in resourceRefs.keys() if resourceRefs[k] is None]
        if failed:
            LOG_NOTE("[BATTLE] spawn_bot_at_base: %d resources failed to load for vehID=%d: %s" % (len(failed), vehID, failed[:5]))
        self._patch_vehicle()
        self._finalizeRuntimeBot(vehID, descr, resourceRefs)

    def _finalizeRuntimeBot(self, vehID, descr, resourceRefs, attempts=0):
        veh = BigWorld.entity(vehID)
        if veh is None or not veh.inWorld:
            if attempts > 100:
                LOG_ERROR("[BATTLE] spawn_bot_at_base: vehID=%d never entered world, giving up" % vehID)
                return
            BigWorld.callback(0.1, lambda: self._finalizeRuntimeBot(vehID, descr, resourceRefs, attempts + 1))
            return
        try:
            veh.isPlayer = False
            veh.isCrewActive = True
            veh.health = descr.maxHealth
            if getattr(veh, 'appearance', None):
                try:
                    veh.appearance.changeEngineMode((1, 0))
                except Exception as e:
                    LOG_NOTE("[BATTLE] spawn_bot_at_base: changeEngineMode failed vehID=%d: %s" % (vehID, e))
            veh.damageStickers = ()
            veh.publicStateModifiers = []
            try:
                descr.keepPrereqs(resourceRefs)
                veh._Vehicle__prereqs = resourceRefs
            except: pass

            m = Math.Matrix()
            m.setRotateYPR((0, 0, 0))
            m.translation = veh.position
            servo = BigWorld.Servo(m)
            if hasattr(veh, 'model'):
                veh.model.addMotor(servo)
            veh._offline_matrix = m
            veh._offline_servo = servo

            if not getattr(veh, 'isStarted', False):
                veh.startVisual()
                veh.isStarted = True

            if getattr(veh, 'appearance', None):
                self._linkBotTurret(vehID, veh)

            try:
                mm = getattr(self.playerAvatar, '_minimap', None)
                if mm:
                    mm.notifyVehicleStart(vehID)
            except Exception as e:
                LOG_NOTE("[BATTLE] spawn_bot_at_base: notifyVehicleStart failed vehID=%d: %s" % (vehID, e))
            try:
                if hasattr(self.arena, 'onVehicleAdded'):
                    self.arena.onVehicleAdded(vehID)
            except Exception as e:
                LOG_NOTE("[BATTLE] spawn_bot_at_base: arena.onVehicleAdded failed vehID=%d: %s" % (vehID, e))

            LOG_NOTE("[BATTLE] spawn_bot_at_base: vehID=%d fully spawned OK" % vehID)
        except Exception as e:
            LOG_ERROR("[BATTLE] spawn_bot_at_base: finalize failed vehID=%d: %s" % (vehID, e))

    def _onResourcesLoaded(self, resourceRefs):
        LOG_NOTE("[BATTLE] _onResourcesLoaded called, refs count=%d" % len(resourceRefs))
        failed = [k for k in resourceRefs.keys() if resourceRefs[k] is None]
        if failed:
            LOG_NOTE("[BATTLE] WARNING: %d resources failed to load: %s" % (len(failed), failed[:5]))
        else:
            LOG_NOTE("[BATTLE] All resources loaded OK")
        BigWorld.callback(0.1, lambda: self._finalizeInit(resourceRefs))

    def _applyAimPatches(self):
        try:
            from AvatarInputHandler import aims
            if not aims._g_aimState:
                aims.clearState()
            max_health = 200
            if self.playerAvatar.vehicleTypeDescriptor:
                max_health = self.playerAvatar.vehicleTypeDescriptor.maxHealth
            aims._g_aimState['health']['cur'] = max_health
            aims._g_aimState['health']['max'] = max_health
            aims._g_aimState['reload']['isReloading'] = False
            aims._g_aimState['reload']['duration'] = 0
            aims._g_aimState['reload']['startTime'] = None
            aims._g_aimState['ammoStock'] = 0
            original_setHealth = aims.Aim._setHealth
            def safe_setHealth(self, cur, max):
                if cur is None or max is None or max == 0:
                    return
                original_setHealth(self, cur, max)
            aims.Aim._setHealth = safe_setHealth
            LOG_NOTE("[BATTLE] _applyAimPatches OK, maxHealth=%d" % max_health)
        except Exception as e:
            LOG_NOTE("[BATTLE] aims patch skipped/failed: %s" % e)
    
    def _restore_matrix(self_battle):
        try:
            if hasattr(self_battle, '_offline_matrix') and hasattr(self_battle, '_cur_yaw'):
                self_battle._offline_matrix.setRotateYPR((
                    self_battle._cur_yaw,
                    getattr(self_battle, '_cur_pitch', 0.0),
                    getattr(self_battle, '_cur_roll', 0.0)
                ))
                self_battle._offline_matrix.translation = self_battle._cur_pos
        except:
            pass
    
    def _patch_control_modes(self):
        _self = self
        try:
            arcade_ctrl = self.playerAvatar.inputHandler._AvatarInputHandler__ctrls.get('arcade')
            if arcade_ctrl is None:
                LOG_ERROR("[BATTLE] _patch_control_modes: arcade control mode NOT FOUND!")
                return
            LOG_NOTE("[BATTLE] _patch_control_modes: arcade ctrl found: %s" % type(arcade_ctrl).__name__)
            arcade_ctrl._ArcadeControlMode__activateAlternateMode = lambda *a, **kw: None
            arcade_ctrl.onChangeControlMode = lambda *args, **kwargs: None
            if hasattr(arcade_ctrl, '_ArcadeControlMode__cam'):
                cam = arcade_ctrl._ArcadeControlMode__cam
                if hasattr(cam, '_ArcadeCamera__onChangeControlMode'):
                    cam._ArcadeCamera__onChangeControlMode = lambda *a, **kw: None
        except Exception as e:
            LOG_NOTE("[BATTLE] control_modes patch failed: %s" % e)
            return

        import CommandMapping
        original_handleKey = arcade_ctrl.handleKeyEvent
        def patched_handleKeyEvent(isDown, key, mods, event=None):
            cmdMap = CommandMapping.g_instance
            avatar = BigWorld.player()

            moved = False
            if cmdMap.isFired(CommandMapping.CMD_MOVE_FORWARD, key):
                avatar._moveForward = isDown
                moved = True
            if cmdMap.isFired(CommandMapping.CMD_MOVE_BACKWARD, key):
                avatar._moveBack = isDown
                moved = True
            if cmdMap.isFired(CommandMapping.CMD_ROTATE_LEFT, key):
                avatar._turnLeft = isDown
                moved = True
            if cmdMap.isFired(CommandMapping.CMD_ROTATE_RIGHT, key):
                avatar._turnRight = isDown
                moved = True

            if moved:
                avatar.currentMove = (1.0 if avatar._moveForward else 0.0) - (1.0 if avatar._moveBack else 0.0)
                avatar.currentTurn = (1.0 if avatar._turnRight else 0.0) - (1.0 if avatar._turnLeft else 0.0)
                LOG_NOTE("[BATTLE][INPUT] key=%d isDown=%s move=%.1f turn=%.1f" % (key, isDown, avatar.currentMove, avatar.currentTurn))
                return True
            if cmdMap.isFired(CommandMapping.CMD_CM_SHOOT, key) and isDown:
                avatar.shoot()
                return True

            if isDown and key == Keys.KEY_F6:
                LOG_NOTE("[BATTLE][INPUT] F6 pressed - spawn ALLY bot")
                BigWorld.callback(0.0, lambda: _self.spawn_bot_at_base(1))
                return True
            if isDown and key == Keys.KEY_F7:
                LOG_NOTE("[BATTLE][INPUT] F7 pressed - spawn ENEMY bot")
                BigWorld.callback(0.0, lambda: _self.spawn_bot_at_base(2))
                return True
            if isDown and key == Keys.KEY_F8:
                LOG_NOTE("[BATTLE][INPUT] F8 pressed - capture spawn point")
                BigWorld.callback(0.0, lambda: _self._capture_spawn_point())
                return True
            if isDown and key == Keys.KEY_F9:
                LOG_NOTE("[BATTLE][INPUT] F9 pressed - exit to hangar")
                BigWorld.callback(0.0, _self._finishBattle)
                return True
            if isDown and key == Keys.KEY_F2:
                LOG_NOTE("[BATTLE][INPUT] F2 pressed - stop simulation, exit to hangar")
                BigWorld.callback(0.0, _self._finishBattle)
                return True
            if cmdMap.isFired(CommandMapping.CMD_CM_ALTERNATE_MODE, key) and isDown:
                try:
                    aih = avatar.inputHandler
                    veh = BigWorld.entity(avatar.playerVehicleID)

                    shotPoint = None
                    try:
                        shotPoint = aih.getDesiredShotPoint()
                    except:
                        pass
                    
                    if shotPoint is None and veh:
                        import Math as _M
                        try:
                            turretMat = _M.Matrix(avatar.turretMatrix)
                            gunMat    = _M.Matrix(avatar.gunMatrix)
                            vehMat    = _M.Matrix(veh.matrix)
                            worldDir  = _M.Matrix()
                            worldDir.setIdentity()
                            worldDir.postMultiply(gunMat)
                            worldDir.postMultiply(turretMat)
                            worldDir.postMultiply(vehMat)
                            fwd = worldDir.applyVector(_M.Vector3(0, 0, 1))
                            shotPoint = veh.position + fwd * 300.0
                        except:
                            shotPoint = veh.position + _M.Vector3(0, 0, 300)
                    
                    if shotPoint is None:
                        return True

                    if veh and hasattr(_self, '_offline_matrix'):
                        try:
                            _self._offline_matrix.setRotateYPR((
                                getattr(_self, '_cur_yaw', 0.0),
                                0.0,
                                0.0
                            ))
                            _self._offline_matrix.translation = _self._cur_pos
                        except:
                            pass
                    
                    descr = avatar.vehicleTypeDescriptor
                    isATSPG = 'AT-SPG' in descr.type.tags if descr else False
                    
                    if veh and avatar._ownVehicleMProv.target is None:
                        avatar._ownVehicleMProv.target = veh.matrix

                    _saved_bind = avatar.bindToVehicle
                    def _offline_bind(doBind, vehicleID=None):
                        if doBind and veh:
                            avatar._ownVehicleMProv.target = veh.matrix
                    avatar.bindToVehicle = _offline_bind
                    try:
                        aih.onControlModeChanged('sniper',
                            preferredPos=shotPoint,
                            aimingMode=0,
                            saveZoom=False,
                            isATSPG=isATSPG)
                        LOG_NOTE("[BATTLE] Switched to sniper mode OK")
                    finally:
                        avatar.bindToVehicle = _saved_bind
                        BigWorld.callback(0.1, lambda: _self._restore_matrix())
                except Exception as e:
                    LOG_NOTE("[BATTLE] Sniper switch failed: %s" % e)
                return True
            return original_handleKey(isDown, key, mods, event)

        arcade_ctrl.handleKeyEvent = patched_handleKeyEvent
        LOG_NOTE("[BATTLE] Movement patched into ArcadeControlMode OK")
        original_mouse = arcade_ctrl.handleMouseEvent
        def patched_handleMouseEvent(dx, dy, dz):
            result = original_mouse(dx, dy, dz)
            avatar = BigWorld.player()
            gr = getattr(avatar, 'gunRotator', None)
            if gr:
                try:
                    cam = arcade_ctrl._ArcadeControlMode__cam
                    camDir = cam.camera.direction
                except:
                    pass
            return result
        arcade_ctrl.handleMouseEvent = patched_handleMouseEvent
        LOG_NOTE("[BATTLE] Mouse rotation patched into ArcadeControlMode OK")

        import AvatarInputHandler.control_modes as _cm
        _orig_sniper_enable = _cm.SniperControlMode.enable
        def _safe_sniper_enable(self_ctrl, **args):
            try:
                _orig_sniper_enable(self_ctrl, **args)
            except Exception as e:
                LOG_NOTE("[BATTLE] SniperControlMode.enable partial fail: %s" % e)
                self_ctrl._SniperControlMode__isEnabled = True
            try:
                self_ctrl._SniperControlMode__cam._SniperCamera__cam.spaceID = BigWorld.player().spaceID
            except Exception as e:
                LOG_NOTE("[BATTLE] Sniper camera spaceID sync failed: %s" % e)
        _cm.SniperControlMode.enable = _safe_sniper_enable

        _orig_sniper_mouse = _cm.SniperControlMode.handleMouseEvent
        def _safe_sniper_mouse(self_ctrl, dx, dy, dz):
            if not self_ctrl._SniperControlMode__isEnabled:
                return False
            return _orig_sniper_mouse(self_ctrl, dx, dy, dz)
        _cm.SniperControlMode.handleMouseEvent = _safe_sniper_mouse

        _orig_sniper_key = _cm.SniperControlMode.handleKeyEvent
        def _safe_sniper_key(self_ctrl, isDown, key, mods, event=None):
            if not self_ctrl._SniperControlMode__isEnabled:
                return False

            cmdMap = CommandMapping.g_instance
            avatar = BigWorld.player()
            moved = False
            if cmdMap.isFired(CommandMapping.CMD_MOVE_FORWARD, key):
                avatar._moveForward = isDown
                moved = True
            if cmdMap.isFired(CommandMapping.CMD_MOVE_BACKWARD, key):
                avatar._moveBack = isDown
                moved = True
            if cmdMap.isFired(CommandMapping.CMD_ROTATE_LEFT, key):
                avatar._turnLeft = isDown
                moved = True
            if cmdMap.isFired(CommandMapping.CMD_ROTATE_RIGHT, key):
                avatar._turnRight = isDown
                moved = True
            if moved:
                avatar.currentMove = (1.0 if avatar._moveForward else 0.0) - (1.0 if avatar._moveBack else 0.0)
                avatar.currentTurn = (1.0 if avatar._turnRight else 0.0) - (1.0 if avatar._turnLeft else 0.0)
                return True

            return _orig_sniper_key(self_ctrl, isDown, key, mods, event)
        _cm.SniperControlMode.handleKeyEvent = _safe_sniper_key

        _orig_sniper_marker = _cm.SniperControlMode.showGunMarker
        def _safe_sniper_marker(self_ctrl, flag):
            if not self_ctrl._SniperControlMode__isEnabled:
                return
            return _orig_sniper_marker(self_ctrl, flag)
        _cm.SniperControlMode.showGunMarker = _safe_sniper_marker

        LOG_NOTE("[BATTLE] SniperControlMode asserts patched OK")

        from VehicleGunRotator import VehicleGunRotator as _VGR
        def _safe_updateShotPoint(self_gr, shotPoint):
            self_gr._VehicleGunRotator__prevSentShotPoint = shotPoint
        _VGR._VehicleGunRotator__updateShotPointOnServer = _safe_updateShotPoint
        LOG_NOTE("[BATTLE] VehicleGunRotator.__updateShotPointOnServer patched OK")
        _orig_onTick = _VGR._VehicleGunRotator__onTick
        def _safe_onTick(self_gr):
            try: _orig_onTick(self_gr)
            except: pass
        _VGR._VehicleGunRotator__onTick = _safe_onTick

    def _patch_decalmap(self):
        try:
            if DecalMap.g_instance:
                DecalMap.g_instance.getIndex = lambda name: 0
            BigWorld.wg_addDecal = lambda *args, **kwargs: 0
            if hasattr(BigWorld, 'WGVehicleFashion'):
                BigWorld.WGVehicleFashion.setTrackTraces = lambda *a, **kw: None
        except Exception as e:
            LOG_NOTE("[BATTLE] DecalMap patch failed: %s" % e)

        try:
            if hasattr(BigWorld, 'WGStickerModel'):
                BigWorld.WGStickerModel.addSticker = lambda self, layer, texCoords, model, start, end, sizes, up: 0
            if hasattr(BigWorld, 'WGVehicleFashion'):
                BigWorld.WGVehicleFashion.setTrackTraces = lambda self, group, textureIndex, centerOffset, size: None
            if hasattr(BigWorld, 'wg_addDecal'):
                BigWorld.wg_addDecal = lambda *args, **kwargs: 0
            try:
                from helpers import bound_effects
                if hasattr(bound_effects.ModelBoundEffects, 'addNew'):
                    original_addNew = bound_effects.ModelBoundEffects.addNew
                    def safe_addNew(self, mat, effects, stages, entity=None):
                        try:
                            return original_addNew(self, mat, effects, stages, entity)
                        except Exception as e:
                            LOG_NOTE("[BATTLE] bound_effects.addNew failed: %s" % e)
                    bound_effects.ModelBoundEffects.addNew = safe_addNew
            except:
                pass
            LOG_NOTE("[BATTLE] Disabled decals and effects OK")
        except Exception as e:
            LOG_NOTE("[BATTLE] Failed to disable decals: %s" % e)
    def _patch_gui(self):
        try:
            from gui.Scaleform import BattleLoading as _BLMod

            if not getattr(_BLMod.BattleLoading, '_patched_offline', False):

                orig_populateUI = _BLMod.BattleLoading.populateUI
                def _safe_populateUI(self_bl, proxy):
                    arena = getattr(BigWorld.player(), 'arena', None)
                    if arena:
                        for vData in arena.vehicles.values():
                            vData.setdefault('prebattleID', 0)
                            vData.setdefault('accountDBID', 0)
                            vData.setdefault('clanDBID', 0)
                            vData.setdefault('clanAbbrev', '')
                    try:
                        orig_populateUI(self_bl, proxy)
                    except Exception as e:
                        LOG_NOTE("[BATTLE] BattleLoading.populateUI failed: %s" % e)
                _BLMod.BattleLoading.populateUI = _safe_populateUI

                orig_BL_up = _BLMod.BattleLoading._BattleLoading__updatePlayers
                def _safe_BL_up(self_bl, *args):
                    arena = getattr(self_bl, '_BattleLoading__arena', None)
                    if arena:
                        for vData in arena.vehicles.values():
                            vData.setdefault('prebattleID', 0)
                            vData.setdefault('accountDBID', 0)
                            vData.setdefault('clanDBID', 0)
                            vData.setdefault('clanAbbrev', '')
                    try:
                        orig_BL_up(self_bl, *args)
                    except Exception as e:
                        LOG_NOTE("[BATTLE] BattleLoading.__updatePlayers failed: %s" % e)
                _BLMod.BattleLoading._BattleLoading__updatePlayers = _safe_BL_up

                _BLMod.BattleLoading._patched_offline = True
                LOG_NOTE("[BATTLE] BattleLoading patched OK")
        except Exception as e:
            LOG_NOTE("[BATTLE] BattleLoading patch failed: %s" % e)

        try:
            from gui.Scaleform import Battle as _BattleMod
            if not getattr(_BattleMod.Battle, '_patched_offline', False):
                orig_Battle_up = _BattleMod.Battle._Battle__updatePlayers
                def _safe_Battle_up(self_b, *args):
                    arena = getattr(self_b, '_Battle__arena', None)
                    if arena:
                        for vData in arena.vehicles.values():
                            vData.setdefault('prebattleID', 0)
                            vData.setdefault('accountDBID', 0)
                            vData.setdefault('clanDBID', 0)
                            vData.setdefault('clanAbbrev', '')
                    try:
                        orig_Battle_up(self_b, *args)
                    except Exception as e:
                        LOG_NOTE("[BATTLE] Battle.__updatePlayers failed: %s" % e)
                _BattleMod.Battle._Battle__updatePlayers = _safe_Battle_up
                _BattleMod.Battle._patched_offline = True
                LOG_NOTE("[BATTLE] Battle.__updatePlayers patched OK")
        except Exception as e:
            LOG_NOTE("[BATTLE] Battle patch failed: %s" % e)
    def _patch_startVisual(self):
        import VehicleAppearance as VA
        if hasattr(VA.VehicleAppearance, '_patched_for_offline'):
            LOG_NOTE("[BATTLE] _patch_startVisual: already patched, skipping")
            return
        _ROOT_NODE_NAME = 'V'
        def _offline_setupVehicleFashion(fashion, vehicle, isCrashedTrack=False):
            vDesc = vehicle.typeDescriptor
            tracesCfg = vDesc.chassis['traces']
            tracksCfg = vDesc.chassis['tracks']
            wheelsCfg = vDesc.chassis['wheels']
            swingingCfg = vDesc.hull['swinging']
            fashion.movementInfo = vehicle.filter.movementInfo
            fashion.maxMovement = vDesc.physics['speedLimits'][0]
            fashion.setPitchSwinging(_ROOT_NODE_NAME, *swingingCfg['pitchParams'])
            fashion.setRollSwinging(_ROOT_NODE_NAME, *swingingCfg['rollParams'])
            fashion.setShotSwinging(_ROOT_NODE_NAME, swingingCfg['sensitivityToImpulse'])
            fashion.setLods(tracesCfg['lodDist'], wheelsCfg['lodDist'], tracksCfg['lodDist'], swingingCfg['lodDist'])
            fashion.setTracks(tracksCfg['leftMaterial'], tracksCfg['rightMaterial'], tracksCfg['textureScale'])
            if isCrashedTrack:
                return
            for group in wheelsCfg['groups']:
                nodes = [ '%s%d' % (group[1], i) for i in range(group[3], group[3] + group[2]) ]
                fashion.addWheelGroup(group[0], group[4], nodes)
            for wheel in wheelsCfg['wheels']:
                fashion.addWheel(wheel[0], wheel[2], wheel[1])
            try:
                BigWorld.wg_addDecalGroup(tracesCfg['decalGroup'], 30.0, 1000)
            except Exception as e:
                LOG_NOTE("[BATTLE] wg_addDecalGroup failed for %s: %s" % (tracesCfg['decalGroup'], e))
            try:
                from helpers.DecalMap import DecalMap as _DM
                _traceTexIdx = _DM.g_instance.getIndex(tracesCfg['decalTexture']) if _DM.g_instance else 0
                if _traceTexIdx is None or _traceTexIdx < 0:
                    _traceTexIdx = 0
            except Exception:
                _traceTexIdx = 0
            try:
                fashion.setTrackTraces(tracesCfg['decalGroup'], _traceTexIdx, tracesCfg['centerOffset'], tracesCfg['size'])
            except Exception as e:
                LOG_NOTE("[BATTLE] setTrackTraces still failed for %s (non-fatal, rest of fashion already applied): %s" % (getattr(vehicle, 'id', '?'), e))
            LOG_NOTE("[BATTLE] _offline_setupVehicleFashion OK (wheels+tracks+movementInfo+swinging set, traces skipped) for %s" % getattr(vehicle, 'id', '?'))
        VA._setupVehicleFashion = _offline_setupVehicleFashion

        original_updateMovement = VA.VehicleAppearance._VehicleAppearance__updateMovementSounds
        def safe_updateMovement(self_va):
            try:
                return original_updateMovement(self_va)
            except Exception as e:
                pass
        VA.VehicleAppearance._VehicleAppearance__updateMovementSounds = safe_updateMovement

        def _offline_getDamageModelsState(self_va, h):
            try:
                vehicle = getattr(self_va, '_VehicleAppearance__vehicle', None)
                vid = getattr(vehicle, 'id', None)
                if vid is not None and vid in _DESTROYED_VEH_IDS:
                    return 'destroyed'
            except Exception:
                pass
            return 'undamaged'
        VA.VehicleAppearance._VehicleAppearance__getDamageModelsState = _offline_getDamageModelsState

        original_setup = VA.VehicleAppearance._VehicleAppearance__setupModels
        def safe_setupModels(self_va):
            self_va._VehicleAppearance__curDamageState = 'undamaged'
            try:
                original_setup(self_va)
            except Exception as e:
                err = str(e)
                if 'wg_fashion' in err or 'wg_gunRecoil' in err or 'setTrackTraces' in err or 'groupName' in err or 'trace' in err:
                    LOG_NOTE("[BATTLE] safe_setupModels caught known error: %s" % err)
                    try:
                        m = self_va._VehicleAppearance__vehicle.model
                        if not hasattr(m, 'wg_fashion'):
                            m.wg_fashion = type('FakeFashion', (), {
                                'setTrackTraces': lambda *a, **kw: None,
                                'receiveShotImpulse': lambda *a, **kw: None,
                                'hideTracks': lambda *a, **kw: None,
                                'movementInfo': None,
                                'staticPitchSwingForce': 0,
                                'disableSwinging': False
                            })()
                        if not hasattr(m, 'wg_gunRecoil'):
                            m.wg_gunRecoil = None
                    except: pass
                else:
                    vid = getattr(getattr(self_va, '_VehicleAppearance__vehicle', None), 'id', None)
                    if vid in _DESTROYED_VEH_IDS:
                        LOG_NOTE("[BATTLE] safe_setupModels: destroyed-model rebuild failed for %s, falling back: %s" % (vid, err))
                        _DESTROYED_VEH_IDS.discard(vid)
                        try:
                            original_setup(self_va)
                        except Exception:
                            pass
                    else:
                        LOG_ERROR("[BATTLE] safe_setupModels UNEXPECTED error: %s" % err)
                        raise
        VA.VehicleAppearance._VehicleAppearance__setupModels = safe_setupModels

        original_start = VA.VehicleAppearance.start
        def safe_start(self_va, vehicle, prereqs=None):
            LOG_NOTE("[BATTLE][VA] VehicleAppearance.start called for vehID=%s" % getattr(vehicle, 'id', '?'))
            from helpers.DecalMap import DecalMap as DM
            old_getIndex = DM.getIndex
            def _safe_getIndex(self, name):
                try:
                    idx = old_getIndex(self, name)
                    return idx if idx is not None and idx >= 0 else 0
                except Exception:
                    return 0
            DM.getIndex = _safe_getIndex
            old_addDecal = getattr(BigWorld, 'wg_addDecal', None)
            def _safe_addDecal(*a, **kw):
                try:
                    return old_addDecal(*a, **kw)
                except Exception:
                    return 0
            if old_addDecal:
                BigWorld.wg_addDecal = _safe_addDecal
            self_va._VehicleAppearance__curDamageState = 'undamaged'
            try:
                result = original_start(self_va, vehicle, prereqs)
                LOG_NOTE("[BATTLE][VA] VehicleAppearance.start OK for vehID=%s" % getattr(vehicle, 'id', '?'))
                return result
            except Exception as e:
                err = str(e)
                if 'setTrackTraces' in err or 'groupName' in err or 'trace' in err or 'wg_fashion' in err:
                    LOG_NOTE("[BATTLE][VA] safe_start caught known error: %s" % err)
                else:
                    LOG_ERROR("[BATTLE][VA] safe_start UNEXPECTED error: %s" % err)
                    raise
            finally:
                DM.getIndex = old_getIndex
                if old_addDecal:
                    BigWorld.wg_addDecal = old_addDecal

        VA.VehicleAppearance.start = safe_start
        VA.VehicleAppearance._patched_for_offline = True
        LOG_NOTE("[BATTLE] _patch_startVisual: VA.VehicleAppearance patched OK")
        VA.VehicleAppearance._VehicleAppearance__destroyTrackDamageSounds = lambda self: setattr(self, '_VehicleAppearance__trackSounds', [None, None])
        LOG_NOTE("[BATTLE] __setupTrackDamageSounds patched to no-op OK")

    def _updateBattleUI(self):
        if self.battleWindow:
            try:
                if hasattr(self.battleWindow, 'damagePanel'):
                    vdata = self.arena.vehicles.get(self.playerAvatar.playerVehicleID)
                    veh = BigWorld.entity(self.playerAvatar.playerVehicleID)
                    if veh:
                        curHealth = vdata.get('health', veh.health) if vdata is not None else veh.health
                        self.battleWindow.damagePanel.updateHealth(curHealth)
                if hasattr(self.battleWindow, '_Battle__updatePlayers'):
                    self.battleWindow._Battle__updatePlayers = lambda *args: None
            except Exception as e:
                LOG_NOTE("[BATTLE] UI update error: %s" % e)
        if self.battleWindow:
            BigWorld.callback(0.5, self._updateBattleUI)

    def _fixTankIndicator(self):
        if not self.battleWindow or not self.playerAvatar:
            return
        try:
            descr = self.playerAvatar.vehicleTypeDescriptor
            vtype = 'Tank'
            if descr is not None:
                vTags = descr.type.tags
                if 'SPG' in vTags:
                    vtype = 'SPG'
                elif 'AT-SPG' in vTags:
                    vtype = 'AT-SPG'
            self.battleWindow.call('battle.tankIndicator.setType', [vtype])
            LOG_NOTE("[BATTLE] Tank indicator set to %s OK" % vtype)
        except Exception as e:
            LOG_NOTE("[BATTLE] Failed to fix tank indicator: %s" % e)

        aim = getattr(self.playerAvatar.inputHandler, 'aim', None) if self.playerAvatar.inputHandler else None
        reattached = False
        if aim is not None:
            try:
                aim.attachTankIndicator(weakref.ref(self.battleWindow))
                reattached = True
                LOG_NOTE("[BATTLE] tankIndicator re-attached via aim.attachTankIndicator (hull+turret+camera sync) OK")
            except Exception as e:
                LOG_NOTE("[BATTLE] aim.attachTankIndicator re-attach failed, falling back to manual matrices: %s" % e)

        if not reattached:
            try:
                veh = BigWorld.entity(self.playerAvatar.playerVehicleID)
                if veh and getattr(veh, 'appearance', None):
                    mc = getattr(self.battleWindow.component, 'tankIndicator', None)
                    if mc:
                        mc.wg_hullMatProv   = self.playerAvatar.getOwnVehicleMatrix()
                        mc.wg_turretMatProv = veh.appearance.turretMatrix
                        LOG_NOTE("[BATTLE] tankIndicator matrices re-linked (fallback, no camera sync) OK")
            except Exception as e:
                LOG_NOTE("[BATTLE] tankIndicator matrices re-link failed: %s" % e)

    def _setPrebattleTimer(self, duration):
        now = BigWorld.time()
        self._prebattleStartTime = now
        _prebattle = getattr(constants, 'ARENA_PERIOD_PREBATTLE', getattr(getattr(constants, 'ARENA_PERIOD', None), 'PREBATTLE', 1))
        period_data = (_prebattle, now + duration, duration, None)
        _upd_period = getattr(constants, 'ARENA_UPDATE_PERIOD',
                      getattr(constants.ARENA_UPDATE, 'PERIOD', 3))
        self.arena.update(_upd_period, cPickle.dumps(period_data))
        LOG_NOTE("[BATTLE] Pre-battle timer set to %.1f seconds" % duration)

    def _startMinimap(self):
        try:
            from gui.Minimap import Minimap
            mm = Minimap()
            prereqs = mm.prerequisites()

            def _onReady(resourceRefs):
                try:
                    mm.start()
                    self.playerAvatar._minimap = mm
                    LOG_NOTE("[BATTLE] Minimap started OK")
                    for vehID, descr, isPlayer in self.vehicles:
                        if not isPlayer:
                            try:
                                mm.notifyVehicleStart(vehID)
                            except Exception as e:
                                LOG_NOTE("[BATTLE] notifyVehicleStart(%d) failed: %s" % (vehID, e))
                            try:
                                if hasattr(self.arena, 'onVehicleAdded'):
                                    self.arena.onVehicleAdded(vehID)
                            except Exception as e:
                                LOG_NOTE("[BATTLE] arena.onVehicleAdded(%d) dispatch failed: %s" % (vehID, e))
                    LOG_NOTE("[BATTLE] Minimap: notifyVehicleStart + onVehicleAdded sent for %d bots" % (len(self.vehicles) - 1))
                except Exception as e:
                    LOG_NOTE("[BATTLE] Minimap.start() failed: %s" % e)

            if prereqs:
                BigWorld.loadResourceListBG(prereqs, _onReady)
            else:
                _onReady(None)

        except Exception as e:
            LOG_NOTE("[BATTLE] _startMinimap error: %s" % e)
    
    def _setupTankIndicator(self):
        if self._stopped:
            return
        try:
            bw = g_windowsManager.battleWindow
            if bw is None:
                BigWorld.callback(0.5, self._setupTankIndicator)
                return

            aim = getattr(self.playerAvatar.inputHandler, 'aim', None)
            if aim is None:
                BigWorld.callback(0.5, self._setupTankIndicator)
                return

            try:
                aim.attachCruiseCtrl(weakref.ref(bw))
                LOG_NOTE("[BATTLE] cruiseCtrl attached OK")
            except Exception as e:
                LOG_NOTE("[BATTLE] cruiseCtrl attach failed: %s" % e)

            try:
                descr = self.playerAvatar.vehicleTypeDescriptor
                vTags = descr.type.tags
                if 'SPG' in vTags:
                    vtype = 'SPG'
                elif 'AT-SPG' in vTags:
                    vtype = 'AT-SPG'
                else:
                    vtype = 'Tank'
                bw.call('battle.tankIndicator.setType', [vtype])
                LOG_NOTE("[BATTLE] tankIndicator type set: %s" % vtype)
            except Exception as e:
                LOG_NOTE("[BATTLE] tankIndicator setType failed: %s" % e)

            reattached = False
            try:
                aim.attachTankIndicator(weakref.ref(bw))
                reattached = True
                LOG_NOTE("[BATTLE] tankIndicator attached (hull+turret+camera sync) OK")
            except Exception as e:
                LOG_NOTE("[BATTLE] tankIndicator attach failed, falling back to manual matrices: %s" % e)

            if not reattached:
                try:
                    veh = BigWorld.entity(self.playerAvatar.playerVehicleID)
                    if veh and getattr(veh, 'appearance', None):
                        mc = getattr(bw.component, 'tankIndicator', None)
                        if mc:
                            mc.wg_hullMatProv   = self.playerAvatar.getOwnVehicleMatrix()
                            mc.wg_turretMatProv = veh.appearance.turretMatrix
                            LOG_NOTE("[BATTLE] tankIndicator matrices linked (fallback, no camera sync) OK")
                except Exception as e:
                    LOG_NOTE("[BATTLE] tankIndicator matrices failed: %s" % e)

        except Exception as e:
            LOG_NOTE("[BATTLE] _setupTankIndicator failed: %s" % e)
    
    def _setupAmmoPanel(self):
        if self._stopped:
            return
        try:
            bw = g_windowsManager.battleWindow
            if bw is None:
                BigWorld.callback(0.5, self._setupAmmoPanel)
                return
            self.battleWindow = bw

            cp = getattr(bw, 'consumablesPanel', None)
            if cp is None:
                LOG_NOTE("[BATTLE] AmmoPanel: consumablesPanel not ready, retrying...")
                BigWorld.callback(0.5, self._setupAmmoPanel)
                return

            descr = self.playerAvatar.vehicleTypeDescriptor
            if not descr:
                LOG_NOTE("[BATTLE] AmmoPanel: vehicleTypeDescriptor is None")
                return

            shots = descr.gun['shots']
            if not shots:
                LOG_NOTE("[BATTLE] AmmoPanel: no shots in gun descriptor")
                return

            shell_counts = {}
            try:
                from CurrentVehicle import g_currentVehicle
                veh = g_currentVehicle.vehicle
                if veh:
                    shells = list(getattr(veh, 'shells', []) or [])
                    for j in range(0, len(shells) - 1, 2):
                        shell_counts[shells[j]] = shells[j + 1]
            except Exception as e:
                LOG_NOTE("[BATTLE] AmmoPanel: shell_counts failed: %s" % e)

            ammoList = []
            for idx, shot in enumerate(shots):
                shellDescr = shot['shell']
                piercingPower = shot['piercingPower']
                shell_cd = shellDescr.get('compactDescr', 0)
                count = shell_counts.get(shell_cd, 0)
                if count == 0:
                    try:
                        default_shells = vehicles.getDefaultAmmoForGun(descr.gun)
                        for di in range(0, len(default_shells) - 1, 2):
                            if default_shells[di] == shell_cd:
                                count = default_shells[di + 1]
                                break
                    except:
                        count = 30
                ammoList.append([shell_cd, count])
                try:
                    cp.addShellSlot(idx, count, shellDescr, piercingPower)
                    LOG_NOTE("[BATTLE] AmmoPanel: shell idx=%d kind=%s count=%d OK" % (
                        idx, shellDescr.get('kind', '?'), count))
                except Exception as e:
                    LOG_NOTE("[BATTLE] AmmoPanel: addShellSlot idx=%d failed: %s" % (idx, e))

            self.playerAvatar._ammo = ammoList

            try:
                cp.setCurrentShell(0)
                cp.setNextShell(0)
            except Exception as e:
                LOG_NOTE("[BATTLE] AmmoPanel: setCurrentShell failed: %s" % e)

            self.playerAvatar._currentShellIndex = 0
            LOG_NOTE("[BATTLE] AmmoPanel: %d shell types loaded" % len(shots))

            from items.vehicles import NUM_EQUIPMENT_SLOTS
            eq_compacts = [0, 0, 0]
            try:
                from CurrentVehicle import g_currentVehicle as _cv
                hangar_veh = _cv.vehicle
                if hangar_veh:
                    eq_compacts = list(getattr(hangar_veh, 'equipments', [0, 0, 0]) or [0, 0, 0])
                    while len(eq_compacts) < NUM_EQUIPMENT_SLOTS:
                        eq_compacts.append(0)
            except Exception as e:
                LOG_NOTE("[BATTLE] AmmoPanel: equipments read failed: %s" % e)

            _eqSlotBase = len(shots)
            self.playerAvatar._equipSlotBase = _eqSlotBase
            for eq_idx in range(NUM_EQUIPMENT_SLOTS):
                _slot = _eqSlotBase + eq_idx
                cd = eq_compacts[eq_idx] if eq_idx < len(eq_compacts) else 0
                if cd and cd != 0:
                    try:
                        from items.vehicles import getDictDescr
                        eq_descr = getDictDescr(cd)
                        cp.addEquipmentSlot(_slot, 1, eq_descr)
                        LOG_NOTE("[BATTLE] AmmoPanel: equipment slot %d = %s OK" % (
                            _slot, eq_descr.get('name', cd)))
                    except Exception as e:
                        LOG_NOTE("[BATTLE] AmmoPanel: equipment slot %d failed: %s, adding empty" % (_slot, e))
                        cp.addEmptyEquipmentSlot(_slot)
                else:
                    cp.addEmptyEquipmentSlot(_slot)
                    LOG_NOTE("[BATTLE] AmmoPanel: equipment slot %d empty" % _slot)

        except Exception as e:
            LOG_NOTE("[BATTLE] _setupAmmoPanel failed: %s" % e)

#################### тут танк ЕДИТ ################
#################### тут танк ЕДИТ ################
#################### тут танк ЕДИТ ################

    # ---------------- Обводка танка под прицельным маркером ----------------

    def _getAim(self):
        ih = getattr(self.playerAvatar, 'inputHandler', None)
        if ih is None:
            if not getattr(self, '_marker_dbg_noih_logged', False):
                LOG_NOTE("[BATTLE][MARKER][DBG] playerAvatar.inputHandler is None")
                self._marker_dbg_noih_logged = True
            return None
        try:
            aim = ih.aim
        except Exception as e:
            if not getattr(self, '_marker_dbg_aimexc_logged', False):
                LOG_NOTE("[BATTLE][MARKER][DBG] inputHandler.aim property raised: %s" % e)
                self._marker_dbg_aimexc_logged = True
            return None
        if aim is None and not getattr(self, '_marker_dbg_noaim_logged', False):
            LOG_NOTE("[BATTLE][MARKER][DBG] inputHandler.aim resolved to None")
            self._marker_dbg_noaim_logged = True
        elif aim is not None and not getattr(self, '_marker_dbg_aimok_logged', False):
            LOG_NOTE("[BATTLE][MARKER][DBG] inputHandler.aim OK, type=%s" % type(aim))
            self._marker_dbg_aimok_logged = True
        return aim

    def _hideMarkerFrame(self):
        """Совместимость: раньше прятала ручную GUI.Colour-рамку. Теперь
        снимает цель и с нативного прицела (aim.clearTarget), и с
        нативной подсветки силуэта (wgDelEdgeDetectEntity) - см. ниже."""
        if self._marker_target_vehID is not None:
            aim = self._getAim()
            if aim is not None:
                try:
                    aim.clearTarget()
                except Exception as e:
                    LOG_NOTE("[BATTLE][MARKER] aim.clearTarget() failed: %s" % e)
            prevVeh = BigWorld.entity(self._marker_target_vehID)
            if prevVeh is not None:
                try:
                    BigWorld.wgDelEdgeDetectEntity(prevVeh)
                except Exception as e:
                    LOG_NOTE("[BATTLE][MARKER] wgDelEdgeDetectEntity() failed: %s" % e)
            self._marker_target_vehID = None

    def _targetMarkerTick(self):
        if not self.battleWindow:
            return
        if self.playerAvatar:
            try:
                self._targetMarkerTickImpl()
            except Exception as e:
                LOG_NOTE("[BATTLE][MARKER] _targetMarkerTick failed: %s" % e)
        BigWorld.callback(0.1, self._targetMarkerTick)

    def _targetMarkerTickImpl(self):
        cam = BigWorld.camera()
        aim = self._getAim()
        if cam is None:
            self._hideMarkerFrame()
            return

        playerVehID = self.playerAvatar.playerVehicleID
        pdata = self.arena.vehicles.get(playerVehID) if (self.arena and playerVehID is not None) else None
        if pdata is None:
            self._hideMarkerFrame()
            return
        playerTeam = getattr(self.playerAvatar, 'team', None)
        if playerTeam is None:
            playerTeam = pdata.get('team')

        camMatrix = Math.Matrix(cam.matrix)
        camPos = camMatrix.translation
        camDir = camMatrix.applyVector(Math.Vector3(0, 0, 1))
        camDir.normalise()

        MAX_DIST = 500.0
        ANGLE_COS_THRESHOLD = 0.997   
                                       
                                       

        bestVehID = None
        bestDot = ANGLE_COS_THRESHOLD

        for vehID, descr, isPlayer in self.vehicles:
            if isPlayer or vehID == playerVehID:
                continue
            vdata = self.arena.vehicles.get(vehID)
            if vdata is None or not vdata.get('isAlive', True):
                continue
            veh = BigWorld.entity(vehID)
            if veh is None or not getattr(veh, 'isStarted', False):
                continue
            try:
                vehPos = Math.Vector3(veh.position)
            except Exception:
                continue
            vehPos.y += 1.0

            toVec = vehPos - camPos
            dist = toVec.length
            if dist < 0.05 or dist > MAX_DIST:
                continue
            toDir = Math.Vector3(toVec)
            toDir.normalise()
            dot = camDir.dot(toDir)
            if dot > bestDot:
                bestDot = dot
                bestVehID = vehID

        if bestVehID == self._marker_target_vehID:
            return

        if bestVehID is None:
            LOG_NOTE("[BATTLE][MARKER][DBG] target lost (was %s)" % self._marker_target_vehID)
            self._hideMarkerFrame()
            return

        veh = BigWorld.entity(bestVehID)
        if veh is None or not hasattr(veh, 'publicInfo'):
            LOG_NOTE("[BATTLE][MARKER][DBG] candidate %s has no publicInfo (veh=%s)" % (bestVehID, veh))
            self._hideMarkerFrame()
            return

        if self._marker_target_vehID is not None:
            prevVeh = BigWorld.entity(self._marker_target_vehID)
            if prevVeh is not None:
                try:
                    BigWorld.wgDelEdgeDetectEntity(prevVeh)
                except Exception as e:
                    LOG_NOTE("[BATTLE][MARKER] wgDelEdgeDetectEntity() (prev) failed: %s" % e)

        if aim is not None:
            try:
                aim.setTarget(veh)
            except Exception as e:
                LOG_NOTE("[BATTLE][MARKER] aim.setTarget() failed: %s" % e)

        try:
            if veh.isAlive():
                edgeType = 2 if playerTeam == veh.publicInfo.get('team') else 1
                BigWorld.wgAddEdgeDetectEntity(veh, edgeType)
                LOG_NOTE("[BATTLE][MARKER][DBG] wgAddEdgeDetectEntity(%s, %d) OK, name=%s" %
                         (bestVehID, edgeType, veh.publicInfo.get('name')))
        except Exception as e:
            LOG_NOTE("[BATTLE][MARKER] wgAddEdgeDetectEntity() failed: %s" % e)

        self._marker_target_vehID = bestVehID


    def __movementTick(self):
        if self._stopped:
            return
        if not self.playerAvatar or not self.playerAvatar.isOnArena:
            BigWorld.callback(0.05, self.__movementTick)
            return

        veh = BigWorld.entity(self.playerAvatar.playerVehicleID)
        if veh is None or not getattr(veh, 'isStarted', False):
            BigWorld.callback(0.05, self.__movementTick)
            return

        flt = getattr(veh, 'filter', None)
        if flt is None:
            BigWorld.callback(0.05, self.__movementTick)
            return

        move = self.playerAvatar.currentMove
        turn = self.playerAvatar.currentTurn
        if not self._battleStarted:
            move = 0
            turn = 0
        descr = self.playerAvatar.vehicleTypeDescriptor
        if descr is None:
            BigWorld.callback(0.05, self.__movementTick)
            return

        now = BigWorld.time()
        if not hasattr(self, '_last_tick_time'):
            self._last_tick_time = now
        dt = now - self._last_tick_time
        if dt <= 0.0 or dt > 0.2: 
            dt = 0.05
        self._last_tick_time = now

        fwdLimit = descr.physics['speedLimits'][0]
        bwdLimit = descr.physics['speedLimits'][1]
        rotLimit = (descr.physics.get('rotationSpeedLimit')
            or descr.physics.get('rotationSpeed')
            or descr.physics.get('turretRotationSpeed')
            or 0.5)

        if not hasattr(self, '_cur_speed'):
            self._cur_speed = 0.0
            self._cur_rot   = 0.0

        accel = 3.0
        if move > 0:
            self._cur_speed = min(self._cur_speed + accel * dt, fwdLimit)
        elif move < 0:
            self._cur_speed = max(self._cur_speed - accel * dt, -bwdLimit)
        else:
            if abs(self._cur_speed) < accel * dt:
                self._cur_speed = 0.0
            elif self._cur_speed > 0:
                self._cur_speed -= accel * dt
            else:
                self._cur_speed += accel * dt

        if turn != 0:
            self._cur_rot = turn * rotLimit
        else:
            self._cur_rot = 0.0

        if not hasattr(self, '_cur_yaw'):
            self._cur_yaw = 0.0
        self._cur_yaw += self._cur_rot * dt

        import math as _math
        if not hasattr(self, '_cur_pos'):
            self._cur_pos = Math.Vector3(veh.position)
        self._cur_pos.x += _math.sin(self._cur_yaw) * self._cur_speed * dt
        self._cur_pos.z += _math.cos(self._cur_yaw) * self._cur_speed * dt

        my_id = self.playerAvatar.playerVehicleID
        next_x = self._cur_pos.x
        next_z = self._cur_pos.z

        bot_pos_by_id = {}
        for _b in self._bot_ai:
            bot_pos_by_id[_b['vehID']] = _b['pos']

        for vehID, _, _ in self.vehicles:
            if vehID == my_id:
                continue
            other_veh = BigWorld.entity(vehID)
            if not other_veh or not getattr(other_veh, 'isStarted', False):
                continue
            livePos = bot_pos_by_id.get(vehID)
            if livePos is not None:
                other_x, other_y, other_z = livePos.x, livePos.y, livePos.z
            else:
                other_x, other_y, other_z = other_veh.position.x, other_veh.position.y, other_veh.position.z
            diff_x = next_x - other_x
            diff_z = next_z - other_z
            dist = _math.sqrt(diff_x * diff_x + diff_z * diff_z)
            min_dist = 3.5
            if dist < min_dist and dist > 0.001:
                overlap = min_dist - dist
                nx = diff_x / dist
                nz = diff_z / dist
                next_x += nx * overlap * 0.6
                next_z += nz * overlap * 0.6
                self._cur_speed *= 0.3
                try:
                    new_bot_pos = Math.Vector3(
                        other_x - nx * overlap * 0.4,
                        other_y,
                        other_z - nz * overlap * 0.4
                    )
                    if livePos is not None:
                        livePos.x = new_bot_pos.x
                        livePos.z = new_bot_pos.z
                    if hasattr(other_veh, '_offline_matrix'):
                        other_veh._offline_matrix.translation = new_bot_pos
                except:
                    pass
        self._cur_pos.x = next_x
        self._cur_pos.z = next_z

        groundY = get_ground_height(self.spaceID, self._cur_pos)
        if groundY > 0:
            self._cur_pos.y = groundY + 0.5
        pos = self._cur_pos

        groundY = get_ground_height(self.spaceID, pos)
        if groundY > -100:
            pos.y = groundY

        import math as _math

        L = 2.5
        W = 1.5

        fx = _math.sin(self._cur_yaw)
        fz = _math.cos(self._cur_yaw)
        rx = _math.cos(self._cur_yaw)
        rz = -_math.sin(self._cur_yaw)

        h_front = get_ground_height(self.spaceID, Math.Vector3(pos.x + fx*L, 0, pos.z + fz*L))
        h_back  = get_ground_height(self.spaceID, Math.Vector3(pos.x - fx*L, 0, pos.z - fz*L))
        h_right = get_ground_height(self.spaceID, Math.Vector3(pos.x + rx*W, 0, pos.z + rz*W))
        h_left  = get_ground_height(self.spaceID, Math.Vector3(pos.x - rx*W, 0, pos.z - rz*W))


        target_pitch = _math.atan2(h_back - h_front, L * 2.0)
        target_roll  = _math.atan2(h_right - h_left, W * 2.0)

        if not hasattr(self, '_cur_pitch'):
            self._cur_pitch = 0.0
            self._cur_roll  = 0.0
        
        self._cur_pitch += (target_pitch - self._cur_pitch) * 0.15
        self._cur_roll  += (target_roll - self._cur_roll) * 0.15

        direction = Math.Vector3(self._cur_yaw, self._cur_pitch, self._cur_roll)

        try:
            flt.allowLagProcessing = True
            flt.setInitialSpeeds(self._cur_speed, self._cur_rot)

            try:
                fsh = veh.appearance._VehicleAppearance__fashion
                if fsh is not None:
                    _hw = descr.chassis['topRightCarryingPoint'][0]
                    _max_spd = max(fwdLimit, 0.001)
                    _left  = (self._cur_speed - self._cur_rot * _hw) / _max_spd
                    _right = (self._cur_speed + self._cur_rot * _hw) / _max_spd
                    fsh.movementInfo = Math.Vector4(0.0, _left, _right, 0.0)
            except Exception as e3:
                LOG_NOTE("[MOVE] fashion.movementInfo update failed: %s" % e3)

            if not hasattr(self, '_offline_matrix'):
                self._offline_matrix = Math.Matrix()
                self._offline_matrix.setRotateYPR((self._cur_yaw, self._cur_pitch, self._cur_roll))
                self._offline_matrix.translation = pos
                self._offline_servo = BigWorld.Servo(self._offline_matrix)
                try:
                    veh.model.delMotor(veh.model.motors[0])
                    veh.model.addMotor(self._offline_servo)
                    LOG_NOTE("[MOVE] Offline Servo motor installed OK")
                except Exception as e2:
                    LOG_NOTE("[MOVE] Servo install failed: %s" % e2)
                    del self._offline_matrix
            else:
                self._offline_matrix.setRotateYPR((self._cur_yaw, self._cur_pitch, self._cur_roll))
                self._offline_matrix.translation = pos

            if abs(self._cur_speed) > 0.01 or abs(self._cur_rot) > 0.001:
                LOG_NOTE("[MOVE] pos=(%.1f,%.1f,%.1f) spd=%.2f yaw=%.3f" % (
                    pos.x, pos.y, pos.z, self._cur_speed, self._cur_yaw))
        except Exception as e:
            LOG_NOTE("[MOVE] tick failed: %s" % e)
        
        try:
            flags = 0
            if move > 0:  flags |= 1
            if move < 0:  flags |= 2
            if turn < 0:  flags |= 4
            if turn > 0:  flags |= 8
            veh.showPlayerMovementCommand(flags)

            if abs(self._cur_speed) < 0.1 and move == 0:
                power = 1
            elif abs(self._cur_speed) > self._cur_speed * 0.5 and move != 0:
                power = 3
            else:
                power = 2
            dirFlags = flags & 0x03
            engine_mode = (power, dirFlags)
            if getattr(veh, 'appearance', None):
                try:
                    if veh.appearance.changeEngineMode(engine_mode) is not False:
                        pass
                except Exception as _em_e:
                    pass
                try:
                    flt = getattr(veh, 'filter', None)
                    if flt and hasattr(flt, 'speedInfo'):
                        flt.setInitialSpeeds(self._cur_speed, self._cur_rot)
                except: pass
        except: pass
        try:
            mm = getattr(self.playerAvatar, '_minimap', None)
            if mm and hasattr(mm, 'onVehicleMove'):
                mm.onVehicleMove(self.playerAvatar.playerVehicleID, pos, self._cur_yaw)
        except:
            pass
        BigWorld.callback(0.05, self.__movementTick)

    def __botAITick(self):
        if self._stopped:
            return
        if not self._bot_ai:
            BigWorld.callback(0.1, self.__botAITick)
            return

        if not self._battleStarted:
            BigWorld.callback(0.1, self.__botAITick)
            return

        now = BigWorld.time()
        if not hasattr(self, '_bot_last_tick'):
            self._bot_last_tick = now
        dt = now - self._bot_last_tick
        if dt <= 0.0 or dt > 0.3:
            dt = 0.1
        self._bot_last_tick = now

        DETECT_RANGE = 130.0  
        FIRE_RANGE = 60.0     

        aliveBots = dict((b['vehID'], b) for b in self._bot_ai if not b.get('dead'))

        playerVehID = self.playerAvatar.playerVehicleID if self.playerAvatar else None
        playerData = self.arena.vehicles.get(playerVehID) if playerVehID is not None else None
        playerAlive = bool(playerData and playerData.get('isAlive', True) and hasattr(self, '_cur_pos'))

        for bot in self._bot_ai:
            if bot.get('dead'):
                continue
            veh = BigWorld.entity(bot['vehID'])
            if veh is None or not getattr(veh, 'isStarted', False):
                continue
            flt = getattr(veh, 'filter', None)
            if flt is None:
                continue

            botTeam = bot.get('team')
            if botTeam is None:
                vdataBot = self.arena.vehicles.get(bot['vehID'])
                botTeam = vdataBot.get('team') if vdataBot else None

            bestDist = None
            bestKind = None       
            bestTargetID = None
            bestTargetPos = None
            try:
                for otherID, other in aliveBots.items():
                    if otherID == bot['vehID']:
                        continue
                    otherTeam = other.get('team')
                    if otherTeam is None or otherTeam == botTeam:
                        continue
                    dxo = other['pos'].x - bot['pos'].x
                    dzo = other['pos'].z - bot['pos'].z
                    do = math.sqrt(dxo * dxo + dzo * dzo)
                    if do <= DETECT_RANGE and (bestDist is None or do < bestDist):
                        bestDist, bestKind, bestTargetID, bestTargetPos = do, 'bot', otherID, other['pos']

                if botTeam is not None and botTeam != 1 and playerAlive:
                    dxp = self._cur_pos.x - bot['pos'].x
                    dzp = self._cur_pos.z - bot['pos'].z
                    dp = math.sqrt(dxp * dxp + dzp * dzp)
                    if dp <= DETECT_RANGE and (bestDist is None or dp < bestDist):
                        bestDist, bestKind, bestTargetID, bestTargetPos = dp, 'player', playerVehID, self._cur_pos
            except Exception as e:
                LOG_NOTE("[BOT-AI] target search failed for %s: %s" % (bot['vehID'], e))

            bot['engageID'] = bestTargetID

            turretRot = bot.get('turret')
            turretAimed = False
            if turretRot is not None:
                turretSpeed = 0.5
                try:
                    turretSpeed = bot['descr'].turret['rotationSpeed']
                except Exception:
                    pass
                maxYawStep = max(0.05, turretSpeed) * dt
                if bestKind is not None and bestTargetPos is not None:
                    dxT = bestTargetPos.x - bot['pos'].x
                    dzT = bestTargetPos.z - bot['pos'].z
                    worldAimYaw = math.atan2(dxT, dzT)
                    localAimYaw = worldAimYaw - bot['yaw']
                    turretAimed = turretRot.turnTowards(localAimYaw, maxYawStep)
                else:
                    turretRot.turnTowards(0.0, maxYawStep * 0.5)

            canSeeTarget = False
            if bestKind is not None and bestTargetPos is not None:
                canSeeTarget = has_line_of_sight(self.spaceID, bot['pos'], bestTargetPos)

            if (bestKind is not None and bestDist is not None and bestDist <= FIRE_RANGE
                    and canSeeTarget and turretAimed):
                try:
                    nextShot = bot.get('nextShotTime')
                    if nextShot is None:
                        bot['nextShotTime'] = now + random.uniform(2.0, 5.0)
                    elif now >= nextShot:
                        bot['nextShotTime'] = now + random.uniform(4.0, 7.0)
                        if random.random() < 0.6:
                            dmg = _random_shell_damage(bot['descr'].shot)
                            if bestKind == 'player':
                                self.apply_damage_to_player(dmg, attackerID=bot['vehID'])
                            else:
                                targetBot = aliveBots.get(bestTargetID)
                                if targetBot is not None:
                                    wasAlive = not targetBot.get('dead')
                                    self.apply_damage_to_bot(targetBot, dmg)
                                    if wasAlive and targetBot.get('dead'):
                                        vdataAttacker = self.arena.vehicles.get(bot['vehID'])
                                        if vdataAttacker is not None:
                                            vdataAttacker['frags'] = vdataAttacker.get('frags', 0) + 1
                                            try:
                                                if hasattr(self.arena, 'onVehicleUpdated'):
                                                    self.arena.onVehicleUpdated(bot['vehID'], 'frags', vdataAttacker['frags'])
                                            except Exception:
                                                pass
                            try:
                                veh.showShooting(1)
                            except Exception:
                                pass
                            LOG_NOTE("[BOT-AI] Bot %s fired at %s(%s) for %d dmg (dist=%.1f)" % (
                                bot['vehID'], bestKind, bestTargetID, dmg, bestDist))
                except Exception as e:
                    LOG_NOTE("[BOT-AI] fire check failed for %s: %s" % (bot['vehID'], e))

            hasTarget = bestKind is not None and bestTargetPos is not None
            target = bestTargetPos if hasTarget else bot['wp']
            dx = target.x - bot['pos'].x
            dz = target.z - bot['pos'].z
            dist = math.sqrt(dx * dx + dz * dz)

            if not hasTarget and dist < 3.0:
                bot['wp'] = self._random_wander_point()
                target = bot['wp']
                dx = target.x - bot['pos'].x
                dz = target.z - bot['pos'].z
                dist = math.sqrt(dx * dx + dz * dz)
                if dist < 0.001:
                    dist = 0.001

            desiredYaw = math.atan2(dx, dz)
            yawDiff = (desiredYaw - bot['yaw'] + math.pi) % (2.0 * math.pi) - math.pi

            maxRot = 0.6  
            turnStep = max(-maxRot * dt, min(maxRot * dt, yawDiff))
            bot['yaw'] += turnStep

            fwdLimit = 10.0
            try:
                fwdLimit = bot['descr'].physics['speedLimits'][0]
            except Exception:
                pass

            if hasTarget and bestDist is not None and bestDist <= FIRE_RANGE * 0.7:
                speed = min(fwdLimit * 0.6, max(dist - FIRE_RANGE * 0.5, 0.0) * 1.5)
            else:
                speed = min(fwdLimit * 0.6, max(dist, 0.0) * 1.5)
            if abs(yawDiff) > 0.9:
                speed *= 0.25

            bot['pos'].x += math.sin(bot['yaw']) * speed * dt
            bot['pos'].z += math.cos(bot['yaw']) * speed * dt

            groundY = get_ground_height(self.spaceID, bot['pos'])
            if groundY > -100.0:
                bot['pos'].y = groundY + 0.5

            try:
                _L = 2.5
                _W = 1.5
                _fx = math.sin(bot['yaw']); _fz = math.cos(bot['yaw'])
                _rx = math.cos(bot['yaw']); _rz = -math.sin(bot['yaw'])
                _h_front = get_ground_height(self.spaceID, Math.Vector3(bot['pos'].x + _fx * _L, 0, bot['pos'].z + _fz * _L))
                _h_back  = get_ground_height(self.spaceID, Math.Vector3(bot['pos'].x - _fx * _L, 0, bot['pos'].z - _fz * _L))
                _h_right = get_ground_height(self.spaceID, Math.Vector3(bot['pos'].x + _rx * _W, 0, bot['pos'].z + _rz * _W))
                _h_left  = get_ground_height(self.spaceID, Math.Vector3(bot['pos'].x - _rx * _W, 0, bot['pos'].z - _rz * _W))
                _target_pitch = math.atan2(_h_back - _h_front, _L * 2.0)
                _target_roll  = math.atan2(_h_right - _h_left, _W * 2.0)
                if 'pitch' not in bot:
                    bot['pitch'] = 0.0
                    bot['roll'] = 0.0
                bot['pitch'] += (_target_pitch - bot['pitch']) * 0.15
                bot['roll']  += (_target_roll - bot['roll']) * 0.15

                if bot['matrix'] is None:
                    bot['matrix'] = Math.Matrix()
                    bot['matrix'].setRotateYPR((bot['yaw'], bot['pitch'], bot['roll']))
                    bot['matrix'].translation = bot['pos']
                    bot['servo'] = BigWorld.Servo(bot['matrix'])
                    try:
                        veh.model.delMotor(veh.model.motors[0])
                        veh.model.addMotor(bot['servo'])
                        LOG_NOTE("[BOT-AI] Servo motor installed for bot %s" % bot['vehID'])
                    except Exception as e2:
                        LOG_NOTE("[BOT-AI] Servo install failed for %s: %s" % (bot['vehID'], e2))
                        bot['matrix'] = None
                        bot['servo'] = None
                else:
                    bot['matrix'].setRotateYPR((bot['yaw'], bot['pitch'], bot['roll']))
                    bot['matrix'].translation = bot['pos']

                flt.allowLagProcessing = True
                _rot = turnStep / dt if dt > 0 else 0.0
                flt.setInitialSpeeds(speed, _rot)

                try:
                    fsh = veh.appearance._VehicleAppearance__fashion
                    if fsh is not None:
                        _hw = bot['descr'].chassis['topRightCarryingPoint'][0]
                        _max_spd = max(fwdLimit, 0.001)
                        _left  = (speed - _rot * _hw) / _max_spd
                        _right = (speed + _rot * _hw) / _max_spd
                        fsh.movementInfo = Math.Vector4(0.0, _left, _right, 0.0)
                except Exception as e3:
                    LOG_NOTE("[BOT-AI] fashion.movementInfo update failed for %s: %s" % (bot['vehID'], e3))
            except Exception as e:
                LOG_NOTE("[BOT-AI] tick failed for bot %s: %s" % (bot['vehID'], e))

            try:
                flags = 1 if speed > 0.1 else 0
                veh.showPlayerMovementCommand(flags)
                if getattr(veh, 'appearance', None):
                    power = 3 if speed > 0.1 else 1
                    try:
                        veh.appearance.changeEngineMode((power, flags))
                    except Exception:
                        pass
            except Exception:
                pass

        BigWorld.callback(0.1, self.__botAITick)

    def __captureTick(self):
        if self._stopped:
            return
        if not self._battleStarted or getattr(self, '_battleResultShown', False):
            BigWorld.callback(0.5, self.__captureTick)
            return
        try:
            self.__captureTickImpl()
        except Exception as e:
            LOG_NOTE("[CAPTURE] tick failed: %s" % e)
        if not getattr(self, '_battleResultShown', False):
            BigWorld.callback(0.5, self.__captureTick)

    def __captureTickImpl(self):
        dt = 0.5

        playerVehID = self.playerAvatar.playerVehicleID if self.playerAvatar else None
        playerData = self.arena.vehicles.get(playerVehID) if playerVehID is not None else None
        playerAlive = bool(playerData and playerData.get('isAlive', True) and hasattr(self, '_cur_pos')
                            and not getattr(self, '_playerDestroyed', False))
        playerTeam = playerData.get('team', 1) if playerData else 1

        liveVehicles = []
        if playerAlive:
            liveVehicles.append((playerTeam, self._cur_pos))
        for bot in self._bot_ai:
            if bot.get('dead'):
                continue
            botTeam = bot.get('team')
            if botTeam is None:
                continue
            liveVehicles.append((botTeam, bot['pos']))

        for defTeam, basePos in self._teamBaseCenter.items():
            if basePos is None:
                continue
            attackers = 0
            defenders = 0
            for team, pos in liveVehicles:
                dx = pos.x - basePos.x
                dz = pos.z - basePos.z
                if (dx * dx + dz * dz) <= (CAPTURE_RADIUS * CAPTURE_RADIUS):
                    if team == defTeam:
                        defenders += 1
                    else:
                        attackers += 1

            state = self._captureState[defTeam]
            if defenders > 0:
                state['points'] = max(0.0, state['points'] - CAPTURE_RESET_RATE * dt)
            elif attackers > 0:
                n = min(attackers, CAPTURE_MAX_VEHICLES_COUNTED)
                state['points'] = min(CAPTURE_POINTS_TO_WIN,
                                       state['points'] + CAPTURE_RATE_PER_VEHICLE * n * dt)
            state['attackers'] = attackers
            state['defenders'] = defenders

            if state['points'] >= CAPTURE_POINTS_TO_WIN:
                self.__onBaseCaptured(defTeam)
                return

        self._updateCaptureBar()

    def __onBaseCaptured(self, capturedTeam):
        if getattr(self, '_battleResultShown', False):
            return
        self._battleResultShown = True

        playerData = self.arena.vehicles.get(self.playerAvatar.playerVehicleID) if self.playerAvatar else None
        playerTeam = playerData.get('team', 1) if playerData else 1
        playerWon = (capturedTeam != playerTeam)

        LOG_NOTE("[CAPTURE] Base of team %d captured! Player %s" % (
            capturedTeam, "WINS" if playerWon else "LOSES"))
        _play_sound_event('battle_start' if playerWon else 'vehicle_destroyed')
        self._showCaptureResult(playerWon)
        self._updateCaptureBar()
        BigWorld.callback(3.0, self._finishBattle)

    def _ensureCaptureBar(self):
        if self._capture_bar_gui is not None:
            return self._capture_bar_gui
        try:
            parts = {}
            for key in ('enemy_bg', 'enemy_fill', 'own_bg', 'own_fill'):
                c = GUI.Colour((0, 0, 0, 0))
                c.visible = False
                GUI.mroot().addChild(c)
                parts[key] = c
            self._capture_bar_gui = parts
            LOG_NOTE("[CAPTURE][UI] Capture bar GUI created OK")
        except Exception as e:
            LOG_NOTE("[CAPTURE][UI] Failed to create capture bar: %s" % e)
            self._capture_bar_gui = None
        return self._capture_bar_gui

    def _updateCaptureBar(self):
        parts = self._ensureCaptureBar()
        if not parts:
            return
        try:
            playerData = self.arena.vehicles.get(self.playerAvatar.playerVehicleID) if self.playerAvatar else None
            playerTeam = playerData.get('team', 1) if playerData else 1
            enemyTeam = 2 if playerTeam == 1 else 1

            BAR_W = 0.36
            BAR_H = 0.018
            X0 = -BAR_W / 2.0

            enemyState = self._captureState.get(enemyTeam)
            if enemyState is not None:
                frac = max(0.0, min(1.0, enemyState['points'] / CAPTURE_POINTS_TO_WIN))
                active = frac > 0.001 or enemyState.get('attackers', 0) > 0
                bg, fill = parts['enemy_bg'], parts['enemy_fill']
                bg.colour = (20, 20, 20, 170)
                bg.width, bg.height = BAR_W, BAR_H
                bg.position = (0.0, 0.86, 0)
                bg.visible = active
                fillW = max(BAR_W * frac, 0.0001)
                fill.colour = (60, 230, 60, 235)
                fill.width, fill.height = fillW, BAR_H
                fill.position = (X0 + fillW / 2.0, 0.86, 0)
                fill.visible = active and frac > 0.001

            ownState = self._captureState.get(playerTeam)
            if ownState is not None:
                frac2 = max(0.0, min(1.0, ownState['points'] / CAPTURE_POINTS_TO_WIN))
                active2 = frac2 > 0.001 or ownState.get('attackers', 0) > 0
                bg2, fill2 = parts['own_bg'], parts['own_fill']
                bg2.colour = (20, 20, 20, 170)
                bg2.width, bg2.height = BAR_W, BAR_H
                bg2.position = (0.0, 0.82, 0)
                bg2.visible = active2
                fillW2 = max(BAR_W * frac2, 0.0001)
                fill2.colour = (230, 60, 60, 235)
                fill2.width, fill2.height = fillW2, BAR_H
                fill2.position = (X0 + fillW2 / 2.0, 0.82, 0)
                fill2.visible = active2 and frac2 > 0.001
        except Exception as e:
            LOG_NOTE("[CAPTURE][UI] update failed: %s" % e)

    def _showCaptureResult(self, playerWon):
        try:
            if getattr(self, '_capture_result_text', None) is None:
                t = GUI.Text("")
                GUI.mroot().addChild(t)
                self._capture_result_text = t
            t = self._capture_result_text
            t.text = "ПОБЕДА! База захвачена" if playerWon else "ПОРАЖЕНИЕ! Ваша база захвачена"
            t.colour = (60, 230, 60, 255) if playerWon else (230, 60, 60, 255)
            t.position = (0.0, 0.0, 0)
            t.visible = True
        except Exception as e:
            LOG_NOTE("[CAPTURE][UI] result text failed: %s" % e)

    def _hideCaptureUI(self):
        try:
            if self._capture_bar_gui:
                for c in self._capture_bar_gui.values():
                    GUI.mroot().delChild(c)
        except Exception:
            pass
        self._capture_bar_gui = None
        try:
            if self._capture_result_text is not None:
                GUI.mroot().delChild(self._capture_result_text)
        except Exception:
            pass
        self._capture_result_text = None

    def find_hit_bot(self, shotPos, shotDir, maxRange=500.0, maxRadius=3.2):
        dirLen = math.sqrt(shotDir.x * shotDir.x + shotDir.y * shotDir.y + shotDir.z * shotDir.z)
        if dirLen < 0.0001:
            return None
        ux, uy, uz = shotDir.x / dirLen, shotDir.y / dirLen, shotDir.z / dirLen

        best = None
        bestProj = None
        for bot in self._bot_ai:
            if bot.get('dead'):
                continue
            bpos = bot['pos']
            tx = bpos.x - shotPos.x
            ty = bpos.y - shotPos.y
            tz = bpos.z - shotPos.z
            proj = tx * ux + ty * uy + tz * uz
            if proj <= 0.0 or proj > maxRange:
                continue
            cx = shotPos.x + ux * proj
            cy = shotPos.y + uy * proj
            cz = shotPos.z + uz * proj
            dx = bpos.x - cx
            dy = bpos.y - cy
            dz = bpos.z - cz
            perp = math.sqrt(dx * dx + dy * dy + dz * dz)
            if perp <= maxRadius:
                if bestProj is None or proj < bestProj:
                    bestProj = proj
                    best = bot
        return best

    def _refresh_battle_players(self):
        try:
            bw = self.battleWindow
            if bw is None:
                return
            from gui.Scaleform import Battle as _BattleMod
            upd = getattr(_BattleMod.Battle, '_Battle__updatePlayers', None)
            if upd:
                upd(bw)
                LOG_NOTE("[BATTLE] Tab players panel refreshed")
        except Exception as e:
            LOG_NOTE("[BATTLE] _refresh_battle_players failed: %s" % e)

    def apply_damage_to_bot(self, bot, dmg):
        botID = bot['vehID']
        vdata = self.arena.vehicles.get(botID)
        if vdata is None:
            return
        newHP = max(0, vdata.get('health', 0) - int(dmg))
        vdata['health'] = newHP
        LOG_NOTE("[HIT] Bot %s took %d dmg, hp=%d" % (botID, dmg, newHP))
        _play_sound_event('hit_penetration', pos=bot.get('pos'))
        if newHP <= 0 and not bot.get('dead'):
            bot['dead'] = True
            vdata['isAlive'] = False
            vdata['health'] = 0
            _play_sound_event('vehicle_destroyed', pos=bot.get('pos'))

            try:
                if hasattr(self.arena, 'onVehicleUpdated'):
                    self.arena.onVehicleUpdated(botID, 'isAlive', False)
                    self.arena.onVehicleUpdated(botID, 'health', 0)
                if hasattr(self.arena, 'onVehicleKilled'):
                    self.arena.onVehicleKilled(botID, self.playerAvatar.playerVehicleID, 0, 0)
            except Exception as e:
                LOG_NOTE("[HIT] arena kill-event dispatch unavailable/failed for %s: %s" % (botID, e))

            try:
                playerVehID = self.playerAvatar.playerVehicleID
                pdata = self.arena.vehicles.get(playerVehID)
                if pdata is not None:
                    pdata['frags'] = pdata.get('frags', 0) + 1
                    LOG_NOTE("[BATTLE] Player frags now %d" % pdata['frags'])
                    try:
                        if hasattr(self.arena, 'onVehicleUpdated'):
                            self.arena.onVehicleUpdated(playerVehID, 'frags', pdata['frags'])
                    except Exception as e2:
                        LOG_NOTE("[BATTLE] arena.onVehicleUpdated(frags) unavailable/failed: %s" % e2)
            except Exception as e:
                LOG_NOTE("[HIT] failed to credit frag for bot %s: %s" % (botID, e))

            veh = BigWorld.entity(botID)

            try:
                if veh is not None:
                    veh.showPlayerMovementCommand(0)
                    if getattr(veh, 'appearance', None):
                        try:
                            veh.appearance.changeEngineMode((0, 0))
                        except Exception:
                            pass
            except Exception as e:
                LOG_NOTE("[HIT] failed to stop destroyed bot %s: %s" % (botID, e))

            try:
                if bot.get('matrix') is not None and bot.get('pos') is not None:
                    bot['pos'].y -= 0.15
                    tiltPitch = random.uniform(-0.05, 0.05)
                    tiltRoll  = random.uniform(-0.12, 0.12)
                    bot['matrix'].setRotateYPR((bot['yaw'], tiltPitch, tiltRoll))
                    bot['matrix'].translation = bot['pos']
            except Exception as e:
                LOG_NOTE("[HIT] failed to tilt destroyed bot %s: %s" % (botID, e))

            try:
                _DESTROYED_VEH_IDS.add(botID)
                if veh is not None and getattr(veh, 'appearance', None):
                    rebuild = getattr(veh.appearance, '_VehicleAppearance__setupModels', None)
                    if rebuild:
                        rebuild()
                        LOG_NOTE("[HIT] Rebuilt appearance (destroyed) for bot %s" % botID)
            except Exception as e:
                LOG_NOTE("[HIT] failed to rebuild destroyed appearance for %s: %s" % (botID, e))

            self._refresh_battle_players()

            LOG_NOTE("[BATTLE] Bot %s DESTROYED" % botID)

    def apply_damage_to_player(self, dmg, attackerID=None):
        if getattr(self, '_playerDestroyed', False):
            return
        if not self.playerAvatar:
            return
        playerVehID = self.playerAvatar.playerVehicleID
        vdata = self.arena.vehicles.get(playerVehID)
        if vdata is None or not vdata.get('isAlive', True):
            return

        newHP = max(0, vdata.get('health', 0) - int(dmg))
        vdata['health'] = newHP

        veh = BigWorld.entity(playerVehID)
        if veh is not None:
            veh.health = newHP

        LOG_NOTE("[HIT] Player took %d dmg from %s, hp=%d" % (dmg, attackerID, newHP))
        _play_sound_event('hit_penetration', pos=getattr(self, '_cur_pos', None))

        try:
            if hasattr(self.arena, 'onVehicleUpdated'):
                self.arena.onVehicleUpdated(playerVehID, 'health', newHP)
        except Exception as e:
            LOG_NOTE("[BATTLE] arena.onVehicleUpdated(health) failed: %s" % e)

        try:
            if self.battleWindow and hasattr(self.battleWindow, 'damagePanel'):
                self.battleWindow.damagePanel.updateHealth(newHP)
        except Exception as e:
            LOG_NOTE("[BATTLE] damagePanel update on hit failed: %s" % e)
        try:
            from AvatarInputHandler import aims
            aims._g_aimState['health']['cur'] = newHP
        except Exception as e:
            LOG_NOTE("[BATTLE] aims health update on hit failed: %s" % e)

        if newHP <= 0:
            vdata['isAlive'] = False
            self._playerDestroyed = True
            _play_sound_event('vehicle_destroyed', pos=getattr(self, '_cur_pos', None))
            try:
                if hasattr(self.arena, 'onVehicleUpdated'):
                    self.arena.onVehicleUpdated(playerVehID, 'isAlive', False)
                if hasattr(self.arena, 'onVehicleKilled') and attackerID is not None:
                    self.arena.onVehicleKilled(playerVehID, attackerID, 0, 0)
            except Exception as e:
                LOG_NOTE("[BATTLE] arena kill-event dispatch failed for player: %s" % e)

            self.playerAvatar._moveForward = False
            self.playerAvatar._moveBack    = False
            self.playerAvatar._turnLeft    = False
            self.playerAvatar._turnRight   = False
            self.playerAvatar.currentMove  = 0.0
            self.playerAvatar.currentTurn  = 0.0

            LOG_NOTE("[BATTLE] Player vehicle DESTROYED, returning to hangar shortly")
            BigWorld.callback(3.0, self._finishBattle)

    def _finalizeInit(self, resourceRefs):
        LOG_NOTE("[BATTLE] _finalizeInit: checking %d vehicles..." % len(self.vehicles))
        for vehID, _, _ in self.vehicles:
            veh = BigWorld.entity(vehID)
            if veh is None or not veh.inWorld:
                LOG_NOTE("[BATTLE] _finalizeInit: vehID=%s not ready yet (inWorld=%s), retrying..." % (
                    vehID, getattr(veh, 'inWorld', 'N/A')))
                BigWorld.callback(0.1, lambda: self._finalizeInit(resourceRefs))
                return

        LOG_NOTE("[BATTLE] All %d vehicles in world, starting visual init..." % len(self.vehicles))
        try:
            from gui.Scaleform.Waiting import Waiting
            Waiting.hide()
        except: pass
        self._patch_vehicle()

        for vehID, descr, isPlayer in self.vehicles:
            veh = BigWorld.entity(vehID)
            if not veh:
                LOG_ERROR("[BATTLE] _finalizeInit: entity %d is None!" % vehID)
                continue
            veh.isPlayer = isPlayer
            veh.isCrewActive = True
            veh.health = descr.maxHealth
            if getattr(veh, 'appearance', None):
                try:
                    veh.appearance.changeEngineMode((1, 0))
                except Exception as e:
                    LOG_NOTE("[BATTLE] changeEngineMode init failed vehID=%d: %s" % (vehID, e))
            veh.damageStickers = ()
            veh.publicStateModifiers = []
            try:
                veh.typeDescriptor.keepPrereqs(resourceRefs)
                veh._Vehicle__prereqs = resourceRefs
            except: pass
            if not isPlayer:
                try:
                    m = Math.Matrix()
                    m.setRotateYPR((0, 0, 0))
                    m.translation = veh.position
                    servo = BigWorld.Servo(m)
                    if hasattr(veh, 'model'):
                        veh.model.addMotor(servo)
                    veh._offline_matrix = m
                    veh._offline_servo = servo
                except: pass
            LOG_NOTE("[BATTLE] Vehicle %d prepared: isPlayer=%s health=%d" % (vehID, isPlayer, descr.maxHealth))

        from VehicleGunRotator import VehicleGunRotator
        try:
            real_gr = VehicleGunRotator(self.playerAvatar)
            descr = self.playerAvatar.vehicleTypeDescriptor
            turretSpeed = descr.turret['rotationSpeed']
            gunSpeed    = turretSpeed * 0.5               
            real_gr._VehicleGunRotator__turretRotationSpeed = turretSpeed
            real_gr._VehicleGunRotator__gunRotationSpeed    = gunSpeed
            self.playerAvatar.gunRotator = real_gr
            LOG_NOTE("[BATTLE] Real VehicleGunRotator installed, turretSpeed=%.4f" % turretSpeed)
        except Exception as e:
            LOG_NOTE("[BATTLE] VehicleGunRotator failed, using Dummy: %s" % e)
            self.playerAvatar.gunRotator = DummyGunRotator()

        self.playerAvatar.turretMatrix = self.playerAvatar.gunRotator.turretMatrix
        self.playerAvatar.gunMatrix = self.playerAvatar.gunRotator.gunMatrix

        from AvatarInputHandler import AvatarInputHandler
        aih = AvatarInputHandler()


        try:
            aih.onCameraChanged += lambda mode: None
        except Exception as _e:
            LOG_NOTE("[BATTLE] onCameraChanged subscribe failed: %s" % _e)

        _orig_start = aih.start
        def _safe_aih_start():
            try:
                _orig_start()
                LOG_NOTE("[BATTLE] AvatarInputHandler.start() OK")
            except TypeError as _te:
                LOG_NOTE("[BATTLE] AvatarInputHandler.start() TypeError (suppressed): %s" % _te)
                try:
                    aih._AvatarInputHandler__isStarted = True
                    aih._AvatarInputHandler__isArenaStarted = False
                    aih._AvatarInputHandler__isGUIVisible = True
                    aih._AvatarInputHandler__curCtrl.enable(
                        ctrlState=__import__('control_modes').dumpStateEmpty()
                    )
                    aih.onCameraChanged('arcade')
                except Exception as _e2:
                    LOG_NOTE("[BATTLE] Manual AIH init also failed: %s" % _e2)
            except Exception as _e:
                LOG_NOTE("[BATTLE] AvatarInputHandler.start() other error: %s" % _e)

        self.playerAvatar.inputHandler = aih
        _safe_aih_start()
        BigWorld.callback(2.0, self._setupTankIndicator)
        LOG_NOTE("[BATTLE] AvatarInputHandler init done")

        try:
            import sys
            control_modes = sys.modules.get('AvatarInputHandler.control_modes')
            if control_modes:
                def _patched_flash_enable(self, state):
                    if state is not None and 'reload' in state:
                        if 'start_time' in state['reload'] and 'startTime' not in state['reload']:
                            state['reload']['startTime'] = state['reload']['start_time']
                    return True
                if hasattr(control_modes, '_FlashGunMarker'):
                    control_modes._FlashGunMarker.enable = _patched_flash_enable
                if hasattr(control_modes, '_SPGFlashGunMarker'):
                    control_modes._SPGFlashGunMarker.enable = _patched_flash_enable
                LOG_NOTE("[BATTLE] GunMarker patch OK")
        except Exception as e:
            LOG_NOTE("[BATTLE] GunMarker patch failed: %s" % e)

        self._patch_control_modes()
        self._applyAimPatches()
        self.playerAvatar.inputHandler.setReloading(0)

        playerVeh = BigWorld.entity(self.playerAvatar.playerVehicleID)
        LOG_NOTE("[BATTLE] Player vehicle entity: %s" % playerVeh)

        if playerVeh and hasattr(playerVeh, 'filter') and playerVeh.filter:
            if hasattr(playerVeh, 'appearance') and playerVeh.appearance:
                try:
                    fashion = playerVeh.appearance.modelsDesc['chassis']['model'].wg_fashion
                    fashion.movementInfo = playerVeh.filter.movementInfo
                    LOG_NOTE("[BATTLE] movementInfo linked to filter OK")
                except Exception as e:
                    LOG_NOTE("[BATTLE] movementInfo link failed: %s" % e)

        if playerVeh:
            cam = BigWorld.camera()
            if cam is None:
                cam = BigWorld.CursorCamera()
                LOG_NOTE("[BATTLE] Created new camera")
            cam.spaceID = self.spaceID
            cam.target = playerVeh.matrix
            BigWorld.camera(cam)
            LOG_NOTE("[BATTLE] Camera targeted to player vehicle OK")
            self.playerAvatar.bindToVehicle(True, self.playerAvatar.playerVehicleID)
            BigWorld.worldDrawEnabled(True)
        else:
            LOG_ERROR("[BATTLE] playerVeh is None at finalizeInit! playerVehicleID=%s" % self.playerAvatar.playerVehicleID)

        g_windowsManager.startBattle()
        self.battleWindow = g_windowsManager.battleWindow
        LOG_NOTE("[BATTLE] g_windowsManager.startBattle() called, battleWindow=%s" % self.battleWindow)

        for vehID, descr, isPlayer in self.vehicles:
            veh = BigWorld.entity(vehID)
            if not veh:
                LOG_ERROR("[BATTLE] startVisual: entity %d is None!" % vehID)
                continue
            veh.health       = descr.maxHealth
            veh.isCrewActive = True
            if not getattr(veh, 'isStarted', False):
                try:
                    LOG_NOTE("[BATTLE] Calling startVisual for vehID=%d isPlayer=%s" % (vehID, isPlayer))
                    veh.startVisual()
                    veh.isStarted = True
                    LOG_NOTE("[BATTLE] startVisual OK for vehID=%d" % vehID)
                    if isPlayer and getattr(veh, 'appearance', None):
                        try:
                            veh.appearance.turretMatrix.target = self.playerAvatar.gunRotator.turretMatrix
                            veh.appearance.gunMatrix.target    = self.playerAvatar.gunRotator.gunMatrix
                            LOG_NOTE("[BATTLE] turretMatrix/gunMatrix linked to DummyGunRotator OK")
                            try:
                                self.playerAvatar.gunRotator.start()
                                LOG_NOTE("[BATTLE] gunRotator.start() OK")
                            except Exception as e:
                                LOG_NOTE("[BATTLE] gunRotator.start() failed: %s" % e)
                        except Exception as e:
                            LOG_NOTE("[BATTLE] matrix link failed: %s" % e)
                    elif not isPlayer and getattr(veh, 'appearance', None):
                        self._linkBotTurret(vehID, veh)
                    flt = getattr(veh, 'filter', None)
                    LOG_NOTE("[BATTLE] After startVisual: filter=%s type=%s" % (flt, type(flt).__name__ if flt else 'None'))
                except Exception as e:
                    veh.isStarted = True
                    LOG_ERROR("[BATTLE] startVisual FAILED for vehID=%d: %s" % (vehID, e))

            if isPlayer:
                flt = getattr(veh, 'filter', None)
                if flt is not None:
                    try:
                        flt.allowStrafeCompensation = False
                        flt.allowLagProcessing = False
                        try:
                            if hasattr(veh, 'appearance') and veh.appearance:
                                modelsDesc = getattr(veh.appearance, 'modelsDesc', None)
                                if modelsDesc and 'chassis' in modelsDesc:
                                    model = modelsDesc['chassis'].get('model')
                                    if model and not hasattr(model, 'wg_fashion'):
                                        model.wg_fashion = type('FakeFashion', (), {
                                            'setTrackTraces': lambda *a, **kw: None,
                                            'receiveShotImpulse': lambda *a, **kw: None,
                                            'hideTracks': lambda *a, **kw: None,
                                            'movementInfo': flt.movementInfo,
                                            'staticPitchSwingForce': 0.0,
                                            'disableSwinging': False,
                                        })()
                                        LOG_NOTE("[BATTLE] FakeFashion injected into chassis model OK")
                        except Exception as e:
                            LOG_NOTE("[BATTLE] FakeFashion inject failed: %s" % e)
                        LOG_NOTE("[BATTLE] WGVehicleFilter configured OK for player veh %d (type=%s)" % (vehID, type(flt).__name__))
                    except Exception as e:
                        LOG_NOTE("[BATTLE] WGVehicleFilter config failed: %s" % e)
                else:
                    LOG_ERROR("[BATTLE] CRITICAL: filter=None for PLAYER veh %d after startVisual! Movement will NOT work!" % vehID)

        self.arena.onPeriodChange += self._onPeriodChange
        PREBATTLE_DURATION = 28.0
        self._setPrebattleTimer(PREBATTLE_DURATION)

        def _unlock_movement():
            if self._stopped:
                LOG_NOTE("[BATTLE] _unlock_movement: battle already finished, skipping")
                return
            self._battleStarted = True
            try:
                if self.playerAvatar and getattr(self.playerAvatar, 'inputHandler', None):
                    self.playerAvatar.inputHandler._AvatarInputHandler__isArenaStarted = True
                    LOG_NOTE("[BATTLE] __isArenaStarted forced True by prebattle timer - turret UNLOCKED")
            except Exception as e:
                LOG_NOTE("[BATTLE] Failed to force __isArenaStarted in _unlock_movement: %s" % e)
            LOG_NOTE("[BATTLE] Prebattle timer elapsed (%.1fs) - movement UNLOCKED" % PREBATTLE_DURATION)
            _play_sound_event('battle_start')
        BigWorld.callback(PREBATTLE_DURATION, _unlock_movement)

        BigWorld.worldDrawEnabled(True)
        def _safeShowBattle():
            if self._stopped:
                return
            g_windowsManager.showBattle()
        BigWorld.callback(1.5, _safeShowBattle)

        try:
            import MusicController as _MC
            import SoundGroups
            mc = _MC.g_musicController
            if mc:
                mc.stop()
                LOG_NOTE("[BATTLE] MusicController: stopped lobby music OK")
            SoundGroups.g_instance.enableSounds('arena', True)
            LOG_NOTE("[BATTLE] SoundGroups: arena sounds enabled OK")
        except Exception as e:
            LOG_NOTE("[BATTLE] Music init failed: %s" % e)

        def _startBattleMusic():
            if self._stopped:
                return
            try:
                import MusicController as _MC
                mc = _MC.g_musicController
                if mc is None:
                    return
                arena = self.playerAvatar.arena
                if arena is None:
                    return
                arenaType = arena.typeDescriptor
                import FMOD
                ambientName = getattr(arenaType, 'ambientSound', None)
                if ambientName:
                    snd = FMOD.getSound(ambientName)
                    if snd:
                        snd.play()
                        self._battleAmbientSound = snd
                        LOG_NOTE("[BATTLE] Arena ambient started: %s" % ambientName)
                musicName = getattr(arenaType, 'music', None)
                if musicName:
                    snd = FMOD.getSound(musicName)
                    if snd:
                        snd.play()
                        self._battleMusicSound = snd
                        LOG_NOTE("[BATTLE] Arena music started: %s" % musicName)
            except Exception as e:
                LOG_NOTE("[BATTLE] _startBattleMusic failed: %s" % e)

        BigWorld.callback(1.0, _startBattleMusic)
        
        LOG_NOTE("[BATTLE] showBattle called")

        BigWorld.callback(0.05, self.__movementTick)
        BigWorld.callback(0.5, self.__botAITick)
        BigWorld.callback(0.5, self.__captureTick)
        BigWorld.callback(0.1, self._targetMarkerTick)
        from gui.Cursor import forceShowCursor
        forceShowCursor(True)
        BigWorld.callback(0.5, self._fixTankIndicator)
        BigWorld.worldDrawEnabled(True)
        self.playerAvatar.onAvatarReady()
        g_playerEvents.onAvatarReady()
        LOG_NOTE("[BATTLE] onAvatarReady fired OK")

        BigWorld.callback(0.5, self._updateBattleUI)
        BigWorld.callback(1.5, self._startMinimap)
        BigWorld.callback(1.0, self._setupAmmoPanel)

        def switch_to_battle():
            if self._stopped:
                LOG_NOTE("[BATTLE] switch_to_battle: battle already finished, skipping")
                return
            if getattr(self, '_periodSwitchSent', False):
                return
            self._periodSwitchSent = True
            LOG_NOTE("[BATTLE] Switching arena period to BATTLE")
            _prebattle = getattr(constants, 'ARENA_PERIOD_PREBATTLE', getattr(getattr(constants, 'ARENA_PERIOD', None), 'PREBATTLE', 1))
            if self.arena.period == _prebattle:
                _battle = getattr(constants, 'ARENA_PERIOD_BATTLE', getattr(constants.ARENA_PERIOD, 'BATTLE', 2))
                _upd = getattr(constants, 'ARENA_UPDATE_PERIOD', getattr(constants.ARENA_UPDATE, 'PERIOD', 3))
                battle_period_data = (_battle, BigWorld.time(), 1800.0, None)
                self.arena.update(_upd, cPickle.dumps(battle_period_data))
        BigWorld.callback(PREBATTLE_DURATION, switch_to_battle)

        LOG_NOTE("[BATTLE] _finalizeInit completed successfully!")

    def _onPeriodChange(self, period, periodEndTime, periodLength, addInfo):
        LOG_NOTE("[BATTLE] _onPeriodChange: period=%d periodLength=%.1f" % (period, periodLength))
        if self.playerAvatar and getattr(self.playerAvatar, 'inputHandler', None):
            _battle = getattr(constants, 'ARENA_PERIOD_BATTLE', getattr(constants.ARENA_PERIOD, 'BATTLE', 2))
            self.playerAvatar.inputHandler._AvatarInputHandler__isArenaStarted = (period == _battle)
            if period == _battle:
                self._battleStarted = True
            if period == _battle and not getattr(self, '_periodChangeBattleHandled', False):
                self._periodChangeBattleHandled = True
                LOG_NOTE("[BATTLE] Period changed to BATTLE — enabling controls")
                try:
                    from AvatarInputHandler import aims
                    if self.playerAvatar.vehicleTypeDescriptor:
                        max_health = self.playerAvatar.vehicleTypeDescriptor.maxHealth
                        aims._g_aimState['health']['cur'] = max_health
                        aims._g_aimState['health']['max'] = max_health
                except:
                    pass
                try:
                    if self.playerAvatar.playerVehicleID is None:
                        self.playerAvatar.playerVehicleID = self.vehicles[0][0]
                        LOG_NOTE("[BATTLE] Restored playerVehicleID after period change")

                    try:
                        self.playerAvatar.inputHandler._AvatarInputHandler__isArenaStarted = True
                        LOG_NOTE("[BATTLE] __isArenaStarted forced True")
                    except Exception as e:
                        LOG_NOTE("[BATTLE] Could not force __isArenaStarted: %s" % e)

                    _saved_bind = self.playerAvatar.bindToVehicle
                    self.playerAvatar.bindToVehicle = lambda *a, **kw: None
                    try:
                        self.playerAvatar.inputHandler.onControlModeChanged('arcade')
                    finally:
                        self.playerAvatar.bindToVehicle = _saved_bind
                    LOG_NOTE("[BATTLE] onControlModeChanged done, bindToVehicle restored")

                    self.playerAvatar.bindToVehicle(True, self.playerAvatar.playerVehicleID)

                    veh = BigWorld.entity(self.playerAvatar.playerVehicleID)
                    if veh:
                        cam = BigWorld.camera()
                        if cam and hasattr(cam, 'target'):
                            cam.target = veh.matrix
                            LOG_NOTE("[BATTLE] Camera re-targeted after period change OK")
                        BigWorld.worldDrawEnabled(True)
                        self._updateBattleUI()
                        BigWorld.callback(0.5, self._fixTankIndicator)
                    else:
                        LOG_ERROR("[BATTLE] _onPeriodChange: player vehicle entity is None!")
                except Exception as e:
                    LOG_ERROR("[BATTLE] Failed to change control mode: %s" % e)

        _afterbattle = getattr(constants, 'ARENA_PERIOD_AFTERBATTLE', getattr(constants.ARENA_PERIOD, 'AFTERBATTLE', 3))
        if period == _afterbattle:
            LOG_NOTE("[BATTLE] Period AFTERBATTLE — finishing battle")
            self._finishBattle()

    def _finishBattle(self):
        if self._finish_called:
            LOG_NOTE("[BATTLE] _finishBattle: already finished, ignoring duplicate call")
            return
        self._finish_called = True
        LOG_NOTE("[BATTLE] _finishBattle called")
        self._stopped = True

        if self.arena is not None:
            try:
                self.arena.onPeriodChange -= self._onPeriodChange
            except Exception:
                pass

        try:
            snd = getattr(self, '_battleAmbientSound', None)
            if snd:
                snd.stop()
        except Exception:
            pass
        try:
            snd = getattr(self, '_battleMusicSound', None)
            if snd:
                snd.stop()
        except Exception:
            pass
        try:
            import SoundGroups
            SoundGroups.g_instance.enableSounds('arena', False)
        except Exception:
            pass
        try:
            import MusicController as _MC
            mc = _MC.g_musicController
            if mc:
                mc.start()
                LOG_NOTE("[BATTLE] MusicController: lobby music restarted OK")
        except Exception as e:
            LOG_NOTE("[BATTLE] Music restore on battle exit failed: %s" % e)

        self._hideCaptureUI()
        if self._marker_frame:
            try:
                for c in self._marker_frame.values():
                    GUI.mroot().delChild(c)
            except Exception:
                pass
            self._marker_frame = None
            self._marker_target_vehID = None
        if self.playerAvatar and getattr(self.playerAvatar, '_minimap', None):
            try:
                self.playerAvatar._minimap.destroy()
                self.playerAvatar._minimap = None
            except: pass
        if self.playerAvatar and getattr(self.playerAvatar, 'inputHandler', None):
            try:
                self.playerAvatar.inputHandler.stop()
            except: pass
        if self.playerAvatar and getattr(self.playerAvatar, 'gunRotator', None):
            try:
                self.playerAvatar.gunRotator.stop()
                self.playerAvatar.gunRotator.destroy()
            except: pass
        try:
            BigWorld.camera(None)
        except: pass

        for vehID, _, _ in self.vehicles:
            try:
                veh = BigWorld.entity(vehID)
                if veh and getattr(veh, 'isStarted', False):
                    veh.stopVisual()
                    veh.isStarted = False
            except Exception as e:
                LOG_NOTE("[BATTLE] Ignored error while stopping visual for %d: %s" % (vehID, e))
        for vehID, _, _ in self.vehicles:
            try:
                BigWorld.destroyEntity(vehID)
            except: pass

        if getattr(self, '_accountEntityID', None) is not None:
            try:
                BigWorld.destroyEntity(self._accountEntityID)
                LOG_NOTE("[BATTLE] Account entity %s destroyed" % self._accountEntityID)
            except Exception as e:
                LOG_NOTE("[BATTLE] Ignored error while destroying Account entity: %s" % e)
            self._accountEntityID = None

        if self.battleWindow:
            try:
                self.battleWindow.close()
            except: pass
            self.battleWindow = None

        if self.spaceID is not None:
            try:
                BigWorld.clearSpace(self.spaceID)
            except: pass
            try:
                BigWorld.releaseSpace(self.spaceID)
            except: pass
            self.spaceID = None

        BigWorld.player = lambda: self._oldPlayer
        LOG_NOTE("[BATTLE] Restored old player, returning to lobby")
        self.playerAvatar = None
        try:
            g_windowsManager.showLobby()
        except: pass

        try:
            g_playerEvents.onStatsResync()
            g_playerEvents.onInventoryResync()
            LOG_NOTE("[BATTLE] Hangar resync (stats+inventory) fired OK")
        except Exception as e:
            LOG_NOTE("[BATTLE] Hangar resync on battle exit failed: %s" % e)

        try:
            from Offline import Manager
            Manager._save_profile(force=True)
        except Exception as e:
            LOG_NOTE("[BATTLE] Profile save on battle exit failed: %s" % e)

        self._bot_descr_cache = {}
        self._bot_pool = None
        self.vehicles = []
        self._bot_ai = []
        self.arena = None
        try:
            import gc
            gc.collect()
        except Exception:
            pass

def start_offline_battle(arena_id=None):
    LOG_NOTE("[BATTLE] start_offline_battle called: arena_id=%s" % arena_id)
    if arena_id is None or arena_id == -1:
        try:
            from Offline import Manager
            arena_id = Manager._selected_arena or '05_prohorovka'
            LOG_NOTE("[BATTLE] Arena from Manager._selected_arena: '%s'" % arena_id)
        except Exception as e:
            LOG_NOTE("[BATTLE] Could not get arena from Manager: %s" % e)
            arena_id = '05_prohorovka'
    LOG_NOTE("[BATTLE] Final arena: '%s'" % arena_id)
    battle = OfflineBattle()
    battle.start(arena_id, botCount=1)