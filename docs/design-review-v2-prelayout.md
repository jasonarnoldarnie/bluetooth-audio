# System Design Review — Bluetooth Audio Adaptor, Rev B (pre-layout)

**Date:** 2026-09-14
**Reviewer:** netlist-level audit against primary datasheets
**Scope:** Final schematic review before starting PCB layout.
**Verdict:** One blocking S1 (board cannot power up as drawn), plus a small cluster of
integration/value defects. **The three S1 defects from [`design-review-v1.md`](design-review-v1.md)
are all now correctly fixed.** Fix the items in §6 "before layout" and the board is ready.

---

## 0. How this review was done

Connectivity was taken from the **exported netlist**, not the schematic PDF or memory:
`bluetooth-audio.kicad_sch` (root + `micro`/`power`/`audio` sheets) exported to KiCad XML via the
IPC backend at commit `9141db3`, then parsed pin-by-pin. Every finding below is stated against a
net and, where a pin function was in doubt, verified against the datasheet in `hw/datasheets/`.

| Checked against | Document (local) | Used for |
|---|---|---|
| ESP32-D0WD-V3 | `esp32_datasheet_en.pdf` | Flash SDIO pin functions, strapping-pin internal pulls |
| W25Q32JV | referenced (Winbond rev G) | Flash IO0–IO3 pinout |
| ES8388 | `..._ES8388_C365736.pdf` | Codec supply pins, CE, I²S/I²C |
| TS5A23159 | `TI-TS5A23159-SCDS201H.pdf` | Dual-SPDT channel pin grouping |
| ERC | KiCad IPC `run_erc` | Corroboration (10 errors / 82 warnings) |

Confidence labels: **Confirmed** = verified against netlist + cited datasheet; **Estimated** =
calculated, arithmetic shown; **Needs bench/library check** = cannot be settled from the netlist.

**Not re-verified this pass** (trusted as-is): CH340K auto-program transistor network (Q1/Q2 detail),
exact RF match values (a known NanoVNA bring-up task), thermal figures (unchanged from the overview).

---

## 1. Corrections to previous reviews

**The old flash IO2/IO3 finding is fixed — and I nearly re-flagged it wrongly.** Reasoning from
memory, "SPIHD should go to the flash /HOLD pin" looks like a swap. It is not. Espressif's own
recommended flash connection table (ESP32 datasheet, Pin Definitions) maps `SD_DATA_2/SPIHD → IO2`
and `SD_DATA_3/SPIWP → IO3`, and the schematic now matches it exactly. Recorded as **confirmed
correct** in §3. The lesson the skill warns about held: the datasheet, not recall, settled it.

