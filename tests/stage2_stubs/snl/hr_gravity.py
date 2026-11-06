import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import note

if __name__ == "__main__":
    job = sys.argv[1]
    from _common import fail_if_asked
    fail_if_asked('gravity')
    note(job, "gravity")
    json.dump(dict(schema=1, engine_sha="stub", engine=os.environ.get("STELTIC_ENGINE_DIR"), states={"D": 1.0}),
              open(os.path.join(job, "nl_hr_gravity.json"), "w"))
