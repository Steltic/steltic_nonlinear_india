import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import note

if __name__ == "__main__":
    assert sys.argv[1] == "report", sys.argv
    job = sys.argv[2]
    note(job, "report")
    open(os.path.join(job, "four_analyses.html"), "w").write("<html>four analyses</html>")
    json.dump(dict(status="COMPLETE", reasons=[]), open(os.path.join(job, "complete_gate.json"), "w"))
