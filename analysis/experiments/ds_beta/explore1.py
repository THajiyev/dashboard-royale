from models import *
run("B2 reproduction", b2_family())
for loc in ["median", "trim", "huber"]:
    run(f"loc={loc}", b2_family(loc=loc))
for hl in [14, 28, 56]:
    run(f"EW mean hl={hl}", b2_family(half_life=hl))
    run(f"EW median hl={hl}", b2_family(loc="median", half_life=hl))
for L in ["median", "ratio"]:
    run(f"lift={L}", b2_family(lift=L))
for s in [0.5, 0.75, 1.25]:
    run(f"lift shrink {s}", b2_family(lift_shrink=s))
run("LAD log", lad())
run("LAD log trend", lad(True))
run("LAD level", lad(log=False))
