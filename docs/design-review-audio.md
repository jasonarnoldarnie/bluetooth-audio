# System Design Review — Audio Sheet (`audio.kicad_sch`)

**Reviewer:** Claude (acting as reviewing systems engineer)
**Date:** 2026-09-07
**Design under review:** `hw/bluetooth-audio/audio.kicad_sch` — working tree (uncommitted changes present), netlist re-exported 2026-09-07 from `bluetooth-audio.kicad_sch`.
**Scope:** the audio subsystem only — ES8388 codec (U4), TX/RX analog switch (U3), MEMS microphone (MK1), the 3.5 mm jack (J1) and their support circuitry.

This review **re-audits the sheet from a fresh netlist** and supersedes the 2026-09-04 audio review. The sheet has changed materially since then — the coupling capacitors, the microphone part, and the jack are all different — so every claim below is re-derived from the current netlist, not carried over.

> **Update 2026-09-08 (post-fix re-check).** The four BAT54W discretes were replaced with **2× BAT54S** (D7/D8) — wiring verified correct on the netlist: **common (pin 3) → signal, anode → GND, cathode → AVDD**, off at the VMID idle point, no rail short (§3.4a now describes this). Mic DC-blocking caps set to **100 nF C0G** (Murata **C97946**, 1206); the pseudo-differential − reference (R41 0 Ω / C54 alt) is **DNP by deliberate provisioning** — JLC places both C0G caps (C41 +, C42 −) and R41 is the hand-fit enable — so **A9 is resolved as a design choice**, the only residual being that RIN1 floats in the default build (benign while the right ADC is powered down; fitting R41 removes it). **A3 (mic-cap dielectric) is closed** (now C0G). Cap sizing is written into the design overview §8. **A7 is now decided — line-level-only, PGA 0 dB** (§3.4/§5). Remaining is firmware-only: **A8** (mute across power-up / mode switch).

---

## 0. How this review was done

Connectivity comes from the exported KiCad netlist (`export_netlist` → `parse_netlist.py`, per-component pin maps). Every device claim is checked against the primary datasheet, cited by page/line.

| Evidence source | Revision / location | Used for |
|---|---|---|
| KiCad netlist export | working tree, 2026-09-07 | all connectivity |
| **ES8388 datasheet** | Everest Semiconductor Rev 5.0 — `hw/datasheets/1912111437_…ES8388_C365736.pdf` | pin functions, supply/level, analog I/O |
| **TI TS5A23159 datasheet** | SCDS201H, Feb 2015 — `hw/datasheets/TI-TS5A23159-SCDS201H.pdf` | pinout (§5 Pin Functions), Ron, break-before-make, THD, analog range |
| **ZillTek ZTS6216 datasheet** | DS-1.4 — `hw/datasheets/ZillTek-ZTS6216-DS1.4.pdf` | supply range, self-bias, PSRR, SNR, dielectric note, top-port |
| **XKB PJ-3537S datasheet** | C2689709 — `hw/datasheets/XKB-PJ-3537S-SMT-C2689709.pdf` | jack pinout (T/R/S + switch) |

**Confidence labels:** *Confirmed* = verified against a cited datasheet + the netlist. *Estimated* = my calculation, arithmetic shown. *Needs bench check* = cannot be settled from documents.

**Errata:** ES8388, TS5A23159 and ZTS6216 are analog/fixed-function parts without published errata. Nothing to reconcile.

