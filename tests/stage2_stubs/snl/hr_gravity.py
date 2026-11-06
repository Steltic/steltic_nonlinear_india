import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import note

if __name__ == "__main__":
    job = sys.argv[1]
    from _common import fail_if_asked
    fail_if_asked('gravity')
    note(job, "gravity")
    states = {"D": 1.0}
    eng = os.environ.get("STELTIC_ENGINE_DIR")
    if os.environ.get("STUB_GRAVITY_FROM_ENGINE") and eng:     # an engine change that changes the gravity states
        states = {"D": float(len(open(os.path.join(eng, "engine3d.py"), "rb").read()))}
    json.dump(dict(schema=1, engine_sha="stub", engine=eng, states=states),
              open(os.path.join(job, "nl_hr_gravity.json"), "w"))
