# System Design Review — Micro Sheet (`micro.kicad_sch`), Rev B in progress

**Date:** 2026-08-31 · Reviewer: Claude (systems review) · Requested by: Jason

Scope: the microcontroller sheet — ESP32-D0WD-V3 (U1), SPI flash (U6), CH340K USB-UART (U2),
auto-boot transistor (Q1), 40 MHz crystal (Y1), RF match (ANT1/L1/C37/C38), boot strapping, EN/reset
network, I²C pull-ups, and the two firmware LEDs. This pass follows the completion of the power sheet,
so it pays special attention to the **micro↔power interface** the power work created.

---

## 0. How this review was done

Ground truth is the exported netlist, not the schematic PDF or memory.

| Checked | Against | How |
|---|---|---|
| Full-project connectivity | `bluetooth-audio.kicad_sch` → kicad-cli netlist | `kicad-cli sch export netlist --format kicadxml`, then `parse_netlist.py` (comp / nets / floating / bom) |
| ERC state | KiCad 10 ERC | `kicad-cli sch erc` → 92 violations, triaged below |
| ESP32 pin functions / strapping | `hw/datasheets/esp32_datasheet_en.pdf`; `hw/app notes/esp-hardware-design-guidelines-en-master-esp32.pdf` | pin-by-pin against the netlist map |
| Flash IO mapping | `hw/datasheets/...W25Q32JVZPIQ_C571260.pdf` (rev G) | SPIWP/SPIHD ↔ IO2/IO3 |
| CH340 TXD/RXD direction + 3.3 V supply | WCH CH340 datasheet v3B — downloaded to `hw/datasheets/WCH-CH340-datasheet-v3B.pdf` | pin direction and V3/VCC config |

**Confidence labels:** *Confirmed* = verified against netlist or a primary datasheet; *Estimated* =
calculated, arithmetic shown; *Needs bench check* = not settleable from documents.

**Errata:** the ESP32 has published errata (ECO/silicon anomalies). None of the findings below depend
on an erratum-sensitive area (they are connectivity, not silicon corner-cases), so a full errata pass
was deferred to the RF/bring-up review where it matters more. Flagged, not done.

**What I could not do:** local PDF page-rendering is unavailable in this environment, so ESP32/flash
pin-table citations are to the document and table by name, not page number. The connectivity claims do
not depend on that — they come from the netlist.

---

## 1. Corrections to previous conclusions

- **Design overview §9 and Delta #4 state the flash IO2/IO3 swap is "fixed in Rev B." It is not.**
  The netlist still has them crossed (Finding S1-2). The overview is describing an intended change
  that was never applied to the schematic. Corrected in the overview's "not yet on the schematic"
  list in this pass.
- **Session-log open question "what drives Rail A's `EN` pin?" is now answered by the schematic:**
  AP7361C `EN` (U7.1) is tied to `+V_SYS` — LDO A is always on. No firmware control. Recorded as
  resolved.

---

## 2. Headline findings