**Note on the TS5A23159 truth table:** the pin-function table (SCDS201H §5) was extracted cleanly; the IN→NO/NC state table is a figure that did not machine-extract, so the RX/TX direction below is stated *Confirmed* on the basis of the pin functions plus system self-consistency (RX routes the codec's NC-pin outputs to the jack), and matches the datasheet reading in the prior review.

---

## 1. Status of the previous review's findings — four of seven now fixed

The 2026-09-04 review raised A1–A7. Re-audited against the current netlist:

| # | 2026-09-04 finding | Status now | Evidence |
|---|---|---|---|
| **A1** | Codec-rail gating back-powers the ES8388 via I²C pull-ups to +3V3_SYS | **FIXED (HW)** | `R19`/`R20` (4k7) now pull `I2C_CLK`/`I2C_DATA` to **+3V3_AUDIO** — they die with the codec rail. FW tri-state rule for the I²S lines remains (documented in overview §8). |
| **A2** | L/R swapped at the jack | **FIXED** | Left → Tip, Right → Ring — see §3.2. |
| **A4** | `RIN1`/MIC− floating | **Improved** | `U4.23` now carries an explicit **no-connect flag** (ERC-clean). Electrically still an unused input in single-ended mode (acceptable); the net is cosmetically mislabelled `MIC-` — see A4′. |
| **A6** | Jack still 4-pole TRRS | **FIXED** | `J1` is now **PJ-3537S** — a 3-pole TRS with a switched (detect) contact; `SW_NC` NC-flagged. |
| **A3** | Mic coupling cap dielectric (Class-2) | **OPEN** | `C41` still 100 nF **0402** → Class-II MLCC. ZTS6216 forbids it (§3.3). |
| **A5** | Single-ended mic decision undocumented | **OPEN (doc)** | Overview still describes a *differential* SPH8878 mic — now factually wrong; this pass fixes it. |
| **A7** | TX input full-scale ~1.0 V_RMS, no attenuator | **OPEN (decision)** | No divider present; jack → 10 Ω → 47 µF → switch → LIN2/RIN2 (§3.4). |

**And the coupling-capacitor subsystem was redesigned** (1 µF MLCC → 47 µF electrolytic + jack-side bleed) — reviewed as correct in §3.2, because the topology is subtle and worth showing.

---

## 2. Headline findings (current)

| # | Sev | Finding | Requirement | Fix effort |
|---|---|---|---|---|
| A3 | **S3** | Mic coupling `C41` (100 nF 0402) is a Class-II MLCC; the ZTS6216 datasheet (DS-1.4, p.4) states plainly *"Capacitors near the microphone should not contain Class 2 dielectrics."* | REQ-AUD-01/04 | C0G in a larger case, or film |
| **A9** | **S2** | Pseudo-differential mic input: as *populated*, RIN1 (the −) is **floating** — C22 is fitted but the parts that would connect RIN1 to the reference (R41, C23) are both DNP (§3.3a). The intended noise-rejection benefit is absent and an input floats. | REQ-AUD-04 | Populate one of R41 / C23 |
| A7 | **Decided** | TX input is **line-level-only** (≤ ~1 V_RMS), PGA at 0 dB. No attenuator — it would halve the common quieter sources and cost SNR to rescue a rare hot one; the BAT54S clamps are damage protection only (a hotter source clips softly, not a fault). ES8388 full-scale in = AVDD/3.3 ≈ 1.0 V_RMS. | REQ-AUD-07 | ✅ closed 2026-09-08 |
| A5 | **S3 (doc)** | Overview mic description must track the hardware: single-ended (with the pseudo-diff option). Corrected this pass; re-confirm once A9's population is settled. | REQ-AUD-04 | Doc |
| A4′ | **S3 (cosmetic)** | Mic − net now `MIC_N`/`MIC_N_UC` (was `MIC-`). Fine, but see A9 for the population inconsistency. | — | — |
| A8 | **S3 (note)** | 47 µF couplers lengthen turn-on/mode-switch settling (τ ≈ R·C is ~10× the old 1 µF), so the mute-around-transitions rule matters more. Not a defect; a firmware/UX note. | REQ-AUD-06 | FW mute |

**One S2 remains (A9 — a DNP population slip, not an architecture fault).** The prior review's two S2 items (A1, A2) are both fixed. The sheet is layout-ready once A9 is populated correctly, A3 is re-specced and A7 is decided.

---

## 3. Subsystem detail

### 3.1 Codec supply, levels, references — right (unchanged, re-confirmed)

*Confirmed* against the netlist: `DVDD` (pin 2) and `PVDD` (pin 3) on **+3V3_AUDIO**; `AVDD` (17) via **R21 10 Ω**, `HPVDD` (16) via **R16 10 Ω**, both from +3V3_AUDIO (correct per-pin isolation off the shared LP5907 node). `CE` (26) → **R27 10 kΩ → GND** = I²C address **0x20**. Reference decoupling present as 10 µF + 100 nF pairs on VREF, ADCVREF, VMID (C27–C32). Logic levels agree in both directions (all rails 3.3 V). I²C pull-ups 4k7 to +3V3_AUDIO — still a deviation from the user guide's 1 kΩ suggestion, accepted as low-priority.

### 3.2 TX/RX switch + coupling caps (U3, C1/C21) — correct, and the redesign is good

*Confirmed* pinout (TS5A23159 SCDS201H §5): `1 IN1 · 2 NO1 · 3 GND · 4 NO2 · 5 IN2 · 6 COM2 · 7 NC2 · 8 V+ · 9 NC1 · 10 COM1`. Mapped to the netlist:

| Pin | Name | Net | Role |
|---|---|---|---|
| 1, 5 | IN1, IN2 | AUDIO_SW (GPIO5) | ganged L+R select |
| 10 | COM1 | → C1 (47 µF) → R7 → **J1 Ring (Right)** | channel-1 common |
| 9 | NC1 | ROUT1 | RX: right codec out |
| 2 | NO1 | RIN2 | TX: right codec in |
| 6 | COM2 | → C21 (47 µF) → R8 → **J1 Tip (Left)** | channel-2 common |
| 7 | NC2 | LOUT1 | RX: left codec out |
| 4 | NO2 | LIN2 | TX: left codec in |
| 8 | V+ | AVDD | supply |
| 3 | GND | GND | |

**A2 (L/R) is fixed.** RX (IN=LOW → COM–NC): COM1 carries **ROUT1 (Right)** → Ring; COM2 carries **LOUT1 (Left)** → Tip. J1 pins confirm `TIP_LEFT`/`RING_RIGHT`. **Left → Tip, Right → Ring** — standard TRS. TX (IN=HIGH → COM–NO) keeps the same channel-to-contact mapping (Right = RIN2, Left = LIN2). One mapping is correct in both directions. *Confirmed.*

**The coupling redesign is done well** (all *Confirmed* from the netlist):
- **Caps moved to 47 µF electrolytic** (`C1`/`C21`, footprint `CP_Elec_5x5.8`) on the **switch-common/jack side**, so the switch only ever passes VMID-biased signals (≈1.65 V, inside its 0–VCC range). One pair serves both directions.
- **Polarity correct:** `C1`/`C21` Pad 1 (+) → COM (VMID side); Pad 2 (−) → jack side (0 V). VMID > 0, so the + terminal is the more-positive side. ✓
- **Jack-side bleed added:** `R22`/`R23` (100 kΩ) tie the Pad-2/jack nodes to GND, defining them at 0 V when nothing is plugged in (kills insertion/removal pops). Correctly on the jack side, not the codec side.
- **High-pass corner:** *Estimated* 1/(2π·47 µF·10 kΩ) ≈ **0.34 Hz** into a car-AUX load — deep bass margin.

*Estimated / needs bench check (unchanged):* U3.V+ = AVDD ≈ 3.15–3.2 V after R21's drop; at full-scale codec output (VMID + ~1.4 V ≈ 3.0 V) the signal peak nears the switch rail where Ron/THD degrade. Ample margin at line level (~0.3–0.7 V_RMS). Keep the DAC at line level; verify full-scale THD on the bench.

### 3.3 Microphone (MK1, ZTS6216) — single-ended, self-biased, one open note

*Confirmed* from the netlist: `MK1` **ZTS6216**, output `OUT` (1) → **C41 (100 nF) → MIC_P → LIN1** (U4.24). `VDD` (4) on **AVDD**; `IDD` 120 µA typ / 150 µA max (DS-1.4 p.4) — negligible on the analog rail. Supply range **1.5–3.6 V** (abs-max 5 V), so 3.3 V AVDD is in spec. Self-biased single-ended analog output (DC 0.9 V @ VDD 1.5 V), AC-coupled through C41 — the correct front end. The board now wires **RIN1 as a pseudo-differential −** (§3.3a), which — populated correctly — turns the old floating-RIN1 concern (A4) into a used pin and buys common-mode rejection.

- **A3 — coupling-cap dielectric (S3, open).** DS-1.4 p.4: *"Capacitors near the microphone should not contain Class 2 dielectrics."* `C41` is 100 nF in **0402** — necessarily X7R/X5R (Class-II, piezoelectric, voltage-nonlinear). Use **C0G/NP0** (needs ≥0805) or film. *Estimated:* 100 nF into the codec's ~20 kΩ input is an ~80 Hz corner — fine for voice, so keep the value; only the dielectric changes.
- **A5 — single-ended vs differential (record the reasoning).** The ZTS6216's **65 dB PSRR** (DS-1.4 p.4, with internal RF/EMI filtering) is what makes a single-ended connection defensible next to the radio — unlike the older differential rationale in `mems-microphone-primer.md`, which was written for a −45 dB-PSRR part. SNR is **65 dB(A)** — ordinary, but adequate for HFP voice, the mic's only job. Sound trade; now written into the overview so it is not re-litigated.
- **Mechanical:** ZTS6216 is **top-ported** — the enclosure needs an acoustic hole above the part. LGA (do not wash the board). Check the custom footprint's land + port against the datasheet before layout.

### 3.3a Pseudo-differential mic option (MK1 → LIN1/RIN1) — sound idea, wrong population

**Concept — correct.** Driving the mic single-ended into LIN1 (+) while AC-coupling RIN1 (−) to the
mic's ground reference through a *matched* cap gives the ES8388's differential ADC a common-mode to
reject — supply/ground noise picked up between mic and codec cancels, the signal survives. With C41
and its counterpart both 100 nF the two legs high-pass together. This is the right way to get most of
a differential mic's noise rejection from a single-ended MEMS part, and it properly *uses* RIN1
(retiring A4). The pin choice is *confirmed* correct: the ES8388's L-R differential input is
**LINPUT1(+)/RINPUT1(−)** by default (Reg 10 `LINSEL=11`, `DS`/`DSR=0`, datasheet p.17) — exactly
LIN1/RIN1. Firmware dependency: set `LINSEL=11` (not the single-ended `LINSEL=00`).

**A9 — the populated set is inconsistent, so RIN1 floats (S2).** *Confirmed* from the netlist:

| Net | Nodes | Populated? |
|---|---|---|
| `MIC_P` | C41.2, **LIN1** (U4.24) | ✅ mic → C41 → LIN1 (+) |
| `MIC_N` | C22.2 (→GND), R41.1 | C22 ✅ fitted; R41 **DNP** |
| `MIC_N_UC` | **RIN1** (U4.23), C23.1, R41.2 | C23 **DNP**, R41 **DNP** |

RIN1 sits on `MIC_N_UC`, whose only neighbours are **C23 (DNP)** and **R41 (DNP)** — so **RIN1 is not
connected to anything populated. It floats.** Meanwhile the fitted cap C22 couples GND to `MIC_N`, a
stub that dead-ends at R41's unplaced pad — it does nothing. The design provisions three parts for a
one-part job and the fitted subset is the wrong one.

**Fix — populate exactly one reference path to GND, drop the rest:**
- **Simplest:** fit **C23** (100 nF, RIN1 → GND directly); leave C22 and R41 DNP. One cap, matched to C41.
- **Or:** fit **R41** (0 Ω) so RIN1 → MIC_N → C22 → GND; leave C23 DNP.
- Either way, verify C41 and the −-leg cap are the **same value** (100 nF) for a balanced high-pass.

### 3.4 Jack and TX level

- **J1 = PJ-3537S** (3-pole TRS + switch): Sleeve/GND → GND, `RING_RIGHT`, `TIP_LEFT`, `SW_NC` NC-flagged. TRS is the correct, unambiguous choice (A6 fixed).
- **A7 — TX input level: DECIDED line-level-only (2026-09-08).** Jack → R7/R8 (10 Ω) → C1/C21 → switch → LIN2/RIN2, no divider. ES8388 full-scale input = AVDD/3.3 ≈ **1.0 V_RMS**, and the PGA only adds gain (can't cut a hot source). **Decision: expect line level (≤ ~1 V_RMS), PGA at 0 dB.** No attenuator — it would halve the common quieter sources (a 0.316 V_RMS line-out → 0.16 V_RMS) and cost ~6 dB SNR just to rescue a rare over-range source. The BAT54S clamps are **damage protection only**: a source above full-scale clips softly (audible distortion the user fixes by lowering their source), not a fault. A divider is only worth it to cleanly capture a maxed ~2 V_RMS headphone-out — not a use case here.
- LOUT2/ROUT2 → C24/C26 (1 µF) → R9/R10 → TP6: intentional test-point taps. Fine.

### 3.4a TX-input Schottky clamps (D7–D10) — correct and complete

Added to protect the codec's LIN2/RIN2 inputs (and the electrolytic couplers) from a source hot
enough to drive past the rails. *Confirmed* from the netlist — a full clamp pair on each channel:

| Diode | Anode | Cathode | Fires when | Role |
|---|---|---|---|---|
| D7 | LIN2 | AVDD | LIN2 > AVDD + 0.3 V | LIN2 upper |
| D8 | GND | LIN2 | LIN2 < −0.3 V | LIN2 lower |
| D10 | RIN2 | AVDD | RIN2 > AVDD + 0.3 V | RIN2 upper |
| D9 | GND | RIN2 | RIN2 < −0.3 V | RIN2 lower |

**All four correctly oriented, and all reverse-biased at the VMID ≈ 1.65 V idle point** (uppers
because 1.65 < AVDD, lowers because 1.65 > −0.3), so there is **no DC loading of the input bias** —
the fault an earlier single-diode attempt had. Clamp window ≈ −0.3 … +3.5 V (≈ ±1.85 V, ~1.3 V_RMS
around VMID), safely above full-scale (1.0 V_RMS), so normal audio passes untouched and only gross
overdrive conducts. **Part assigned: BAT54W (LCSC C779673, ZRE), SOD-123**, ×4 — JLCPCB *Extended*
(one feeder fee for all four; junction capacitance is a non-issue at audio into 20 kΩ). Confirm
stock at BOM freeze (§2.3). This is protection, not level-setting — A7's attenuator question is
independent.

### 3.5 Cross-cutting

- **Ground loop (REQ-AUD-05):** with a battery in scope, unplugging USB breaks the chassis-ground path — the cleanest whine mitigation. **R7/R8 are plain 0402 10 Ω** — there is **no transformer/link footprint** provisioned (correcting the overview's stale "footprints accept either" claim). Battery-only playback is the plan of record; state it.
- **Settling/pop (A8):** 47 µF lengthens the VMID settling on power-up and on each TX/RX flip; mute the codec across those transitions.

---

## 4. Part-by-part

| Ref | Part | Verdict |
|---|---|---|
| U4 | ES8388 | **Keep.** Correctly supplied and levelled; 95 dB ADC / 96 dB DAC exceeds anything a car AUX resolves. |
| U3 | TS5A23159DGS | **Keep.** Correct dual-SPDT, ~1 Ω, break-before-make, THD 0.004%. Wiring verified pin-by-pin. VSSOP-10 0.5 mm clears the Economic floor. |
| MK1 | ZTS6216 | **Keep, with A3.** Self-biased single-ended, 65 dB PSRR + EMI filter, in spec on 3.3 V. SNR 65 dB(A) is the weakest spec — fine for HFP. Top-ported: needs an enclosure port. |
| J1 | PJ-3537S (TRS) | **Keep.** 3-pole TRS + detect switch; L/R correct. |
| C1, C21 | 47 µF electrolytic, `CP_Elec_5x5.8` | **Keep.** Matches Panasonic **EEEFT1E470AR (C336270)**, 25 V, D5×5.8 mm, in stock. Correct polarity/placement. Extended-tier (one feeder fee); ~6 mm tall — check enclosure height. |
| C41 | 100 nF 0402 | **Re-spec (A3)** — C0G/film. |
| D7–D10 | **BAT54W** (C779673, SOD-123) | **Keep.** Correct TX-input clamp pairs, no DC loading at VMID. Extended-tier, one feeder fee for all four. |
| MK1 − ref | C22 / C23 / R41 | **Fix population (A9)** — fit one of C23 or R41 so RIN1 is referenced, not floating; the fitted subset is currently inconsistent. |

---

## 5. Decisions — resolved

1. **A7 — TX input level:** ✅ **Decided line-level-only (2026-09-08).** Expect ≤ ~1 V_RMS, PGA at 0 dB; no attenuator; BAT54S clamps are damage protection. See §3.4.
2. **A3 — C41 dielectric:** ✅ **Resolved** — mic caps set to 100 nF C0G (Murata C97946, C41/C42).

No open decisions remain on the audio sheet.

## 6. Fix-before-layout list

**Status 2026-09-08 — all pre-layout items resolved:**
1. ~~A9 — mic − reference~~ → **deliberate DNP provisioning**: JLC places both C0G caps (C41 +, C42 −); hand-fit R41 (0 Ω) to enable pseudo-diff. RIN1 floats in the default build — benign while the right ADC is powered down.
2. ~~A3 — C41 dielectric~~ → **100 nF C0G** (Murata C97946) on C41/C42.
3. ~~A7 — TX input level~~ → **decided line-level-only**, PGA 0 dB (clamps = damage protection).

Remaining is firmware-only: **A8** (mute across power-up / TX-RX switch).

**Docs (this pass):** A5 single-ended-mic rationale and the battery-breaks-ground-loop plan folded into the design overview; ZTS6216 top-port enclosure hole flagged for mechanical.

---

## 7. Overall assessment

The audio sheet has closed out the previous review cleanly. **The prior two S2 defects (rail-gating back-power, L/R swap) are fixed, along with the TRRS→TRS jack** — and the coupling network was rebuilt into a genuinely good bidirectional design (47 µF electrolytics on the jack side, correct polarity, jack-side bleed), plus a correct four-diode TX-input clamp and a pseudo-differential mic upgrade. The remaining work is not architecture: **one population slip (A9 — the mic − reference is DNP, so RIN1 floats)**, one datasheet footnote (the mic cap's dielectric, A3), and one scope decision (TX input level, A7). Only A9 needs fixing before layout, and it's a one-part change. The pattern to watch: the audio circuits are now *right by design* but carry a couple of **DNP/population choices that must be made explicit** before the BOM is frozen — a clamp diode array and a mic reference that each provision more than they populate. This subsystem is otherwise the most complete on the board.
