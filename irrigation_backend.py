# ============================================================
# Smart Irrigation System (AI Model Version)
# ============================================================

# ----------- Import Libraries -----------
import warnings
warnings.filterwarnings("ignore")

import time, math, statistics, csv, os
from collections import deque
from datetime import datetime, timezone
import numpy as np
import joblib
import RPi.GPIO as GPIO
import spidev, board, adafruit_dht
import shared_data # تم إضافة هذا السطر للربط مع الـ Backend


# ----------- User Settings -----------
MODEL_PATH = "models/irrigation_model_merged.pkl"
RELAY_PIN = 17
ACTIVE_HIGH = True      
DRY_RUN = False         
SOIL_CH = 0

WET = 233               
DRY = 619               

THRESH_OVERRIDE = None
EMERGENCY_ON_PCT = 20.0 

BURST_ON_SEC = 4
REST_SEC = 5
MIN_ON_SEC = 6
MIN_OFF_SEC = 3
MAX_ON_SEC = 60
MAX_MIN_PER_HOUR = 8
HOURLY_BUCKET = 3600


# ----------- Load AI Model -----------
try:
    bundle = joblib.load(MODEL_PATH)
    MODEL = bundle["model"]
    FEATURES = bundle["features"]
    THRESH  = bundle.get("threshold", 0.06)
    if THRESH_OVERRIDE is not None:
        THRESH = float(THRESH_OVERRIDE)
except Exception as e:
    print(f"ERROR: Could not load AI model from {MODEL_PATH}. Using default threshold. Error: {e}")
    MODEL = None
    THRESH = 0.06


# ----------- Hardware Setup -----------
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT, initial=GPIO.LOW if ACTIVE_HIGH else GPIO.HIGH)

def relay_set(on: bool):
    if DRY_RUN:
        return
    if ACTIVE_HIGH:
        GPIO.output(RELAY_PIN, GPIO.HIGH if on else GPIO.LOW)
    else:
        GPIO.output(RELAY_PIN, GPIO.LOW if on else GPIO.HIGH)

# MCP3008 ADC
spi = spidev.SpiDev()
spi.open(0,0)
spi.max_speed_hz = 135000
spi.mode = 0

def read_adc(ch=0):
    r = spi.xfer2([1,(8+ch)<<4,0])
    return ((r[1]&3)<<8)|r[2]

def adc_to_pct(v, wet=WET, dry=DRY):
    v = max(min(v, dry), wet)
    return round(100.0*(dry - v)/(dry - wet), 1)

# DHT22 Sensor
dht = adafruit_dht.DHT22(board.D4)

def read_dht_safe():
    try:
        t = dht.temperature
        h = dht.humidity
        if (t is not None) and (h is not None):
            return float(t), float(h)
    except Exception:
        pass
    return None, None


# ----------- Helper Functions -----------
def vpd_kpa(temp_c, rh):
    if (temp_c is None) or (rh is None): return None
    es = 0.6108 * math.exp((17.27*temp_c)/(temp_c+237.3))
    ea = es * (rh/100.0)
    return es - ea


# ----------- Filters and Buffers -----------
MEDIAN_N = 9
AVG_WINDOW = 12
buf = deque(maxlen=AVG_WINDOW)
last_soil = None
last30 = deque(maxlen=30)

# ----------- Status Variables -----------
pump_on = False
last_change = time.time()
on_start = 0.0
rest_until = 0.0
hour_window_start = time.time()
run_sec_this_hour = 0