| # | Sev | Finding | Requirement / doc affected | Fix effort |
|---|---|---|---|---|
| S1-1 | **S1** | **CH340K UART wired straight-through, not crossed.** `UART_TX` ties ESP32 U0TXD (out) to CH340 TXD (out); `UART_RX` ties U0RXD (in) to CH340 RXD (in). Board cannot be flashed or use serial console. ERC misses it (ESP32 pin is bidirectional). | Programming/debug (§6) | Swap two nets |
| S1-2 | **S1**† | **Flash IO2/IO3 still crossed.** ESP32 SPIWP(GPIO9)→flash IO3; SPIHD(GPIO10)→flash IO2. Boots in DIO; corrupts every read in QIO/QOUT. Doc claims this was fixed. | Delta #4, §9 flash mode | Swap two nets |
| S1-3 | **S1** | **Digital rail orphaned.** ESP32/flash/CH340K sit on `+3V3`; LDO A output is `+3V3_SYS`. Two different global nets — the MCU has no regulator. (Known: overview §10.) | Power tree §2 | Rename/merge net |
| S1-4 | **S1** | **Whole micro↔power control/telemetry interface undrawn.** `EN1 EN2 /PGOOD /CHG BAT_ADC USB_CC1 USB_CC2 USB_VBUS_SENSE AUDIO_VCC_EN` and the CH340 gate reach no ESP32 pin. Charger uncontrollable, no SoC, no source detection, **codec rail can never turn on**. (Known: overview §10.) | §3.2–3.8, REQ-PWR-10 | Wire GPIOs; add labels |
| S2-1 | S2 | **TX/RX audio switch control undriven.** TS5A23159 `IN1`/`IN2` (U3.1/U3.5) float — no GPIO. TX mode (delta #9) has no way to select the path. GPIO map (§3.8) omits it. | REQ-AUD-07, §3.8 | 1 GPIO (tie IN1+IN2) |
| S2-2 | S2 | **Crystal load caps still 18 pF.** Delta #12 (→~15 pF) not applied. ~12 pF load on a 10 pF crystal → frequency pulled low, outside ±10 ppm before trim. | Delta #12, §7 | Change 2 values |
| S2-3 | S2 | **Firmware LED resistors still 1 kΩ.** D1 (blue, GPIO22/R12) and D3 (green, GPIO19/R18) at 1 kΩ. Blue draws ~0.3 mA → invisible. Delta #7 was applied to the power LEDs only. | Delta #7, §3.7 | Change 2 values |
| S3-1 | S3 | **Schematic hygiene:** 36 `lib_symbol_mismatch` (cached symbols ≠ library, from the library-repo move), 35 off-grid wire endpoints, 3 unconnected wire endpoints, annotation errors on export. Off-grid/dangling endpoints can silently drop connections. | — | ERC cleanup pass |
| S3-2 | S3 | **Rail naming is inconsistent across three schemes:** doc (`SYS`/`3V3_A`/`3V3_B`) vs schematic (`+V_SYS`/`+3V3_SYS`/`+3V3_AUDIO`) vs micro (`+3V3`). | §2 rails | Pick one; align doc |

† S1-2 is severity-S1 by *impact if QIO is enabled* but hides through bring-up in DIO — the dangerous
kind. Treat as fix-before-order.

---

## 3. Subsystem review

### 3.1 What is RIGHT (record so it is not "optimised" away)

- **ESP32 `CAP1` has its required 10 nF** (`C45`, to GND). Delta #3 / prior-review S1 fix — *applied*.
  Confirmed (netlist). `CAP2` correctly left open (deep-sleep only).
- **Strapping pins handled correctly.** MTDI/GPIO12 (VDD_SDIO select) carries a **DNP** pull-up
  (`R26` to +3V3) — the designer recognised that populating it would select 1.8 V and brick the 3.3 V
  flash. GPIO0/GPIO2/GPIO15 rely on the ESP32's internal pulls in the safe direction. GPIO0 doubles
  as MCLK; the codec's MCLK input is high-Z at reset, so the strap is not disturbed. Confirmed
  (netlist + ESP32 datasheet strapping table). **Recommend annotating `R26 = DNP – 1.8 V select, do
  not populate` on the schematic** so nobody fits it later.
- **Auto-boot circuit topology is the canonical cross-coupled one.** Q1A: collector→`EN`,
  emitter→`RTS`, base←`DTR` (via R1). Q1B: collector→`GPIO0`, emitter→`DTR`, base←`RTS` (via R2). This
  is the standard DTR/RTS reset/boot circuit that avoids the both-asserted deadlock. Confirmed
  (netlist). Exact polarity is a bench/firmware item, but the wiring is right.
- **Flash core SPI lines correct:** CS↔GPIO11, CLK↔GPIO6, IO0(DI)↔GPIO8(SPID), IO1(DO)↔GPIO7(SPIQ).
  Only IO2/IO3 are crossed (S1-2). Confirmed (netlist + W25Q32JV rev G pin table).
- **RF Pi-match topology correct:** LNA_IN — C37 (shunt) — L1 2.2 nH (series) — C38 (shunt) — antenna,
  all shunts to GND. Values are placeholders to be tuned on measured S11. Confirmed (netlist).
- **Codec ADC data (`ASDOUT`) correctly on input-only GPIO35.** Confirmed.
- **I²C:** 4.7 kΩ pull-ups to +3V3 on SDA(GPIO23)/SCL(GPIO18); test points present. Correct.
- **EN/reset:** 10 kΩ pull-up + 1 µF (≈10 ms), test point, DNP manual-reset resistor. Correct.
- **CH340K 3.3 V supply config correct:** V3 tied to VCC with external 3.3 V, per CH340 datasheet v3B.

### 3.2 The micro↔power interface (the seam the power work opened)

The power sheet is complete and internally correct — EN1 pulled to `+V_SYS` via 100 kΩ (`R30`), EN2 to
GND via 100 kΩ (`R31`), `/PGOOD`//`CHG` open-drain, the ADC dividers and VBUS-sense tap all built. But
**none of it lands on the ESP32.** Every one of these is a global label with a single node on the
micro side, or a GPIO left unconnected:

| Power-sheet signal | Netlist state | Intended ESP32 pin (§3.8) | ESP32 pin actual |
|---|---|---|---|
| `+3V3` (should be LDO A out) | separate net from `+3V3_SYS` | — | VDD pins on orphaned `+3V3` |
| `EN1` | R30 + U9.6 only | GPIO16 | GPIO16 unconnected |
| `EN2` | R31 + U9.5 only | GPIO17 | GPIO17 unconnected |
| `/PGOOD` | D5 + U9.7 only | any input | not present on U1 |
| `/CHG` | D6 + U9.9 only | any input | not present on U1 |
| `BAT_ADC` | R34/R35/C52 only | ADC1 | not present on U1 |
| `USB_CC1` | R36 only (1-node) | ADC1 | not present on U1 |
| `USB_CC2` | R37 only (1-node) | ADC1 | not present on U1 |
| `USB_VBUS_SENSE` | R38/R39/C53 only | ADC1 | not present on U1 |
| `AUDIO_VCC_EN` | R33 (pulldown) + U11.3 | any GPIO | **not driven → codec rail dead** |
| CH340 gate | *no switch drawn* | any GPIO | CH340 hard-wired to `+3V3` |

`AUDIO_VCC_EN` is the sharp one: it is pulled low by `R33` so the codec LDO is off at boot (correct
intent), but with no GPIO to raise it the codec rail **can never turn on**. Confirmed (netlist +
ERC `isolated_pin_label` on USB_CC1/CC2, `pin_not_driven` on the switch).

### 3.3 GPIO budget — the §3.8 map needs redoing

§3.8 claims "four output-capable pins free (GPIO4/16/17/21) against exactly four outputs — no slack."
Two things are off:

1. **It omits the TX/RX audio switch** (S2-1), which needs a GPIO. That makes it *five* outputs:
   EN1, EN2, AUDIO_VCC_EN, CH340 gate, audio-switch.
2. **It undercounts free outputs.** GPIO5 (unconnected) and GPIO2 (only a test point) are also
   output-capable, and GPIO32/33 are output-capable ADC1 pins. So there is slack after all.

Re-derived budget (Estimated, from the netlist GPIO map):
- **Outputs needed (5):** EN1, EN2, AUDIO_VCC_EN, CH340 gate, audio switch → GPIO4, 16, 17, 21, **5**.
- **Digital inputs (2):** /PGOOD, /CHG → any two spare input pins.
- **ADC1 inputs (4):** BAT_ADC, USB_CC1, USB_CC2, USB_VBUS_SENSE → four of GPIO36/37/38/39/34/32/33.

Feasible, but tight, and GPIO5/GPIO2 are strapping pins — only use them as outputs *after* boot and
keep them from being driven at reset. This should be written into the map, not left implicit.

### 3.4 Cross-cutting

- **Programming path is dead on two counts** (S1-1 UART swap; the auto-boot circuit is fine but
  useless if TX/RX is crossed). Because no board has been assembled, neither has surfaced.
- **Crystal:** `R13 = 0 Ω` sits in series on the XTAL_P leg between the amp and C35/Y1 — a legitimate
  drive-level tuning provision, harmless at 0 Ω. Note the asymmetry (nothing on the XTAL_N leg) if you
  ever fit a non-zero value. Load caps at 18 pF are the real issue (S2-2).
- **RF supply decoupling:** +3V3 carries a 10 µF bulk + 1 µF + several 100 nF for seven ESP32 VDD
  pins — adequate, but *Needs bench check* against the ESP32 HW guidelines' RF-supply filtering once
  the rail is unified. Not a blocking finding.

---

## 4. Part-by-part (micro sheet)

| Part | Role | Verdict |
|---|---|---|
| **ESP32-D0WD-V3** (U1) | MCU + BT Classic radio | Correct part per §5 rationale. Connectivity mostly right; power + control interface incomplete (S1-3, S1-4). |
| **W25Q32JV** (U6) | 4 MB flash | Right part (JV = 3.3 V). IO2/IO3 crossed (S1-2). |
| **CH340K** (U2) | USB-UART bridge | Right part; TXD/RXD swapped (S1-1); no load switch yet (S1-4). Datasheet now in repo. |
| **UMH3N** (Q1) | Dual digital transistor, auto-boot | Correct topology. Built-in base resistors + external R1/R2 give ~20 kΩ series base — fine for high-impedance CMOS loads. |
| **Y1** 40 MHz | RF reference | Right part; load caps mis-derived (S2-2). ±10 ppm requires a frequency-offset measurement to close. |

---

## 5. Requirements impact

- **REQ-PWR-10 (state of charge)** is not achievable as drawn — `BAT_ADC` reaches no ADC pin (S1-4).
- **REQ-AUD-07 (TX mode)** is not achievable as drawn — the path switch has no control GPIO (S2-1).
- **Programming/debug** (implicit product requirement) fails as drawn (S1-1).
- **Indicator visibility** (the human-factors requirement behind delta #7) not met for the blue LED
  (S2-3).
- **Proposed new requirement:** *"USB-C VBUS/serial bring-up must be validated on the first assembled
  board before any layout is committed to a second run."* Two independent flash-path defects
  (S1-1, S1-2) both survived because nothing was ever assembled — the process gap is the root cause.

---

## 6. Prioritised action list

**Fix before layout (defects, not decisions):**
1. Swap `UART_TX`/`UART_RX` so CH340 TXD→ESP32 U0RXD and CH340 RXD→ESP32 U0TXD. (S1-1)
2. Swap flash `SD2`/`SD3` so SPIWP(GPIO9)→IO2 and SPIHD(GPIO10)→IO3. (S1-2)
3. Merge `+3V3` (micro) with `+3V3_SYS` (LDO A output). (S1-3)
4. Wire the power interface to the ESP32: EN1, EN2, /PGOOD, /CHG, BAT_ADC, USB_CC1/2, VBUS_SENSE,
   AUDIO_VCC_EN, CH340 gate + load switch. (S1-4)
5. Add the TX/RX switch control GPIO (tie U3 IN1+IN2). (S2-1)
6. Crystal caps 18 pF → ~15 pF. (S2-2)
7. D1/D3 (R12/R18) 1 kΩ → 330 Ω; consider ~150 Ω or a lower-Vf part for the blue. (S2-3)
8. ERC cleanup: resync library symbols, snap endpoints to grid, re-annotate. (S3-1)

**Decisions needed from you (scope/choice, not bugs):**
- The GPIO map (§3.8) needs re-drawing to include the audio switch — confirm the pin assignment so
  firmware and schematic agree. Recommendation in §3.3 above.
- Rail naming scheme to standardise on (recommend adopting the schematic's `+V_SYS`/`+3V3_SYS`/
  `+3V3_AUDIO` and renaming the doc's `3V3_A`/`3V3_B` to match). (S3-2)

**Cheap wins:** items 6, 7, and annotating `R26 = DNP` while the schematic is open.

---

## 7. Overall assessment

The pattern is not bad component choices — every part is right for its job. It is **an unclosed
integration seam plus two classic mirror-image wiring swaps that ERC cannot see.**

The power sheet was finished as a self-contained block, and the obligations it created on the micro
side (a dozen signals, a rail rename, a load switch) were left for "later" — which is fine as staged
work, but the design overview drifted ahead of the schematic and now describes fixes (flash swap) and
a GPIO budget that the board does not have. The two swaps (UART TX/RX, flash IO2/IO3) are the textbook
defects this kind of review exists to catch: both pass ERC, both hide through early bring-up, and both
only bit because *nothing has been assembled yet* — which is exactly why they are cheap to fix now and
expensive to fix on copper.