**WITHDRAWN — the audio L/R "swap" (this review's own finding #2). It was my error; the design is
correct.** I paired C1 with R8 by adjacent ref-des numbering instead of following the net. The
actual path is: codec **right** (ROUT1/RIN2) → U3 COM1 (pin10) → C1 → **R7** → jack RING (right);
codec **left** (LOUT1/LIN2) → U3 COM2 (pin6) → C21 → **R8** → jack TIP (left). Left↔left,
right↔right — correct in both directions, RX and TX. The trap: on a dual-SPDT the COM-to-jack
routing crosses the ref-des order (C1→R7→ring, not C1→R8→tip), so eyeballing the pairing inverts the
conclusion. Following the net, not the numbering, is the only reliable read.

---

## 2. Headline findings

| # | Sev | Finding | Affects | Status |
|---|-----|---------|---------|--------|
| 1 | **S1** | **U9 (BQ24074) was marked DNP** and nothing else sources `+V_SYS` → whole board unpowered. Confirmed a stray flag. | REQ-PWR-01/02/03/04, all | ✅ **Fixed** — DNP cleared (owner confirmed) |
| 2 | ~~S2~~ | ~~Audio L/R swapped through the TX/RX switch.~~ | — | ❌ **WITHDRAWN** — reviewer error, design is correct (§1) |
| 3 | **S2** | `R39 = 100k`, should be **47k**: VBUS-sense tap = VBUS/2 = 2.5 V, above ADC1's 2.45 V ceiling. | source-detect guard-rail | ✅ **Fixed** — R39 → 47k |
| 4 | **S2** | Crystal load caps still **18 pF** (Rev A); overview's Rev B target is 15 pF → 10 pF crystal over-loaded. | REQ-MCU-06 | ⏳ Owner will recalc; not blocking |
| 5 | **S3** | **C53 pad 1 floating** — VBUS-sense filter not connected to `USB_VBUS_SENSE`. | source-detect guard-rail | ✅ **Fixed by owner** |
| 6 | **S3** | **D1 is a WHITE LED** on 3.3 V/330 Ω → ~0.3–0.9 mA, dim. | REQ-MCU-07 | ✔️ Accepted by owner |
| 7 | **S3** | ERC: U3 units had **different footprints** (TSSOP vs MSOP). Datasheet package is **VSSOP (DGS) = MSOP-10**, not TSSOP. | manufacturability | ✅ **Fixed** — all units → MSOP-10 |
| 8 | **S3** | ERC: `JACK_DET` sheet pin has no matching label inside its sheet (+ associated unconnected pin). | — | ⏳ Open — hierarchy cleanup |
| 9 | verify | **BAT54S (D7/D8) clamp orientation** — pin 3 is the series midpoint. | codec input protection | ✅ Confirmed correct by owner |
| 10 | — | 82 ERC "symbol doesn't match library" warnings (submodule consolidation). | ERC hygiene | ⏳ Run *Update Symbols from Library* |
| 11 | **S3** | **R1/R2 (10k) redundant** — Q1 (UMH3N) is a *pre-biased* digital transistor (LCSC C62892: "2 NPN pre-biased", DTC143-type dice with internal base + base-emitter resistors), so the external base resistors stack on the internal ones. Circuit still works. | REQ-DEV-01, BOM | ⏳ Owner to remove (wire DTR→Q1.2, RTS→Q1.5 direct) — *owner-found* |

---

## 3. Subsystem reviews

### 3.1 Power — one blocking defect, and a broken guard-rail

**What is right.** Two-LDO split is built as designed: U7 (AP7361C-33Y5, SOT-89) → `+3V3_SYS`
(digital/RF), U11 (LP5907, SOT-23-5) → `+3V3_AUDIO` (codec). U7's EN is tied to its own input
(always-on when SYS present); U11's EN is on `AUDIO_VCC_EN` (GPIO4, held low by R33 → codec off at
boot) — correct. Charge-programming resistors match the overview (R_ISET 1k2, R_ILIM 1k5, R_ITERM
3k, R_TMR 56k). EN1/EN2 strapping (R30 100k→SYS, R31 100k→GND) and the CC/BAT dividers are as
documented. **Confirmed.**

**① S1 — the board has no power source as drawn.** `+V_SYS` (which feeds both LDO inputs) connects
only to `U9` pins 10/11 (charger OUT), and **U9 is DNP**. `USB_VBUS` dead-ends at `U9` pin 13 (IN).
There is no 0 Ω link from VBUS to SYS — R3 and R14 (the only DNP 0 Ω parts) are the DTR/RTS
auto-program network, not power bypasses. So with the charger unpopulated, nothing reaches the LDOs
and the board is dead. **This is almost certainly a stray DNP flag** (every document treats the
BQ24074 as populated), but it must be resolved before layout — a DNP charger produces no `+V_SYS`
ratsnest, so the whole power path would go unplaced/unrouted. *Confirmed (netlist).* See §6 for the
decision.

**③ S2 — VBUS-sense divider out of range. [FIXED — R39 → 47k].** `R38/R39 = 100k/100k` gave
`USB_VBUS_SENSE = VBUS/2` = 2.50 V at 5.0 V (2.75 V at 5.5 V). Source: **ESP32 datasheet, ADC
Characteristics** — "Atten = 3, effective measurement range of 150–2450 mV", and the note "When
atten = 3 and the measurement result is above 3000 (voltage at approx. 2450 mV)… measurement errors
may be introduced." So the 2.50 V tap sits just past the atten-3 (11 dB) ceiling and the reading
clips/errors. Overview §3.4 specifies **100k/47k → 1.60 V**, well inside range. R39 changed to 47k.
*Confirmed (netlist + datasheet).*

**⑤ S3 — C53 filter floating.** `C53` pad 2 → GND, pad 1 → *unconnected*. The 100 nF VBUS-sense
filter (overview §3.4, τ = 3.2 ms) has no connection to `USB_VBUS_SENSE`. Pad 1 should tie to that
net. (This is ERC error "Pin not connected".) *Confirmed (netlist + ERC).*

### 3.2 Audio — one functional defect, placement otherwise excellent

