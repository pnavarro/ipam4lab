#!/usr/bin/env python3
"""Reproduce the allocate-after-deallocate failure against a local SQLite DB.

Usage: test_ipam_bug.py <path to ipam4lab checkout>
Imports app.py from the checkout and drives IPAMManager directly, so it never
touches the deployed service.
"""
import importlib.util, os, sys, tempfile, sqlite3

repo = sys.argv[1]
spec = importlib.util.spec_from_file_location("ipamapp", os.path.join(repo, "app.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["ipamapp"] = mod
spec.loader.exec_module(mod)

db = os.path.join(tempfile.mkdtemp(), "ipam.db")
ipam = mod.IPAMManager(db, "192.168.0.0/16")
CL = "testcluster"

a1 = ipam.allocate_lab_network("lab-one", CL)
print("1. allocate lab-one        ->", a1["external_ip_worker_1"])

ipam.deallocate_lab_network("lab-one", CL)
rows = sqlite3.connect(db).execute(
    "SELECT COUNT(*) FROM ip_tracking WHERE cluster = ?", (CL,)).fetchone()[0]
print(f"2. deallocate lab-one      -> ip_tracking rows left for cluster: {rows}")

try:
    a2 = ipam.allocate_lab_network("lab-two", CL)
    print("3. allocate lab-two        ->", a2["external_ip_worker_1"], " PASS")
except sqlite3.IntegrityError as e:
    print(f"3. allocate lab-two        -> IntegrityError: {e}  => HTTP 500   FAIL")
    sys.exit(1)
except Exception as e:
    print(f"3. allocate lab-two        -> {type(e).__name__}: {e}   FAIL")
    sys.exit(1)

a3 = ipam.allocate_lab_network("lab-three", CL)
print("4. allocate lab-three      ->", a3["external_ip_worker_1"], " PASS")
assert a3["external_ip_worker_1"] != a2["external_ip_worker_1"], "handed out the same IP twice"
print("\nall good: a released IP is reusable and no duplicate was handed out")
