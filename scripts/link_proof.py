"""link_proof.py -- third wave (P1): before / after evidence of one pushover direction of an EBF job
(pushover/review.evidence): the largest one-step loss of base shear, the link rotation against (L/e) x drift at the
IS-DBE / IS-MCE targets, Te / T1, V / VB, and Vmax up to the IS-MCE target. Reads <job>/pushover_before (the October
package, copied aside before the re-run) and <job>/<new> (default pushover); runs no analysis.

    python scripts/link_proof.py <job> <X|Y> <L/e> [<new package folder>]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pushover import review as RV, vmax_policy as VP
job, d, le = sys.argv[1], sys.argv[2], float(sys.argv[3])
NEW = sys.argv[4] if len(sys.argv) > 4 else "pushover"
for tag in ("pushover_before", NEW):
    pkg = json.load(open("%s/%s/pushover_package.json" % (job, tag)))
    dd = pkg["directions"].get(d)
    if not dd:
        print(tag, "no direction", d); continue
    ev = RV.evidence(pkg, d, l_over_e=le)
    dr = ev.get("drop") or {}
    print("== %s %s: T1 %.3f s, Vmax %.0f kN at %.0f mm, curve end %.0f mm, stop: %s" % (
        tag, d, ev["T1"], ev["Vmax_kN"], ev["u_at_Vmax_mm"], ev["u_end_mm"], dd.get("stop_reason")))
    print("   largest one-step drop: %s" % ("%.0f%% at %.0f-%.0f mm (%.0f -> %.0f kN)" % (100 * dr["fraction"], dr["u_from_mm"], dr["u_to_mm"], dr["V_from_kN"], dr["V_to_kN"]) if dr else "none"))
    for lv, x in (ev.get("levels") or {}).items():
        print("   %s: dt %.1f mm reached=%s, Te %.3f s (Ki/Ke %.2f), V/VB %.2f, max drift %.3f %%, link rot %.4f rad vs (L/e) x drift %.4f, links yielded %s"
              % (lv, x["target_mm"], x["reached"], x["Te"], x["Ki_over_Ke"], x["V_over_VB"] or 0, 100 * (x["drift"] or 0),
                 x["link_rot"] or 0, x["link_rot_kinematic"] or 0, (x.get("census") or {}).get("links_yielded")))
    h = VP.vmax_to_target(dd)
    print("   %s" % VP.headline_text(d, h))
    print("   %s" % (VP.peak_text(d, h) or "the headline point is the peak of the analysed curve"))