**What is right.** The much-emphasised **TX/RX switch placement is correct**: the switch throws are
the codec's LOUT1/ROUT1 and LIN2/RIN2 (all biased at VMID ~1.65 V, inside the switch's 0–AVDD
window), with the 47 µF coupling caps (C1/C21) and 10 Ω (R7/R8) between the switch COM and the jack.
RX/TX selection polarity is right too (IN high = NO = LIN2/RIN2 = TX, matching the GPIO5 boot
strap). J1 is a 3-pole TRS as decided. Mic single-ended path (MK1 → C41 → LIN1) is correct; RIN1
open is the documented single-ended default (R41/C54 DNP). **Confirmed.**

**② WITHDRAWN — L/R is correct.** TS5A23159 channel grouping (datasheet §5):
Ch1 = COM1(10)/NO1(2)/NC1(9), Ch2 = COM2(6)/NO2(4)/NC2(7). Tracing the *nets* (not the ref-des
order):

- COM1 (pin 10) → C1 → **R7** → jack **RING (Right)**; throws NO1→RIN2, NC1→ROUT1 → **right codec**. ✓
- COM2 (pin 6) → C21 → **R8** → jack **TIP (Left)**; throws NO2→LIN2, NC2→LOUT1 → **left codec**. ✓

Left↔left, right↔right, both directions. My original finding paired C1 with R8 by adjacent
numbering instead of following the net — see §1. No change needed.

**⑨ Needs library check — BAT54S clamp orientation.** D7/D8 connect pin1(A)→GND, pin2(K)→AVDD,
pin3(K)→LIN2/RIN2. This is the correct BAT54S *series-clamp* topology **only if the KiCad symbol's
pin 3 is the series midpoint** (anode-D2/cathode-D1 junction). If the symbol is actually
common-anode, the upper clamp (signal→AVDD) is absent and only the negative excursion is clamped. No
rail-short risk either way. Confirm against the BAT54S datasheet before trusting the protection.
*Needs check.*

### 3.3 Microcontroller / RF — clean; one value carried over

**What is right (all confirmed against the ESP32 + Winbond datasheets):**
- **Flash IO0–IO3 exactly match Espressif's recommended connection** (SD_DATA0/SPIQ→IO1/DO,
  SD_DATA1/SPID→IO0/DI, SD_DATA2/SPIHD→IO2, SD_DATA3/SPIWP→IO3). Old S2 fixed correctly.
- **Strapping pins all safe:** MTDI (GPIO12) has an internal pull-down (datasheet: default 0 →
  3.3 V flash), so floating with R26 DNP is correct; GPIO2 held low by R32; GPIO0 internal PU +
  auto-boot; GPIO5 (AUDIO_SW) has no external pull; MCLK correctly on GPIO0 (codec input Hi-Z at
  reset). CAP2 correctly NC; spare GPIO33 flagged NC.
- **RF C-L-C pi match is present:** shunt C38 (3.3 pF) at antenna, series L1 (2.2 nH), shunt C37
  (3.3 pF) at the ESP32 LNA. Values to be tuned with the NanoVNA — a known bring-up task, not a
  defect.

**④ S2 — crystal load caps unchanged from Rev A.** C35/C36 = 18 pF against a 10 pF-CL crystal (Y1):
`CL = 9 pF + ~3 pF stray ≈ 12 pF` > 10 pF → over-loaded, frequency pulled low. The overview's own
Rev B target (§7) is **~15 pF**. Trimmable at bring-up, but it starts off-target and contradicts the
design doc. Move to 15 pF (then trim on measured offset to ±10 ppm). *Confirmed (netlist) + Estimated.*

**⑥ S3 — white LED under-driven.** D1 (LED_WHITE) is driven from GPIO22 through R12 = 330 Ω. With
white Vf ≈ 3.0–3.2 V on a 3.3 V rail, `I = (3.3 − 3.1)/330 ≈ 0.6 mA` (0.3 mA worst case) — dim, the
same headroom problem as the old blue-LED finding. Green (D3, ~3.6 mA) and the rail/charger
indicators are fine at 330 Ω. **Fix:** use a low-Vf colour (red/green/amber) for the user
indicator; white/blue on 3.3 V is fundamentally headroom-starved regardless of resistor. *Estimated.*

### 3.4 Cross-cutting

- **Always-on rail indicators.** D2 (`+3V3_SYS`) and D4 (`+3V3_AUDIO`) draw ~4 mA each continuously
  when lit — not in the power budget (which lists only 2 GPIO LEDs). On battery, an always-on power
  LED is a real drain; consider whether both are wanted, or gate them. *S3.*