# ----------- Logging Setup -----------
logfile = "ai_irrigation_log.csv"
print(f"Smart AI Irrigation Started | THRESH={THRESH:.3f} | ACTIVE_HIGH={ACTIVE_HIGH} | DRY_RUN={DRY_RUN}\n")
with open(logfile, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp","temp_C","hum_%","vpd","adc_raw","soil_%","soil_ma","delta_soil","proba","decision","reason","pump_on"])

    try:
        while True:
            now = time.time()
            if now - hour_window_start >= HOURLY_BUCKET:
                hour_window_start = now
                run_sec_this_hour = 0

            vals = [read_adc(SOIL_CH) for _ in range(MEDIAN_N)]
            med = int(statistics.median(vals))
            buf.append(med)
            adc_smooth = sum(buf)//len(buf)
            soil = adc_to_pct(adc_smooth)

            temp, hum = read_dht_safe()
            vpd = vpd_kpa(temp, hum)
            hour = int(datetime.now(timezone.utc).strftime("%H"))
            sin_h = math.sin(2*math.pi*hour/24.0)
            cos_h = math.cos(2*math.pi*hour/24.0)

            last30.append(soil)
            soil_ma = sum(last30)/len(last30)
            delta = 0.0 if last_soil is None else soil - last_soil
            last_soil = soil

            # تجهيز مدخلات الذكاء الصناعي
            row = {
                "temperature_C":      temp if temp is not None else 25.0,
                "humidity_air_%":     hum  if hum  is not None else 50.0,
                "soil_moisture_%":    soil,
                "hour":               hour,
                "sin_hour":           sin_h,
                "cos_hour":           cos_h,
                "soil_moisture_ma":   soil_ma,
                "delta_soil":         delta,
                "vpd_kPa":            vpd if vpd is not None else 1.0,
            }
            
            # تشغيل التوقع
            proba = 0.0
            if MODEL:
                X = np.array([[row.get(f, 0.0) for f in FEATURES]], dtype=float)
                proba = float(MODEL.predict_proba(X)[0,1])

            # اتخاذ القرار
            decision_ai = (proba >= THRESH)
            decision_emg = (soil <= EMERGENCY_ON_PCT)
            decision_on = decision_ai or decision_emg
            reason = "AI" if decision_ai else ("EMERGENCY" if decision_emg else "NO")
            in_rest = now < rest_until

            # تشغيل الري
            if (not pump_on) and decision_on and (not in_rest) and (now-last_change)>=MIN_OFF_SEC:
                if (run_sec_this_hour/60.0) < MAX_MIN_PER_HOUR:
                    relay_set(True)
                    pump_on=True
                    on_start=now
                    last_change=now

            # إيقاف بعد مدة
            if pump_on and (now - last_change) >= MIN_ON_SEC and ((now - on_start) >= BURST_ON_SEC):
                relay_set(False)
                pump_on=False
                last_change=now
                rest_until = now + REST_SEC

            # قاطع أمان
            if pump_on and (now - on_start) >= MAX_ON_SEC:
                relay_set(False)
                pump_on=False
                last_change=now
                rest_until = now + REST_SEC

            if pump_on:
                run_sec_this_hour = min(HOURLY_BUCKET, run_sec_this_hour + 1)

            # ----------------------------------------------------------------------
            # تحديث حالة البيانات المشتركة (Shared Data) للـ API
            # ----------------------------------------------------------------------
            shared_data.latest_status.update({
                "timestamp": datetime.now().strftime('%H:%M:%S'),
                "temperature": temp,
                "humidity": hum,
                "soil_pct": round(soil, 1),
                "proba": round(proba, 3),
                "pump_on": pump_on,
                "reason": reason,
                "run_sec_this_hour": run_sec_this_hour,
                "delta_soil": round(delta, 2)
            })
            # ----------------------------------------------------------------------
            
            # تسجيل وطباعة
            writer.writerow([
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                temp, hum, round(vpd,3) if vpd is not None else "",
                med, round(soil,1), round(soil_ma,1), round(delta,2),
                round(proba,3), int(decision_on), reason, int(pump_on)
            ])
            f.flush()

            # إخراج منسّق للطرفية
            print(f"{datetime.now().strftime('%H:%M:%S')} | "
                  f"T:{temp if temp else 'NA'}°C H:{hum if hum else 'NA'}% "
                  f"ADC:{med} Soil:{soil:.1f}% p={proba:.3f} -> "
                  f"{'🟢 ON' if pump_on else '⚪ OFF'} [{reason}]")

            time.sleep(1.5)

    except KeyboardInterrupt:
        pass
    finally:
        relay_set(False)
        GPIO.cleanup()
        spi.close()
        print("\nSystem stopped safely.\n")
