# Template (fill @...@ and run via z2run.py). Root on Z2: record the OWNER's
# on-site electrical attestation for ONE Site. This is NOT a voltage
# measurement; only write it after the owner has confirmed supply, common
# ground, 3.3 V signalling and the exact PMOD connector on site.
import json, os, time
SITE=int("@SITE@"); CONNECTION="@CONNECTION@"; SOURCE="@SOURCE@"
d="/root/plasma-swd-electrical"; p=f"{d}/site{SITE}-attestation.json"
os.makedirs(d,mode=0o700,exist_ok=True); os.chown(d,0,0); os.chmod(d,0o700)
now=int(time.time())
a={"schema":"plasma.swd.owner-electrical-attestation.v1","site_id":SITE,
   "kind":"OWNER_ON_SITE_ATTESTATION","measurement":False,
   "dut":"Blue Pill STM32F103 (expected DPIDR 0x1BA01477)",
   "connection":CONNECTION,
   "dut_supply_ok":True,"common_ground_ok":True,"signal_level_v":3.3,"wiring_ok":True,
   "attested_by":"PLASMA owner, on site","source":SOURCE,
   "created_epoch":now,"expires_epoch":now+4*3600}
tmp=p+".tmp"; fd=os.open(tmp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY|os.O_NOFOLLOW,0o600)
os.write(fd,(json.dumps(a,sort_keys=True,indent=1)+"\n").encode()); os.fsync(fd); os.close(fd)
os.replace(tmp,p); st=os.stat(p)
print("Z2JSON="+json.dumps({"path":p,"mode":oct(st.st_mode),"uid":st.st_uid,"expires_epoch":a["expires_epoch"]}))