- **ERC hygiene (⑦⑧ + warnings).** 10 errors / 82 warnings. Substantive: **U3B/U3C different
  footprints** (a multi-unit part must resolve to one footprint — fix before the PCB sync), and the
  `JACK_DET` sheet-pin/label mismatch. The 82 warnings are dominated by "symbol doesn't match copy
  in library" — fallout from the kicad-library submodule consolidation; run *Update Symbols from
  Library* so ERC is usable going forward. Cosmetic, but clear them before layout.

---

## 4. Part-by-part (key parts only)

| Part | Role | Verdict |
|---|---|---|
| U1 ESP32-D0WD-V3 | MCU + radio | Correct; forced by BT-Classic requirement. Flash + strapping verified. |
| U4 ES8388 | Codec | Correct: all 4 rails 3.3 V, CE→GND (0x20), 10 Ω on AVDD/HPVDD supplies. |
| U6 W25Q32JV | Flash | Correct part (JV/3.3 V) and correct IO mapping (datasheet-verified). |
| U7 AP7361C-33Y5 | LDO A | SOT-89, always-on, as designed. |
| U11 LP5907 | LDO B | Low-noise codec rail, EN on GPIO4. |
| U9 BQ24074 | Charger | **DNP — see S1.** Otherwise wired per overview. |
| U3 TS5A23159 | TX/RX switch | Right placement; **L/R swapped (S2)** + footprint ERC (S3). |
| Y1 40 MHz XTAL | Reference | OK; **load caps need 15 pF (S2)**. |

---

## 5. Requirements impact

- **REQ-PWR-01…04** are marked ✅ but the DNP charger means no rail is actually powered — status is
  currently false. Corrected by fixing S1.
- **REQ-AUD-03/07**: signal path exists and switch placement is right, but channels are reversed (S2).
- **REQ-MCU-06**: crystal loading still off the Rev B target (S2).
- No new requirement gaps surfaced — the overview already covers ambient (REQ-ENV-01, proposed),
  ground loop (REQ-AUD-05), and RF measurability (§2.9).

---

## 6. Prioritised action list

### Applied this pass (schematic files edited on disk — reload eeschema, then *Update PCB from Schematic*)
1. ✅ **U9 DNP cleared** (`power.kicad_sch`) — charger now populates and routes.
2. ✅ **R39 → 47k** (`power.kicad_sch`) — VBUS-sense tap back inside ADC range.
3. ✅ **U3 all units → MSOP-10** (`audio.kicad_sch`) — datasheet-correct (VSSOP/DGS), clears the ERC
   footprint conflict.

### Fixed by owner
- ✅ **C53 pad 1** wired to `USB_VBUS_SENSE` (verified in the re-pulled netlist).

### Still open before/around layout
- ⏳ **Crystal C35/C36** — owner to recalculate (target ~15 pF; not blocking).
- ⏳ **Run *Update Symbols from Library*** (Tools menu) to clear the 82 "doesn't match library"
  warnings, then re-pull the netlist and re-verify — a symbol update *can* move pins, so confirm the
  critical nets afterward.
- ⏳ **`JACK_DET` hierarchy error** — sheet pin with no matching label inside its sheet; clean up.

### Accepted / confirmed by owner (no change)
- ✔️ **D1 white LED** kept as-is.
- ✔️ **D2/D4 always-on** rail indicators — intentional for development, will be disabled for production.
- ✅ **BAT54S (D7/D8)** — pin 3 is the series midpoint; clamps to both AVDD and GND as intended.

---

## 7. Overall assessment

**The pattern: the design content is done and correct — the defects are the last-mile mechanical
ones.** Every hard integration question from v1 (codec logic domain, CE address, CAP1, the 10 Ω
supply resistors, flash IO mapping, strapping) is resolved and verified. What remains is a stray DNP
on the most important IC, a left/right pairing slip, two wrong/omitted passive connections in the
guard-rail, and a crystal value that didn't get updated to its own documented target. None is deep;
all are the kind that hide precisely because the surrounding design is finished and looks trustworthy.
Clear §6 and the board is ready to lay out.

*Confirmed fixes from [`design-review-v1.md`](design-review-v1.md) — recorded so they aren't undone:
codec on a dedicated 3.3 V LDO; ES8388 CE pull-down; ESP32 CAP1 10 nF; flash IO2/IO3; 10 Ω moved
from the codec outputs to between its supply pins.*
