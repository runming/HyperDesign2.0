import sys

sys.path.insert(0, r"D:\hyperdesign2\backend")
from app.cae.fem import HolePlateInput, hole_plate_solve

print("网格加密收敛性（理论上 Kt -> 3.0）")
for ns, nr in ((32, 4), (32, 8), (64, 16), (96, 24)):
    r = hole_plate_solve(HolePlateInput(hole_radius_mm=4.0, outer_radius_mm=40.0,
                                        thickness_mm=2.4, sectors=ns, rings=nr))
    m = r["mesh"]
    print(f"ns={ns:3d} nr={nr:3d} elems={m['elements']:5d}  Kt={r['stress_concentration_kt']:6.3f}  "
          f"sig_hoop={r['sigma_max_hoop_mpa']:7.3f}  sig_xx_max={r['sigma_max_xx_mpa']:7.3f}  "
          f"err={r['kt_error_pct']:5.1f}%")
