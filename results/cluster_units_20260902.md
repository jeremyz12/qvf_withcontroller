
### B31 cleaning: v2.0 smoc -> v2.2 smoc (576)
  n_items=576  n_chains=144
  item-level: Δ=+7.99pp  b=28/c=74  McNemar p=5.91e-06
  chain-level sign test: 36W/16L/92T  p=0.00779
  chain cluster bootstrap 95% CI: [+3.47, +12.67]pp
  TOST margin ±2.0pp (90% CI [+4.17,+11.98]): FAIL (not equivalent)
  TOST margin ±3.0pp (90% CI [+4.17,+11.98]): FAIL (not equivalent)
  TOST margin ±5.0pp (90% CI [+4.17,+11.98]): FAIL (not equivalent)

### B31 cleaning: v2.0 smoc -> v2.4 smoc (576)
  n_items=576  n_chains=144
  item-level: Δ=+7.81pp  b=31/c=76  McNemar p=1.6e-05
  chain-level sign test: 37W/19L/88T  p=0.0222
  chain cluster bootstrap 95% CI: [+2.95, +12.67]pp
  TOST margin ±2.0pp (90% CI [+3.65,+11.98]): FAIL (not equivalent)
  TOST margin ±3.0pp (90% CI [+3.65,+11.98]): FAIL (not equivalent)
  TOST margin ±5.0pp (90% CI [+3.65,+11.98]): FAIL (not equivalent)

### B32' gate: v2.4 -> D gate store (B'3 non-inferiority)
  n_items=576  n_chains=144
  item-level: Δ=-1.39pp  b=40/c=32  McNemar p=0.41
  chain-level sign test: 21W/21L/102T  p=1
  chain cluster bootstrap 95% CI: [-5.38, +2.43]pp
  TOST margin ±2.0pp (90% CI [-4.69,+1.74]): FAIL (not equivalent)
  TOST margin ±3.0pp (90% CI [-4.69,+1.74]): FAIL (not equivalent)
  TOST margin ±5.0pp (90% CI [-4.69,+1.74]): PASS equivalence

### B32' no-gate: v2.4 -> D raw store
  n_items=576  n_chains=144
  item-level: Δ=-18.40pp  b=126/c=20  McNemar p=5.41e-20
  chain-level sign test: 10W/66L/68T  p=2.96e-11
  chain cluster bootstrap 95% CI: [-23.09, -13.89]pp
  TOST margin ±2.0pp (90% CI [-22.40,-14.58]): FAIL (not equivalent)
  TOST margin ±3.0pp (90% CI [-22.40,-14.58]): FAIL (not equivalent)
  TOST margin ±5.0pp (90% CI [-22.40,-14.58]): FAIL (not equivalent)

### B32' read-side: v2.4 -> D read-only-self
  n_items=576  n_chains=144
  item-level: Δ=-9.90pp  b=84/c=27  McNemar p=5.46e-08
  chain-level sign test: 13W/49L/82T  p=4.82e-06
  chain cluster bootstrap 95% CI: [-14.41, -5.73]pp
  TOST margin ±2.0pp (90% CI [-13.54,-6.25]): FAIL (not equivalent)
  TOST margin ±3.0pp (90% CI [-13.54,-6.25]): FAIL (not equivalent)
  TOST margin ±5.0pp (90% CI [-13.54,-6.25]): FAIL (not equivalent)

### B32' gate vs no-gate (recovery)
  n_items=576  n_chains=144
  item-level: Δ=+17.01pp  b=32/c=130  McNemar p=3.26e-15
  chain-level sign test: 67W/15L/62T  p=5.26e-09
  chain cluster bootstrap 95% CI: [+11.63, +22.22]pp
  TOST margin ±2.0pp (90% CI [+12.50,+21.35]): FAIL (not equivalent)
  TOST margin ±3.0pp (90% CI [+12.50,+21.35]): FAIL (not equivalent)
  TOST margin ±5.0pp (90% CI [+12.50,+21.35]): FAIL (not equivalent)
