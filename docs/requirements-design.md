# Bluetooth Audio Adaptor — Requirements & Design Document

**Version:** 1.5
**Date:** 2026-08-20
**Owner:** Jason
**Status:** Documents the as-built v1 hardware design (schematic complete, per commit `369c5f9`), a set of standing design constraints for all future decisions, and a Principal-Engineer scope/complexity review flagging what to fix in v2.
**Source material:** [`calculations.xlsx`](../calculations.xlsx) (6 sheets) cross-checked against the actual KiCad schematics and PCB layout in [`hw/bluetooth-audio/`](../hw/bluetooth-audio/).

> ⚠️ **A netlist-level system design review has been completed — see [`design-review-v1.md`](design-review-v1.md).** It found three **S1** defects (issues that prevent correct operation or stress a part beyond its absolute maximum rating) that are not yet reflected as fixes here, and it **withdrew this document's previous Economic-PCBA cost argument** as factually wrong. Requirement statuses in §3 below have been corrected where the review disproved them; the constraints in §2 have been updated. **Read the review before starting v2 work.**

> Companion interactive view: see the published artifact linked in chat for a filterable/sortable version of the tables below. This markdown file is the source of truth — update it first, then republish the artifact.

---

## 1. Overview

Bluetooth adaptor that plugs into a 3.5 mm audio jack.
- **RX mode (the product):** device receives wireless audio from a phone and outputs it on the 3.5 mm jack (e.g. into a car radio aux input).
- **TX mode — ✅ NOW IN SCOPE (decision D4, 2026-08-23), not yet implemented in hardware.** The original concept (`Specifications!A29`) described the device also accepting analog audio from the 3.5 mm jack and streaming it out over Bluetooth. **The design review found the jack (J1) is wired to `LOUT1`/`ROUT1` only — outputs. There is no signal path from the jack into the codec's inputs.** v1 as built is an RX-only sink. TX is now a committed requirement (REQ-AUD-07, §3.4b): it needs a jack input path into the codec's `LIN2`/`RIN2`, which are already broken out to TP5. Recommended as a second jack labelled IN rather than switching one socket. *(See [design review §3.5(b)](design-review-v1.md).)*

*(Source: `calculations.xlsx` → Specifications!A29, corrected against the netlist in v1.3)*

**Why ESP32 + a separate audio codec, rather than a fixed-function Bluetooth-audio SoC:** this project is meant to be a firmware-hackable platform, not just the cheapest possible dongle — it needs SDK-level control to reach the deferred handsfree (HFP) feature and to leave room for custom DSP/EQ later. That trade (more parts, more design work, in exchange for extensibility) is deliberate and is the design driver behind most of the Microcontroller and Audio subsystem choices below. *(This line was previously implicit — added during the v1.1 scope review, see §5.)*

### 1.1 Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Complete — implemented in schematic, verified against as-built component list |
| ⚠️ | Partial — some sub-items done, others explicitly marked incomplete in source |
| 🔲 | Open — not yet done, or requires firmware/bench verification beyond schematic |
| ➖ | N/A — resolved as "does not apply" (not a gap) |
| 🔮 | Future / candidate — not in scope for v1 |

---

## 2. Design Constraints & Guidelines

**Apply these to every component and layout decision from here on — v1 fixes and all of v2.** When a decision conflicts with one of these, write down *why* the exception earns its cost (schedule, no alternative exists, functional necessity) next to the part, rather than letting scope drift silently. This section is itself a living part of the document — update it when a rule turns out to be wrong in practice.

### 2.1 Manufacturing target: JLCPCB, and which assembly tier

This board is built through JLCPCB. Two SMT assembly tiers exist, and the tier a design qualifies for is a direct multiplier on unit cost, lead time, and max batch size:

| | Economic PCBA | Standard PCBA |
|---|---|---|
| Min. IC pin spacing | 0.4 mm | 0.35 mm |
| Min. BGA ball spacing | 0.5 mm | 0.35 mm |
| Smallest package | 0402 | 0201 |
| Assembly sides | **Single-sided only** | Single or double-sided |
| Layer count supported | 2 / 4 / 6 | 1–32 |
| Batch size | 2–50 pcs | 2–80,000 pcs |
| Solder paste inspection | No | Yes |

*(Source: [JLCPCB PCB Assembly Capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities), fetched 2026-08-20 — reconfirm before finalizing a v2 quote; JLCPCB revises these periodically.)*

**❌ Rule withdrawn in v1.3 — "default to Economic PCBA" is not achievable for this product.**

Versions 1.1–1.2 of this document made Economic PCBA the primary cost goal. That was wrong, and it was wrong because I checked JLCPCB's published *capability table* but never checked whether the actual *parts* were Economic-eligible. The design review checked the live part pages:

| Part | JLCPCB "PCBA Type" | Reason |
|---|---|---|
| ESP32-D0WD-V3 (C967021) | **Standard Only** | QFN-48, 0.35 mm pitch — under the 0.4 mm floor |
| ESP32-WROOM-32E-N4 (C701341) | **Standard Only** | module handling / size |
| ESP32-WROOM-32 (C503587) | **Standard Only** | module handling / size |
| ES8388 (C365736) | Economic **and** Standard | 0.4 mm pitch clears the floor |

**Every Bluetooth-Classic-capable ESP32 option is Standard Only.** REQ-MCU-01 requires Bluetooth Classic, and only the original ESP32 die has Classic radio hardware (S3/C3/C6/H2 are BLE-only). So **Standard PCBA is unavoidable**, and no part or layout choice changes it. The ES8388's 0.4 mm pitch, flagged as a "borderline risk" in v1.1, is confirmed fine and was never the constraint.

### 2.1a The cost model that actually applies

On Standard PCBA, **every unique part carries a ~$1.50 feeder-loading fee, charged once regardless of build quantity** (no parts are pre-loaded, unlike Economic). At hobbyist volumes this dominates: the cost driver is the number of **unique BOM lines**, not the pitch of any one part.

v1 currently has **35 billable BOM lines ≈ $52.50** in feeder fees before paying for a single component.

**Rules that follow:**
- **Minimise unique BOM lines.** Reuse the same value *and the same package* wherever electrically acceptable. v1 currently spends 3 lines on 1 µF (0402/0603/1206) and 4 on 10 µF — roughly $10 of pure waste.
- **Normalise value strings.** v1 mixes `10u` and `10uF` for the same part; identical values written differently become separate BOM lines and separate purchase decisions. Pick one convention and hold it.
- **Count the line, not just the part.** A part that eliminates several others (e.g. a module absorbing flash + crystal + load caps + RF matching) can be cheaper overall despite a higher unit price. Below roughly 45 boards this is exactly the case here — see [design review §4.1](design-review-v1.md).
- **Back-side placement** — see §2.1b, which reverses the v1.3 position on this.

### 2.1b Economic tier IS reachable — by self-populating the ESP32

**Added v1.4.** v1.3 concluded Economic was unreachable because every Bluetooth-Classic ESP32 is "Standard Only." That's true *if JLCPCB places every part*. It isn't true if the one blocking part is **excluded from the assembly and hand-soldered afterwards** — JLCPCB simply fabricates the pads and skips it.

**Verified: the ESP32-D0WD-V3 is the only Standard-Only part in the design.** Every other part checked is Economic-eligible:

| Part | Package | JLCPCB PCBA tier |
|---|---|---|
| ESP32-D0WD-V3 (C967021) | QFN-48, **0.35 mm** | ❌ **Standard Only** → self-populate |
| ES8388 (C365736) | QFN-28, 0.4 mm | ✅ Economic and Standard |
| W25Q32JVZPIQ (C571260) | WSON-8-EP | ✅ Economic and Standard |
| ICS-40720 (C3171779) | LGA-4, MSL 1 | ✅ Economic and Standard |
| BQ24074RGTR (C54313) *(proposed, battery)* | QFN-16-EP 3×3 | ✅ Economic and Standard |

Remaining parts (SOT-23/89/223, SSOP-10, 0402 passives, connectors) are mainstream packages comfortably inside Economic limits. **Definitive check: upload the BOM to JLCPCB's instant quote — it flags Standard-Only parts explicitly.** Do this before committing, since tiers change.

**Constraints this imposes — all three are hard:**

1. **Economic PCBA is single-sided placement only — but ✅ this design already complies.** *(Corrected in v1.4 — my first pass said the six back-side items must move; that was wrong.)* Checking what is actually *placed* rather than what merely sits on the back layer:
   - **TP5, TP6, TP7, TP9** are bare copper test pads. There is no component to pick and place.
   - **J3 and J4** are the only real components on the back — and **both are marked DNP**, so they are excluded from the assembly data and JLCPCB never places them.

   **Nothing is assembled on the back side, so the constraint is already satisfied as drawn.** No re-layout needed. Note that J3/J4 being DNP also means the off-board-serial (REQ-DEV-01) and JTAG (REQ-DEV-02) paths need their headers hand-fitted before use — trivial for through-hole, but worth knowing before a debug session rather than during one.
2. **0402 is the smallest permitted passive.** Every passive is currently 0402 — at the floor, so acceptable, but nothing may shrink further.
3. **0.4 mm is the minimum IC pin pitch.** The ES8388 sits exactly at it. It is confirmed Economic-eligible, but leaves no margin for another fine-pitch part.

4-layer is fine — Economic supports 2/4/6 layers, so §2.4's 4-layer default is unaffected.

**Rule going forward:** the design targets **Economic PCBA with the ESP32 excluded from assembly and hand-populated**. Any new part must be checked for Economic eligibility *and* placed on the front side. Adding a second Standard-Only part would mean either hand-soldering it too or losing the tier entirely — so treat Economic eligibility as a selection criterion, not an afterthought.

### 2.2 Prefer certified modules over bare silicon + support circuitry

Bare RF silicon (any 2.4 GHz radio chip) drags in an external crystal, an RF matching network you have to size and can't easily verify without test equipment, and antenna layout that risks a wasted PCB spin if the match is wrong. A pre-certified module (e.g. ESP32-WROOM-32E in place of the bare ESP32-D0WD-V3) absorbs all of that into one part — flash, crystal, matching network, antenna, and FCC/CE/SRRC certification — at a coarser, hand-solderable pitch, in exchange for a larger footprint and a somewhat higher line-item cost. For a hobbyist build, that trade is almost always worth it: board area is cheap, RF rework after fabrication is not.

**Rule:** default to a certified module for any RF function. Only go to bare silicon + custom matching/antenna when there's a concrete reason a module can't meet the requirement (e.g. board space genuinely doesn't fit the module, or a needed pin/peripheral isn't broken out on any available module).

### 2.2a ⚠️ Explicit exception for this project: RF design is a stated learning objective

**Added v1.4.** This rule is **deliberately overridden** for the 2.4 GHz front end. Designing the trace antenna and matching network is an explicit goal of the project — it is *why* the bare ESP32-D0WD-V3 was chosen over a module, and it outranks the cost and risk arguments that §2.2 is built on.

This is a legitimate requirement, not scope creep. Recording it here so that:
- Reviews **stop re-litigating the module swap.** It was recommended twice ([v1.1 §5 P0](#), [design review §4.1](design-review-v1.md)) on cost and risk grounds; both recommendations are **withdrawn** on the basis of this objective. A learning goal that the owner states explicitly is a requirement like any other.
- The **consequences are accepted knowingly**, not by omission. Keeping the bare IC means these stay live and must be designed and verified rather than deleted by a module: RF matching network sizing, 50 Ω controlled-impedance routing, crystal load-capacitance and frequency offset (REQ-MCU-06), and the flash `IO2`/`IO3` swap (REQ-MCU-04) — all of which a module would have absorbed.
- **Learning objectives get measurement budget.** An RF design you cannot measure isn't a learning exercise, it's a guess. See §2.9.

**Where the rule still applies:** for any *other* RF function added later (e.g. a second radio), default back to a module unless it too is part of a stated learning goal.

### 2.9 Design exercises must be measurable

**Added v1.4.** Where a subsystem is being designed to learn (currently: the RF front end, §2.2a), the project must own the instrumentation needed to close the loop. Otherwise the design cannot be validated, the learning doesn't happen, and a failure looks identical to a success until range testing disappoints.

Minimum for the RF work:
- **NanoVNA (~$50–100)** — measures antenna S11/return loss so the Pi matching network can actually be tuned rather than guessed. This is the single enabling purchase; without it the matching values are unverifiable.
- **A way to measure carrier frequency offset**, for the crystal load-capacitance question (REQ-MCU-06). Espressif's stated method wants a spectrum analyser, but an **RTL-SDR (~$30)** with a known reference is a workable hobbyist substitute for measuring a few tens of ppm.
- **JLCPCB's published stackup and impedance calculator** for the 4-layer board, so 50 Ω trace geometry is calculated against the real dielectric rather than assumed.

**Rule:** before committing a board spin that depends on a tuned RF design, confirm the measurement path exists. Budget the instrument alongside the PCB.

### 2.10 Power budget — two rails, sized separately

**Added v1.5**, answering the concern that the original LDO's footprint was larger than wanted. It was — but the fix is not simply "go smaller", it is *split the load and let each rail take the package it actually needs.*

| Load | Rail | Current |
|---|---|---|
| ESP32, Bluetooth Classic streaming (avg) | **A — digital/RF** | ~130 mA |
| ESP32 transmit peak | A | ~250 mA |
| SPI flash (mostly idle) | A | ~5 mA |
| CH340K (only when USB attached) | A | ~10 mA |
| 2× status LEDs at corrected brightness | A | ~8 mA |
| **Rail A total** | | **~155 mA avg, ~280 mA peak** |
| ES8388, all rails at 3.3 V, playback + record | **B — codec analog** | ~18 mA |
| MEMS microphone | B | ~0.4 mA |
| **Rail B total** | | **~20 mA** |

**Rail B is tiny.** ~20 mA means dissipation of roughly 1.1 V × 0.02 = **22 mW**. A SOT-23-5 is entirely adequate — the constraint here is *noise*, not current, so choose on PSRR and pick the smallest package that meets it.

**Rail A gets easier too, because of the charger.** The BQ24074 regulates its output to never exceed 4.4 V, so the LDO drops 1.1 V instead of 1.7 V from raw USB:

| | Dissipation | Rise (θ_JA) | Junction @ 70 °C ambient |
|---|---|---|---|
| Old: 5 V → 3.3 V @ 300 mA, SOT-223 (~80 °C/W) | 0.51 W | 41 °C | 111 °C |
| New: 4.4 V → 3.3 V @ 155 mA avg | **0.17 W** | 14 °C | 84 °C |
| New: 4.4 V → 3.3 V @ 280 mA peak | 0.31 W | 25 °C | 95 °C |

**So the big SOT-223 is no longer required.** Splitting the rails and capping the input at 4.4 V cuts Rail A's dissipation by ~40 %.

**Correction to the first version of this section:** it sized the package on the 0.31 W *peak* and concluded SOT-23-5 was ruled out. That was too conservative. Bluetooth transmit bursts last ~1–2 ms, while a package's thermal time constant is seconds — so the junction integrates them and **responds to the average (0.17 W), not the peak.** Peak current still sets the *current rating*; average sets the *thermal package*. They are different questions and I conflated them.

| Package | θ_JA | Rise at 0.17 W avg | Junction @ 70 °C ambient |
|---|---|---|---|
| SOT-23-5 | ~200 °C/W | 34 °C | **104 °C** — works, 21 °C margin |
| SOT-89 | ~100 °C/W | 17 °C | **87 °C** — comfortable |
| DFN with thermal pad | ~60–80 °C/W | 10–14 °C | **80–84 °C** — best |

So SOT-23-5 is **viable**, not excluded — but it spends most of the margin. Given this lives in a car and margin is cheap here, **SOT-89 or a small thermal-pad DFN is the better buy**, and both are far smaller than the SOT-223 you objected to.

### 2.10a The constraint that actually drives Rail A: dropout, not current

With a battery in the design, **dropout voltage sets how much of the cell you can use** — and it is now a harder constraint than either current or thermals.

The LDO input is the charger's SYS output, which follows the battery when unplugged. Li-ion runs 4.2 V down to ~3.0 V. To hold 3.3 V out:

| LDO dropout @ 280 mA | Cutoff input | Cell capacity usable |
|---|---|---|
| 150 mV | 3.45 V | **~87 %** |
| 250 mV | 3.55 V | ~83 % |
| 400 mV | 3.70 V | ~75 % |
| **1.2 V (NCP1117 as fitted)** | **4.50 V** | **0 % — will not run on battery at all** |

**This is what rules out the current part**, independent of its footprint. Selection criteria for Rail A:

- **Dropout ≤ 250 mV at 300 mA** — the binding spec; every 100 mV costs several percent of runtime
- **≥ 500 mA rated** — covers the 280 mA transmit peak with margin
- **SOT-89 or thermal-pad DFN** (§2.10)
- Quiescent current in the tens of µA, since it runs from a battery

**Rail B is a different problem entirely.** ~20 mA, ~22 mW — thermals and current are irrelevant. Choose it on **noise and PSRR**, because it feeds a 96 dB-dynamic-range codec sitting next to a radio.

**Verified part for Rail B — TI LP5907MFX-3.3/NOPB (C80670):**

| | |
|---|---|
| JLCPCB tier | ✅ **Economic and Standard**, MSL 1 |
| Package | SOT-23-5 — small, which is fine at 20 mA |
| Price / stock | ~$0.08, 59,000+ at LCSC |
| Why this one | Purpose-built ultra-low-noise LDO for RF and analog rails: ~6.5 µV<sub>RMS</sub> output noise and high PSRR **without a noise-bypass capacitor** — 1 µF in, 1 µF out and done. 250 mA rating is ample for 20 mA. |

### 2.10b Candidate LDOs — all verified on JLCPCB, 2026-08-24

Every part below was checked on its live JLCPCB part page: **all six are `Economic and Standard`
and MSL 1**, so none of them jeopardises the §2.1b assembly plan or needs baking. Prices are LCSC
single-unit and will move — re-check at BOM freeze.

#### Rail A — digital/RF (155 mA avg, 280 mA peak). Ranked.

| | Part | LCSC | Package | I<sub>max</sub> | Dropout | Why |
|---|---|---|---|---|---|---|
| **1** | **AP7361C-33Y5-13** | C460397 | **SOT-89-5** | 1 A | ultra-low | **Recommended.** The package the thermal analysis actually points to (~100 °C/W → ~87 °C junction at 70 °C ambient), 1 A rating gives generous headroom over the 280 mA peak, and ultra-low dropout preserves battery capacity. Materially smaller than the SOT-223 you objected to. |
| **2** | **AP2112K-3.3TRG1** | C51118 | SOT-23-5 | 600 mA | 250 mV typ (400 mV @ 600 mA) | **The small option.** Thermally viable at the 0.17 W average (~104 °C at 70 °C ambient) but spends most of its margin. Extremely common, cheap, well-stocked. Pick this if board area matters more than thermal headroom. |
| **3** | **AP7361C-33E-13** | C500795 | SOT-223 | 1 A | ultra-low | **The safe option.** Same silicon as #1 in the large package — maximum thermal margin, no ambiguity. Only choose it if #1 proves hard to place, since it is the footprint you wanted to move away from. |

*Note:* the AP7361C family also exists in U-DFN3030, which would be the best area-vs-thermal
compromise — but the LCSC listing and the JLCPCB part page disagreed on which suffix maps to which
package (C500795 turned out to be SOT-223, not DFN). **If you want the DFN, confirm the exact part
number on the JLCPCB page rather than trusting the suffix.**

#### Rail B — codec analog (~20 mA). Chosen on noise, not current.

| | Part | LCSC | Package | Noise | Why |
|---|---|---|---|---|---|
| **1** | **LP5907MFX-3.3/NOPB** | C80670 | SOT-23-5 | **~6.5 µV<sub>RMS</sub>** | **Recommended.** Purpose-built ultra-low-noise LDO for RF and analog rails. High PSRR **with no noise-bypass capacitor** — 1 µF in, 1 µF out and done, which saves a part and a BOM line. ~$0.08, 59 k in stock. |
| **2** | **TPS7A2033PDBVR** | C2862740 | SOT-23-5 | low, high PSRR | Solid alternative aimed at the same job. Very low quiescent current, which matters on battery. ~$0.14, 59 k in stock. |
| **3** | **SGM2019-3.3YC5G** | C122713 | SOT-23-5 | ~30 µV<sub>RMS</sub> | Cheaper, and still a genuine low-noise part. Noisier than the LP5907 by ~5×, which is likely inaudible here but gives away margin for little saving. **TLV70233DBVR (C26833, ~$0.10)** is a comparable budget option. |

**Both rails end up in different packages for different reasons** — Rail A on SOT-89 for thermal
margin under transmit load, Rail B on SOT-23-5 because at 20 mA the only thing that matters is
noise. That is the point of splitting them.

### 2.3 JLCPCB part library tier (Basic / Preferred / Extended)

JLCPCB/LCSC parts carry a library tier that affects assembly cost independent of the PCBA tier above:
- **Basic / Preferred parts** — pre-loaded on the assembly line, no setup fee, generally better stock depth.
- **Extended parts** — a per-line setup fee (commonly ~$3) applies, and stock is less predictable.

**Rule:** prefer Basic/Preferred for anything generic — passives, connectors, common logic, LEDs, test points. Extended is acceptable, and often unavoidable, for a genuinely unique part (the main MCU/module, the audio codec) — but shouldn't be used by default for parts that have a Basic equivalent.

**Process rule:** verify a part's actual current stock and library tier before locking a BOM line, rather than trusting a datasheet or a prior design in isolation — stock and tier both change over time. The KiCad MCP server has JLCPCB catalog tools (`search_jlcpcb_parts`, `get_jlcpcb_part`, `suggest_jlcpcb_alternatives`) for this; they need a one-time local database download (`download_jlcpcb_database`, ~1.5 GB) before they return anything. That download wasn't able to complete during this review (see note in §5) — run it before finalizing the v2 BOM, and re-verify the specific line items called out there.

### 2.4 Complexity ceiling

- **Layer count:** default to **4-layer** for this board. *(Revised in v1.2 — the original "default to 2-layer" rule here was a generic cost/complexity heuristic applied without checking it against this design or against JLCPCB's own capability data already gathered in §2.1: Economic PCBA explicitly supports 2/4/6-layer at no assembly-tier penalty, so 4-layer isn't an Economic-vs-Standard trade-off at all. For a mixed-signal board — RF, analog audio, and digital switching sharing one board — a dedicated ground/power plane gives every signal a solid, low-impedance return path, which is both a real signal-integrity win (cleaner RF reference, less digital noise coupling into the audio path) and, in practice, *simpler* to route than fighting for a clean single-layer ground pour on 2-layer. Drop to 2-layer only if a specific reason favors it later — e.g. fab-cost delta starts to matter at a production volume well beyond the hobbyist batch sizes this project targets — not by default.)*
- **RF layout:** avoid hand-tuned matching networks and controlled-impedance routing unless there's no certified-module alternative (see §2.2). If custom RF work is ever unavoidable, the matching network sizing must be written down with the calculation — not left as "TODO" — and ideally checked with a low-cost tool (a NanoVNA, roughly $50–100) before committing to a PCB run, since a bad match isn't visible until the board is built and tested.
- **Debug/programming provisioning:** don't add an interface "just in case." Each flashing/debug path should trace to an actual near-term need. Low-cost headers (a few passives, one connector) are fine to keep even if only one path ends up used day-to-day — the rule is about intentionality, not zero-cost items.
- **Power rails:** minimize distinct regulated rails; every additional one is cost, board area, and a new failure mode. Two rails (3.3 V, 1.8 V) is a reasonable ceiling for a board this size.

### 2.5 Requirement quality bar

Every requirement needs a measurable acceptance criterion, not just a description. "High quality audio" isn't verifiable as written. Either replace it with a number (target THD+N, SNR, or "audibly comparable to reference device X") or explicitly record that it's a subjective, informal bar for a hobbyist build — either is fine, but it should be a stated decision, not an implicit gap.

### 2.6 Firmware vs. hardware completeness

"Complete (schematic)" means the circuit exists, not that the feature works. Anything gated on firmware/SDK behavior (A2DP sink, HFP profile, I2S full-duplex configuration) needs its own separate firmware/bench verification step and shouldn't be counted as done just because the schematic is.

### 2.7 Cost & volume target — proposed, needs confirmation

No unit-cost or batch-size target exists anywhere in the source material, and "is this achievable on a hobbyist budget" can't really be judged without one — it also changes real decisions (Economic PCBA caps at 50 pcs; Standard doesn't, but costs more per board below that). **✅ CONFIRMED 2026-08-23 (decision D5):**

| | |
|---|---|
| **Quantity** | **5 assembled + 5 bare boards.** Flexible if assembly proves expensive. |
| **Target** | **$20 USD landed per unit**, slightly flexible |

**This target is tight, and the fixed costs are why.** At 5 assembled boards, per-design charges are divided by 5, so they dominate:

| Cost | Note |
|---|---|
| Feeder loading (Economic tier) | Largely avoided — this is the main reason the §2.1b self-populate plan matters at this quantity |
| Stencil | ~$8–15, once — and **mandatory**, since you are hand-placing a 0.35 mm-pitch QFN (§2.1b) |
| PCB fabrication, 4-layer | The 5 bare boards share this run, which is the efficient way to buy them |
| Components | ~$8–12/board *estimated*, before the battery circuit adds ~$2 |
| ESP32 bought separately | $1.58–1.84 + **shipping**, which at this quantity is a real line item, not a rounding error |

**MOQ items to check before assuming $20 is reachable** — flagged, not yet verified:
- **JLCPCB assembly has a 2-piece minimum** and Economic caps at 50, so 5 is comfortably inside the window.
- **Component MOQs bite at this scale.** LCSC sells many passives in minimum reels or strips of 50/100; the *unit* price is trivial but the *minimum purchase* is not. Expect to buy more of several lines than you need.
- **Distributor shipping for the self-populated ESP32** can exceed the part cost several times over at qty 5. Batch it with the NanoVNA and anything else needed (§2.9) into one order.

**Realistic read:** $20/unit at qty 5 is achievable *only* if Economic tier holds and BOM lines stay lean. If the quote comes back high, the cheapest lever is raising the assembled quantity — fixed costs divide further — not stripping features. **Get a real instant quote before committing to the target.**

### 2.8 Documentation, SDK, and toolchain accessibility

A part is only actually usable on this project if its datasheet, application notes, and — for anything with firmware or register-level configuration (MCUs, Bluetooth/RF SoCs, audio codecs, USB bridges) — its SDK or programming reference are publicly reachable, with no NDA, no distributor account gated behind a large purchase, and no signed supplier agreement required just to see how the part works. This isn't a new idea for this project; it's why ESP32 was picked over a Qualcomm Bluetooth chipset in the original trade study (`calculations.xlsx` → Specifications, row 10: "Toolchain and SDKs available to hobbyists" → "Use ESP / Nordic instead of Qualcomm") — it just was never written down as a standing rule until now.

**Rule:** before shortlisting any part with firmware or config surface, confirm its datasheet and any SDK/driver code are downloadable from a normal browser — no login, no NDA, no MOQ gate. If a part's real capability can only be discovered by placing an order or signing paperwork, treat that as disqualifying for a hobbyist build, not just an inconvenience — you can't design against documentation you don't have. Active community traction (forums, example projects — e.g. the ESP32-LyraT reference this project already leans on for the audio subsystem) is a strong positive signal on top of formal documentation, not a substitute for it.

---

## 3. Requirements Traceability Matrix

Each requirement ID can be referenced from KiCad component annotations, commit messages, or PR descriptions (e.g. "implements REQ-PWR-03").

### 3.1 Power Subsystem

| ID | Requirement | Consideration | Implementation | Status | Schematic Ref | Notes |
|---|---|---|---|---|---|---|
| REQ-PWR-01 | Powered from car battery via USB cable into cigarette lighter socket | Vin = dirty 5V; LDO tolerant of 3.3–12V input | Wide-range LDO regulator | ✅ | `power.kicad_sch`: J2 (USB-C receptacle), U7 (NCP1117-3.3, SOT-223) | **Note:** actual input connector is USB-C, so real-world Vin ≈ 5V from a USB car charger, not raw 12V battery. See §6.1 re: dropped automotive-transient protection. |
| REQ-PWR-02 | Current sufficient to power Micro, codec, Bluetooth comms | Budget ~300 mA (1.5× safety factor) | NCP1117 (1 A rated) | ✅ | U7 | Comment in source: *"Need to find a smaller regulator"* — reviewed in §5 (P2) and recommended **won't-fix**: SOT-223 dissipates only ~0.5W here, well within margin, and is a cheap Basic-tier part. **UPDATED 2026-08-23:** owner flagged the SOT-223 footprint as larger than wanted — justified. With the load split across two rails and the charger capping input at 4.4 V, Rail A peak dissipation drops from 0.51 W to 0.31 W, so a **SOT-89 or thermal-pad DFN** now works. Do not drop to SOT-23-5 (132 °C junction at automotive peak). Full budget in §2.10. |
| REQ-PWR-03 | ESP32 VCC = 3.3 V | Primary LDO = 3V3 | — | ✅ | U7 → ESP32 VDD nets | |
| REQ-PWR-04 | Audio codec AVDD = 3.3 V | Run off primary LDO | — | ✅ | U7 → ES8388 AVDD | |
| REQ-PWR-05 | ~~Audio codec DVDD = 1.8 V~~ → **Codec digital supply = 3.3 V** | ~~Secondary linear regulator~~ → must match the ESP32's logic levels; preferably a *dedicated* 3.3 V LDO so the codec's analog supply is isolated from ESP32 RF current bursts | ~~TLV71318 (1.8 V)~~ → refit U3's footprint with a 3.3 V LDO (e.g. TLV70233 / AP2112K-3.3) | ❌ **WRONG AS BUILT** | U3 (TLV71318PDBV) | **S1 defect — RESOLVED IN PLAN 2026-08-23: run the ES8388 from its own dedicated 3.3 V LDO (Rail B, §2.10).** This fixes the level incompatibility and the shared-noisy-rail finding together. ES8388 pin 3 `PVDD` is the *digital I/O* supply, not just a core rail. At 1.8 V the codec's logic is incompatible with the 3.3 V ESP32 in **both** directions — see REQ-AUD-02. The 1.8 V figure came from `calculations.xlsx` ESP-32!B12, which copied the datasheet's *typical* value without checking it against the host MCU. The codec datasheet permits 1.5–3.6 V, and the project's own LyraT reference runs every codec rail at 3.3 V. **Fix: delete the 1.8 V rail entirely.** *([review §3.2(a)](design-review-v1.md))* |

### 3.2 Audio Subsystem

*Reference design: [ESP32-LyraT v4.3](https://dl.espressif.com/dl/schematics/ESP32-LYRAT_V4.3-20220119.pdf)*

| ID | Requirement | Consideration | Implementation | Status | Schematic Ref | Notes |
|---|---|---|---|---|---|---|
| REQ-AUD-01 | High quality audio | ESP32's built-in DAC insufficient; use separate stereo codec | ES8388 (Everest Semiconductor), I2C config + I2S audio (codec as slave), QFN-28 0.4mm pitch | ⚠️ (was ✅) | `audio.kicad_sch`: U4 (ES8388) | Part choice is **good** — cheapest option with both ADC and DAC ($0.51), and Economic-tier eligible. But four defects sit against it: **(1) S1 — `CE` (pin 26) is floating**; the user guide states it "should be pulled up to PVDD or pulled down to DGND" and it sets the I²C address (0x20 low / 0x22 high). A floating address may make the codec unaddressable → no audio at all. Fix: pull down to DGND. **(2)** `AVDD`/`HPVDD` share +3V3 with no 10 Ω between them, contrary to the user guide (the four 10 Ω parts R7–R10 went onto the *outputs* instead). **(3)** Codec analog supply shares the ESP32's rail, which sees ~250 mA Bluetooth TX bursts; the guide asks for a dedicated LDO and LyraT uses a separate `Codec_3V3`. **(4)** 1 µF 0402 Class-II MLCC output coupling caps (C23/C25) will add distortion — the user's own "check dielectrics" TODO, and the most likely audible weak point. No measurable acceptance criteria yet (§2.5) — see proposed REQ-AUD-06. *([review §3.2](design-review-v1.md))* |
| REQ-AUD-02 | Full-duplex audio in/out (needed for future handsfree) | Required for ES8388 ↔ ESP32 I2S link | — | ❌ **NOT MET** (was ✅) | U4, ESP32 I2S pins | **S1 defect — the record path cannot work as built.** With PVDD at 1.8 V the codec drives `ASDOUT` at ~1.8 V. The ESP32 datasheet gives `VIH(min)` = 2.475 V and `VIL(max)` = 0.825 V, so **1.8 V falls in the forbidden zone — neither a valid high nor low.** Behaviour is undefined and varies with die/temperature/supply, so it may appear to work on the bench and fail in the car. Fixed by REQ-PWR-05. Separately, the ESP32 drives 3.3 V into codec pins whose absolute maximum is DVDD+0.3 V = 2.1 V. *([review §3.2(a)](design-review-v1.md))* |
| REQ-AUD-03 | Audio out over aux cable | Stereo 3.5 mm jack; ES8388 drives one output channel to it | — | ✅ | `audio.kicad_sch`: J1 (`AudioJack4_Ground`) | J1 is a 4-pole (TRRS) jack, not a simple 3-pole barrel — **confirm this is intentional** (e.g. reserved ring for future use) rather than a mismatch with the "stereo barrel jack" wording. **DECIDED 2026-08-23:** switch to a **3-pole TRS** jack. TODO for the schematic pass. A second jack is now also needed for TX input (REQ-AUD-07). |
| REQ-AUD-04 | Audio in via onboard microphone | PDM digital mic rejected — ES8388 can't do digital mic in; ES8388 recommends differential **analog** mic in (L1–R1, L2–R2) | Analog differential MEMS microphone | ⚠️ (was ✅) | `audio.kicad_sch`: MK1 (ICS-40720, analog differential output) | Circuit approach is right (differential analog, as the codec guide recommends). Two problems: **(1) the ICS-40720 is discontinued** by TDK InvenSense — still listed at JLCPCB (C3171779) but end-of-life; **(2)** the signal path is dead anyway until REQ-AUD-02's level-shift defect is fixed. Since this part exists solely for the deferred HFP feature (REQ-MCU-03), the review recommends **dropping the mic from v2** and re-selecting a current part when HFP is actually built — that also deletes the bias network and 4 caps. Mic `VDD` additionally has no RC filter. *([review §4.8](design-review-v1.md))* **UPDATED 2026-08-23:** HFP is now in scope (D3), so this is a live requirement rather than deferred provisioning. Replacement part identified: **Knowles SPH8878LR5H-1 (C3171733)** — LGA-6, MSL 1, JLCPCB *Economic and Standard*, and supports **both differential and single-ended** modes, so it keeps the ES8388's preferred differential connection while leaving a fallback. The bogus bias network must go regardless — see [`mems-microphone-primer.md`](mems-microphone-primer.md). |
| — | *(unlabeled row in source, Specifications!row 53 — blank requirement/consideration text)* | — | — | 🔲 | — | Ambiguous row with no content; recommend cleaning up in the spreadsheet or confirming nothing was meant to go here. |

### 3.3 Microcontroller

| ID | Requirement | Consideration | Implementation | Status | Schematic Ref | Notes |
|---|---|---|---|---|---|---|
| REQ-MCU-01 | Connects to all phones, not just recent ones | Rules out BLE Audio; use Bluetooth Classic | ESP32-D0WD-V3 | ⚠️ (was ✅) | `micro.kicad_sch`: U1 (QFN-48, 0.35mm pitch) | **The silicon choice is correct and effectively forced** — only the original ESP32 die has Bluetooth Classic hardware at all (S3/C3/C6/H2 are BLE-only), so this requirement pins the design to it. But: **S1 — ESP32 `CAP1` (pin 48) is missing its required 10 nF ±10 % capacitor to GND.** Espressif's hardware design guidelines §3.12 state this cap "is required for proper operation of ESP32." `CAP2`'s RC network is genuinely optional (it only affects deep-sleep entry, which a car-powered device never uses) — so leave CAP2 unpopulated *deliberately* and note why. This resolves the user's own "Check CAP1, CAP2 pins" TODO with a different answer per pin. Recommended change: move to **ESP32-WROOM-32E-N4**, which uses the same D0WD-V3 die (Classic retained) — see decision log §4. *([review §3.3(a), §4.1](design-review-v1.md))* **NORDIC CHECKED 2026-08-23 (D-request), CLOSED:** no Nordic part is viable. The entire nRF portfolio — nRF52, nRF53, nRF54 — is **Bluetooth LE only**; none supports Bluetooth Classic or A2DP. Nordic's audio answer is LE Audio, which is precisely what REQ-MCU-01 rules out. The ESP32 selection stands and should not be revisited on this axis. |
| REQ-MCU-02 | Can act as a Bluetooth sink (phone streams music to it) | Requires A2DP profile support | — | ✅ (schematic); 🔲 (firmware) | U1 | Source comment: *"double confirm"* ESP32 BT stack supports this — hardware is ready, firmware capability unverified (§2.6). |
| REQ-MCU-03 | **Can act as a handsfree device — IN SCOPE (D3)** | Requires HFP profile support | — | 🔲 | U1 | Hardware (full-duplex I2S, mic) is in place; firmware/profile support not yet verified. |
| REQ-MCU-04 | Can store program in flash | ESP32 needs external flash | W25Q32JVZP (32 Mbit / 4 MB, WSON-8 1.27mm pitch) | ⚠️ (was ✅) | `micro.kicad_sch`: U6 | Correct part and correct 3.3 V variant (`JV`; the 1.8 V `JW` would have been wrong), and the SDIO pin group matches Espressif's Slot-0 table. **But S2 — `IO2` and `IO3` are swapped:** GPIO9 (SD_DATA_2) reaches flash pin 7 (IO3) and GPIO10 (SD_DATA_3) reaches flash pin 3 (IO2), verified against the W25Q32JV pinout. Harmless in **DIO/DOUT** mode (those pins are just held high, so the board boots and looks healthy) but **corrupts every read in QIO/QOUT** mode — a dormant bug that fires the day someone enables quad mode for speed. Fix: swap the two nets, or move to a module and the external flash disappears entirely. *([review §3.3(b)](design-review-v1.md))* |
| REQ-MCU-05 | Option to reset the ESP32 | Pull EN to ground; auto-download circuit on DTR/RTS | 2-pin EN/GND test point + transistor auto-program circuit | ✅ | TP1 (`TEST_EN`), Q1 (UMH3N) | |
| REQ-MCU-06 | External crystal for ESP32 | Load caps per Espressif HW design guide | 40 MHz crystal, load caps | ⚠️ (was ✅) | Y1, C35/C36 (2×18pF) | **Load caps look mis-derived.** Y1 is labelled CL = 10 pF; Espressif's formula `CL = (C1×C2)/(C1+C2) + Cstray` gives 9 pF + stray ≈ **11.5–12 pF** with 2×18 pF, i.e. over-loaded → frequency pulled low. A 10 pF crystal calculates nearer 2×15 pF. The guidelines require trimming the offset to **±10 ppm** and warn that missing it causes Wi-Fi/Bluetooth connection failures. **Closing this properly needs a spectrum analyser and Espressif's test tool — not realistically available here**, which is a strong argument for the module. Separately, the series element on XTAL_P is 0 Ω (R13) where the guidelines suggest starting at 24 nH to suppress crystal harmonics. *([review §3.3(c)(d)](design-review-v1.md))* |
| REQ-MCU-07 | Visual indicators | 3 LEDs planned (blue/green/red); reduced to 2 (blue/green) | — | ⚠️ (was ✅) | D1, D3 | LEDs are present but **under-driven**: with 1 kΩ on a 3.3 V rail, the blue LED (Vf ≈ 3.0 V) gets ~0.3 mA — effectively invisible, and hopeless in daylight in a car; green fares a little better at ~1.3 mA. An indicator you can't see doesn't meet the requirement. Fix: ~330 Ω. Comment "TODO on free GPIOs" still open, not blocking. *([review §3.5(d)](design-review-v1.md))* |
| REQ-MCU-08 | Low-cost onboard antenna | 2.4GHz PCB trace antenna, inverted-F, meandered; PI matching network; 50Ω controlled-impedance traces; solid ground plane under RF (4-layer PCB) | Meandered inverted-F trace antenna + matching inductor | ⚠️ | ANT1, L1 (2.2 nH) | **Antenna and matching component are placed, but controlled-impedance trace routing and the 4-layer ground-plane strategy are explicitly marked incomplete in source.** PI network sizing itself is flagged "TODO." Top RF-risk open item — see §5 (P0/P1), and §2.2/§2.4 for the standing rule this violates. |
| REQ-MCU-09 | Programmable over USB | ESP32-D0WD has no built-in USB-UART or USB peripheral (unlike ESP32-S/C variants); needs external bridge | CH340K on-board bridge + USB-C connector | ✅ | U2 (CH340K, SSOP-10 1mm pitch), J2 (USB-C) | Rows about "no built-in USB-UART" and "no SWD" are factual limitations of the chosen chip, not incomplete work — resolved as ➖, not open gaps. |
| REQ-MCU-10 | EMI protected | Ungrounded USB shield (ground on source side); ESD protection on USB lines | USBLC6-2SC6 | ✅ | U5 | |

### 3.4 Development / Programming & Debug

| ID | Requirement | Consideration | Implementation | Status | Schematic Ref | Notes |
|---|---|---|---|---|---|---|
| REQ-DEV-01 | Must be able to flash code to the board | Need control of EN/BOOT; no built-in USB-UART or USB peripheral on this ESP32 variant | Three supported paths: (1) on-board CH340K auto-program via DTR/RTS transistor circuit, (2) manual off-board USB-serial + manual EN/BOOT toggle via test points, (3) ESP-PROG via JTAG header | ✅ | U2 (CH340K), Q1, TP1/TP3 (EN/BOOT), J4 (JTAG header) | CP2102 was evaluated for the on-board bridge and rejected in favor of CH340K — resolved choice, not a contradiction. Reviewed in §5 (P1): three simultaneous paths is more provisioning than a solo hobbyist project typically needs; low cost to keep, flagged as a pattern to avoid defaulting to in future designs. |
| REQ-DEV-02 | Must be able to debug code | JTAG can be broken out; connect via ESP-PROG; SWD not applicable (Xtensa, not ARM) | 2×5 JTAG header | ✅ | J4 | On the back side of the board (§2.1) — candidate to move to the front along with the other back-placed parts. |
| REQ-DEV-03 | Able to probe key points | I2C, mic input, spare mic, audio out, audio out spare, boot pin+GND, spare GPIOs, VDD/VDDSDIO, GND | Dedicated test points | ✅ | TP2–TP15 (13 points total; TP5/6/7/9 on the back side) | Source spreadsheet left this row block's status column blank; marked Complete here based on direct schematic evidence. |

### 3.4a Scope decisions — RESOLVED 2026-08-23

Answered by the owner via the review artifact. These close the open questions that were gating design work.

| # | Decision | Answer | Consequences |
|---|---|---|---|
| **D1** | Battery in scope? | ✅ **In scope.** | Power architecture is rebuilt around a charger + power path. See [`battery-power-proposal.md`](battery-power-proposal.md). **Note:** "retain state across power-off" is *not* a reason — the ESP32 stores Bluetooth bonding keys in NVS flash automatically, so pairing already survives power loss with no battery. The justification is ground-loop breaking and portable use. |
| **D2** | Lives permanently in a hot car? | ❌ **No** — will be removed. | The lithium storage hazard is mitigated by usage, not by circuit. NTC charge qualification stays **mandatory**. LFP was considered and rejected — see battery proposal §2. |
| **D3** | HFP ever happening? | ✅ **Yes — needs provision.** | REQ-MCU-03 moves from *Future* to *In scope*. The mic stays, ES8388 stays (a DAC-only part is now ruled out), and the record path must actually work — which makes the S1 rail defect blocking rather than deferred. |
| **D4** | TX mode in scope? | ✅ **In scope.** | New REQ-AUD-07. The Overview's TX mode stops being an unimplemented claim. Needs a jack input path — plan below. |
| **D5** | Build quantity / cost target? | **5 PCBA + 5 bare boards. Target $20 USD landed per unit**, flexible on both if boards are expensive. | Replaces the §2.7 placeholder. Tightens the cost model — see §2.1a and the MOQ check in §5. |

### 3.4b New requirements from those decisions

| ID | Requirement | Notes |
|---|---|---|
| **REQ-AUD-07** | Device shall accept line-level analog audio from a 3.5 mm jack and stream it over Bluetooth (TX mode). | **Two implementations, both viable — owner asked about switching a single socket (2026-08-24).** **(a) One socket + analog switch — feasible and now the leading option.** TI **TS5A23159DGSR (C42751)**: dual SPDT, so one part switches both L and R; 1 Ω on-resistance, break-before-make, 1.65–5.5 V, ✅ JLCPCB *Economic and Standard*, VSSOP-10 at 0.5 mm (clears the 0.4 mm floor), ~$0.28. Driven by one spare GPIO. Audio cost is negligible: 1 Ω into a ~10 kΩ AUX load is −0.001 dB, and the switch's THD sits well below the ES8388's own −83 dB. **⚠️ Critical placement rule: put the switch on the CODEC side of the coupling capacitors, not the jack side.** An analog switch can only pass signals inside its own supply rails. On the codec side both paths sit at VMID (~1.65 V), comfortably inside 0–3.3 V. On the jack side the signal is centred at 0 V, so every negative half-cycle would be clipped by the switch. One pair of coupling caps then sits between the switch common and the jack. **(b) Two jacks labelled IN and OUT.** No active device in the signal path, unambiguous to use, but two connectors and more panel space. **Recommendation: (a) if panel space or a single-socket product feel matters — it is a sound design and the parts are confirmed available. (b) if you would rather keep the audio path entirely passive.** Either way, watch input level: ES8388 full scale is ~1.0 Vrms and its PGA only adds gain, so a headphone-level source needs a resistive divider. |
| **REQ-PWR-11** | Two independent 3.3 V rails: one for digital/RF, one dedicated to the codec analog section. | Resolves both the S1 level-shift defect and the codec-supply-noise finding in one change. Sizing in §2.10. |

### 3.5 Proposed new requirements (raised by the design review, v1.3)

These cover gaps the review found in the requirements themselves — things the product needs that no requirement asked for. **Status: proposed, pending your confirmation.**

| ID | Requirement | Rationale | Verification | Status |
|---|---|---|---|---|
| **REQ-AUD-05** | Audio output shall not exhibit audible ground-loop noise (alternator whine) when powered from the vehicle's electrical system while connected to the head unit's AUX input. | **The classic failure mode for this exact product category, and currently unaddressed.** The board bonds chassis ground (via the cigarette-lighter USB charger) to the head unit's audio ground (via the AUX sleeve, `J1.S`/`J1.G`). Circulating current between them appears as engine-speed-dependent whine. There is one GND net and no isolation anywhere. **The project already knew about this and lost it:** `calculations.xlsx` → System design!B5 is literally "Noise and interference" linking a diyAudio thread on exactly this problem — it never reached the finalised spec. | Listen across the engine RPM range, engine running, in the target vehicle. | 🔲 Proposed |
| **REQ-AUD-06** | Give REQ-AUD-01 a testable acceptance criterion. Suggested: no audible hiss at maximum volume with no input signal, and no audible distortion at full scale into a 10 kΩ AUX load. | Closes the §2.5 gap this document already flagged — "high quality audio" is currently unverifiable as written. Deliberately informal, which is appropriate for a hobbyist build; the point is that it's *decidable*. | Listening test at stated conditions. | 🔲 Proposed |
| **REQ-ENV-01** | Define operating ambient temperature range (suggested −20 °C to +70 °C for a car interior), enclosure, and connector retention/strain relief. | **Currently entirely unspecified.** The review's thermal analysis of U7 had to *assume* an ambient because none exists — and the answer materially changes the regulator verdict (see §5 P2-7). A device that lives on a dashboard also needs mechanical definition. | Datasheet temperature ratings checked against the stated range for every part. | 🔲 Proposed |

**Recommended implementation note for REQ-AUD-05:** don't commit to a solution blind. Lay out LOUT1/ROUT1 so R7/R8 can be fitted as either 0 Ω links *or* 1:1 audio isolation transformers, so v2 can be tested both ways on a single board spin. Cheap insurance against a problem that otherwise only reveals itself after the boards exist, in a car.

---

## 4. Design Decision Log (Trade Study)

*Source: `calculations.xlsx` sheets "System design", "ESP-32", "STM32WB".*

| Option | Vendor | Verdict | Rationale |
|---|---|---|---|
| **ESP32-D0WD-V3** | Espressif | ✅ **Selected (v1)** | Supports Bluetooth Classic (A2DP/HFP) *and* BLE — needed for broad phone compatibility. Mature hobbyist toolchain/SDK (vs. Qualcomm). Trade-offs accepted: needs external flash, no built-in USB-UART/USB peripheral, no built-in high-quality DAC (external codec required). **Now the #1 v2 recommendation to revisit (§5, P0):** its QFN-48 0.35mm pin pitch is the primary driver forcing Standard-tier PCBA and the associated cost increase (per commit `369c5f9`). |
| nRF5340 Audio DK | Nordic | ❌ Rejected | Reference design pairs nRF5340 with a Cirrus CS47L63 audio DSP, but the platform is **BLE-only** — fails the "connect to all phones" requirement (many phones don't support BLE Audio/LE Audio yet). |
| NXH3670UK | NXP | ❌ Rejected | Ultra-low-power BLE Audio transceiver + DSP — same BLE-only limitation as Nordic. |
| STM32WB | ST | ❌ Rejected | Explicitly ruled out in source: "only supports BLE audio which is not compatible with all phones currently." |
| Smart speaker reference design | TI | ❌ Not pursued | Noted as a reference link only; no further evaluation recorded in source. |
| (unnamed) | Microchip | 🔲 Not evaluated | Listed as a vendor to consider; no detail recorded — open research thread, not resolved either way. |
| ES8388 codec | Everest Semiconductor | ✅ **Selected** | ESP32's built-in DAC judged insufficient for target audio quality. ES8388 chosen as external stereo codec; ESP32-LyraT v4.3 used as reference design. QFN-28 0.4mm pitch is a secondary, borderline contributor to the PCBA-tier question (§2.1). |
| Buck converter (TPS5430) + automotive input protection (TVS, UVLO) | TI | ❌ Abandoned | Original concept assumed a **direct 12 V car-battery connection**, requiring a buck converter, ≥36 V-rated TVS, and 7 V UVLO for automotive transient survival. **Abandoned in favor of LDO-only** once the design settled on a USB-C connector fed by a USB car charger (~5 V input) rather than a raw battery tap — see §6 for the retained calculations and §6.1 for the protection gap this leaves open. |
| Adjustable LDO (LM317-style) | ST (LM317MDT) | ❌ Abandoned | Considered as an alternative to a fixed-output LDO; abandoned in favor of the fixed-output NCP1117-3.3 + TLV71318-1.8 pair actually used in the schematic (no resistor-divider tuning needed). |

---

## 5. Principal-Engineer Scope & Complexity Review (v1.1)

A pass through the requirements above as if scoping this for production on a hobbyist budget: is each item appropriately scoped, achievable with hobbyist tools/budget, and worth its complexity? Findings ranked by leverage — how much cost/risk each fix removes relative to effort.

### P0 — Fix before v2 layout starts (highest leverage)

**1. Replace the bare ESP32-D0WD-V3 with an ESP32-WROOM-32E module.**
This is the single highest-leverage change available. The bare chip requires, on top of itself: external flash (U6), an external crystal + load caps (Y1, C35/C36), a hand-derived RF matching network that was never actually sized (flagged "TODO — research how to size these components" in the source), and controlled-impedance trace routing (not done). A WROOM-32E module bundles flash, crystal, matching network, antenna, and FCC/CE/SRRC pre-certification into one part, at a coarser, hand-solderable, comfortably-Economic-tier pitch (castellated edge pads, ~1.27mm effective spacing). It removes an entire category of RF risk that a hobbyist has no easy way to verify before the board is built (a mis-sized matching network is invisible until you test range and it's poor), and it directly unblocks the Economic-PCBA / lower-cost outcome the project has been chasing since before v1 shipped. *(Note: this is independent of layer count — the board stays 4-layer either way, see §2.4.)*
*Trade-off to accept:* the module's line-item cost is higher than the bare die alone — but once you net out the eliminated flash IC, crystal, load caps, and matching components, plus the design time and DFM risk saved, this is very likely a net win even before counting the assembly-tier savings.

**2. ~~Move all back-side placements (J3, J4, TP5, TP6, TP7, TP9) to the front side.~~ — ❌ DOWNGRADED in v1.3.**
This was justified purely by unblocking Economic PCBA, and §2.1 now shows Economic is unreachable regardless. Back-side placement carries no cost penalty on Standard PCBA. **Demoted to a nice-to-have** (front-side test points are easier to probe during bring-up) — do it opportunistically if the board is being re-laid out anyway, but it does not justify a redesign cycle on its own.

**The real P0 list is now the three S1 defects in [`design-review-v1.md`](design-review-v1.md) §6** — codec digital rail at the wrong voltage, floating `CE` pin, and the missing `CAP1` capacitor. Those are correctness problems, not optimisations, and they outrank everything in this section.

### P1 — Worth resolving, moderate leverage

**3. RF matching network sizing is undocumented.** If item 1 is adopted this becomes moot (the module handles it internally). If a custom PCB antenna is kept for any reason instead, it can't ship again without the sizing calculation on paper and, ideally, a NanoVNA check (§2.4) — "TODO" isn't a design.

**4. ES8388's QFN-28 0.4mm pitch is a marginal Economic-tier case.** Once items 1–2 are resolved, this becomes the next thing standing between the board and Economic PCBA. Get a real JLCPCB instant quote rather than assuming it clears — it's right at the documented floor.

**5. Redundant flash/debug provisioning.** Three simultaneous paths (on-board CH340K, manual off-board serial + EN/BOOT toggle, JTAG via ESP-PROG) is more than a solo hobbyist project typically exercises day to day. Not wrong — the marginal cost is low — but worth naming as a pattern: go forward, justify each interface against an actual near-term need rather than defaulting to "provision everything" (§2.4). Not urgent to cut given the low cost already sunk.

### P2 — Low-cost / cosmetic fixes

**6. I2C pull-up value mismatch (spec: 1k, schematic: 4.7k).** ❌ **My v1.2 recommendation here was wrong and is withdrawn.** I argued that 4.7k is the more standard I²C value, concluded the spec text must be the error, and recommended changing the spec to match the schematic. In fact the ES8388 user guide — the document this spec already cites at Specifications!G47 — states explicitly: *"Two 1K pull up resisters are recommended to I2C bus."* **The spec was right and traceable to the vendor document; the schematic is the deviation.** 4.7k will very likely work in practice at these bus speeds and trace lengths, so this is not urgent — but the correct action is to justify the deviation or adopt 1k, *not* to rewrite the requirement to match what was built. Also unimplemented from the same page: the guide's recommended R-C low-pass filter on the I²C `CCLK` line.

*Process lesson, worth more than the resistor: I overrode a sourced requirement with a general heuristic. When a spec value disagrees with the schematic, find out where the spec value came from before assuming the spec is the error.*

**7. "Need to find a smaller regulator" comment on REQ-PWR-02. → Close as won't-fix — and the reasoning is stronger than v1.1 stated.** My earlier "comfortable thermal margin" claim was too relaxed: it assumed bench ambient. In a car interior reaching 60–70 °C, U7 dissipating ~0.34 W (5 V→3.3 V at ~200 mA) in SOT-223 (~60–100 °C/W) puts the junction near 100–110 °C against a 125 °C limit — adequate, but not comfortable.

That makes the "smaller regulator" idea **actively harmful**: shrinking the package makes thermal performance *worse*. An AP2112K in SOT-23-5 (~200 °C/W) at the same dissipation would rise ~68 °C, landing near 138 °C at automotive ambient — **over the limit**. **SOT-223 is a deliberate thermal choice and should be recorded as such so nobody "optimises" it later.** (Also depends on REQ-ENV-01 fixing an actual ambient — the analysis above assumes one.) *([review §3.1(a), §4.5](design-review-v1.md))*

### Confirmed as appropriately scoped — no action needed

- **Power architecture** (two fixed-output LDOs, no switching regulator, no resistor-divider tuning) is simple, cheap, hobbyist-appropriate, and thermally sound for the actual current budget. This is a good call worth keeping as-is, not just an absence of problems.
- **Onboard analog mic for the future HFP feature** is cheap to provision now (a handful of passives) against a full board respin later. Legitimate forward-compatibility, not scope creep — see the design-driver note added to §1.
- **USB-C input + LDO-only power** (dropping the original automotive TVS/UVLO concept) is appropriately scoped for the actual use case — a USB car charger, not a direct battery tap. Already tracked in §6.1 if a future variant needs to change this assumption.

### Gaps found in the requirements themselves (not just the circuit)

- **No unit-cost or batch-size target exists anywhere in the source material.** "Achievable on a hobbyist budget" can't be fully judged without one. Proposed default recorded in §2.7 — needs confirmation.
- **"High quality audio" has no acceptance criteria** (§2.5, REQ-AUD-01). Needs either a number or an explicit "subjective/informal" label.
- **The reason for choosing ESP32 + a separate codec over an all-in-one Bluetooth-audio SoC was never written down** — it's a reasonable trade (SDK-level firmware control, room for HFP/custom DSP later) but was implicit rather than stated. **Fixed directly in §1** rather than left as an open item, since it cost nothing to just write down.

### Process note

The JLCPCB live parts database (needed to verify current stock/library-tier for every part named above, per §2.3) could not be downloaded during this review — it's a ~1.5GB one-time fetch that didn't complete in the available tool time. The specific numbers above (pitch, package, assembly-side) come from direct inspection of the schematic/PCB files and are reliable; the *stock and Basic/Extended tier* claims are general knowledge, not verified against a live query. **Run `download_jlcpcb_database` once before finalizing the v2 BOM**, then re-check the specific parts flagged in P0–P2 above with `search_jlcpcb_parts` / `get_jlcpcb_part`.

---

## 6. Known Issues / v2 Candidates

Flagged for the next revision — not blocking the current baseline, but should be triaged before further production. *(See §5 for the prioritized, root-caused version of the manufacturing-cost items — this list is kept for anything not already covered there.)*

1. ~~Production cost — ESP32-D0WD-V3 fine pin pitch.~~ **Superseded by §5, P0/P1** — root-caused to two independent causes (chip pitch *and* back-side placement), with a concrete recommendation.
2. **Firmware-dependent items marked "complete" at the schematic level only:** A2DP sink support (REQ-MCU-02), HFP handsfree support (REQ-MCU-03), I2S full-duplex pin configuration (REQ-AUD-02). Hardware is ready; firmware/bench verification is outstanding (§2.6).
3. **Crystal load-cap value ambiguous.** Source text ("2× 18pF, 10pF") doesn't clearly match the as-built 2×18pF — confirm against Espressif's crystal design guidelines. Moot if REQ-MCU-01 moves to a module (§5, P0).
4. **Open PCB-layout TODOs** (from the "PCB checks" sheet, not yet resolved):
   - Check dielectric constants used for audio in-line coupling caps
   - Fix all DRC errors
   - Check CAP1/CAP2 pin connections on ESP32
   - Check USB connector footprint
5. **TRRS vs. barrel jack.** REQ-AUD-03 spec text says "stereo barrel jack"; as-built uses a 4-pole TRRS jack (`AudioJack4_Ground`). Confirm this is intentional (e.g. ring reserved for a future feature) rather than a footprint mismatch.

### 6.1 Automotive input protection

The earliest draft spec (rows 3–7 of the raw Specifications sheet) targeted a direct 12 V car-battery input and called for: a buck converter, a TVS diode on V_IN rated ≥100 V, and a 7 V UVLO. All three were dropped when the design moved to a USB-C connector powered by a USB car charger — the charger itself handles the raw battery voltage, so the board only ever sees a regulated ~5 V. **If a future variant is meant to plug directly into an unregulated 12 V rail (bypassing a USB charger), this protection needs to be reinstated** — it is not currently present anywhere in the schematic (no TVS diode in `power.kicad_sch`).

---

## 7. Future / Candidate Requirements (out of scope for v1)

Carried forward from the early draft spec list (Specifications rows 1–24) — not part of the finalized v1 spec, but worth keeping visible for scoping v2:

| Idea | Source | Notes |
|---|---|---|
| RF switch to enable/disable the onboard antenna, in favor of an off-the-shelf external 2.4 GHz antenna | Draft row 13 | No further detail recorded. Would let a board variant trade the PCB antenna's cost/simplicity for external-antenna range/reliability. Lower priority than §5 P0's module recommendation, which solves most of the same underlying risk more simply. |
| Multiple board variants | Draft row 14 | No detail recorded on what the variants would differ by (e.g. connector type, antenna, power input) — needs scoping if pursued. |
| Battery backup via coin cell + charging circuitry | Draft row 24 | Would let the device retain state (pairing, settings) or ride through brief power loss. Not designed or costed. |

---

## 8. Appendix A — Abandoned Power Calculations (historical only)

These calculations from the `Power` sheet are **not reflected in the as-built design** (which uses fixed-output LDOs, NCP1117-3.3 + TLV71318). Kept here purely as a record of the exploratory work — do not use these values for the current LDO-based design.

### A.1 Buck converter (TPS5430) — abandoned in favor of LDO-only

Target: 3.3 V output from up to 12 V input, 2 A budget, 650 kHz switching.

| Parameter | Value | Note |
|---|---|---|
| Feedback resistors | R1 = 33.2 kΩ, R2 = 10 kΩ (1% tolerance) | Vout = 0.765 × (1 + R1/R2) = 3.305 V |
| Output inductor | 3.3 µH (spec calc used 4.7 µH) | |
| Output capacitor | 68 µF (spec calc used 44 µF) | |
| LC filter pole | 11.07 kHz | |
| Inductor ripple current (Il p-p) | 0.784 A | |
| Inductor peak current | 2.39 A | |
| Inductor RMS current | 2.01 A | |
| Output cap RMS current | 0.226 A | Noted in source as not matching the datasheet's application-example value when checked |
| Output ripple voltage | 78 mV (at ESR = 0.1 Ω) | |
| Input caps | C1 = 47 µF bulk, C2 = 10 µF decoupling (ceramic), C3 = 0.1 µF HF filter, C4 = 0.1 µF bootstrap (ceramic); all rated 16 V | Source note: "consider increasing [C1] to prevent dropout on car start-up" |
| EN pin R-C soft-start | R = 100 kΩ, C = 22 µF (τ = 2.2 s); turn-on threshold V_EN = 1.6 V | |
| EN pin discharge | R = 1 kΩ (τ_off = 22 ms); Zener clamp V_Z = 3 V | Sized to stay under the 8 mA open-drain GPIO limit of the microcontroller originally driving it |

### A.2 Adjustable LDO (LM317-style) — abandoned in favor of fixed-output NCP1117-3.3

| Parameter | Value |
|---|---|
| V_ref | 1.25 V |
| R1 | 330 Ω |
| R2 | 526 Ω (suggested as 470 Ω + 56 Ω in series) |
| I_adj | 100 µA |
| Resulting V_out | 3.295 V |

---

## 9. Appendix B — As-Built Component Reference (by sheet)

Extracted directly from the KiCad schematics/PCB for traceability. Full BOM should be generated from KiCad (`export_bom`) for production — this is a quick-reference list of key ICs and structural parts, now including package/pitch since that's load-bearing for §2.1's manufacturing analysis.

**`power.kicad_sch`:** U7 NCP1117-3.3 (SOT-223, primary 3.3V LDO), U3 TLV71318 (SOT-23-5, 1.8V LDO), U5 USBLC6-2SC6 (SOT-23-6, USB ESD protection), J2 USB-C receptacle, D2 LED (3V3 indicator), TP2/TP13 (3V3/1V8 test points)

**`micro.kicad_sch`:** U1 ESP32-D0WD-V3 (**QFN-48, 0.35mm pitch** — see §2.1), U2 CH340K (SSOP-10, 1mm pitch, USB-UART bridge), U6 W25Q32JVZP (WSON-8, 1.27mm pitch, 4MB SPI flash), Y1 40MHz crystal, Q1 UMH3N (auto-program transistor pair), J4 2×5 JTAG header (**back side**), ANT1 meandered inverted-F 2.4GHz antenna, L1 2.2nH (antenna matching), D1/D3 status LEDs (blue/green), J3 6-pin connector (**back side**)

**`audio.kicad_sch`:** U4 ES8388 (**QFN-28, 0.4mm pitch** — borderline, see §2.1), MK1 ICS-40720 (analog differential MEMS microphone), J1 AudioJack4_Ground (TRRS 3.5mm jack)

**Back-side placements (blocks Economic PCBA regardless of pitch, §2.1):** J3, J4, TP5, TP6, TP7, TP9

---

## 10. Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-20 | Initial baseline — extracted from `calculations.xlsx` and cross-referenced against the completed v1 KiCad schematic (commit `369c5f9`). |
| 1.1 | 2026-08-20 | Added §2 Design Constraints & Guidelines (JLCPCB assembly tiers, module-vs-bare-silicon rule, part library tiers, complexity ceiling, requirement quality bar, cost/volume target) and §5 Principal-Engineer Scope & Complexity Review. Verified exact package/pitch and PCB side for every key IC directly against the schematic and `.kicad_pcb` files rather than assumption — found that back-side test points/headers independently block Economic PCBA alongside the ESP32's pitch. Root-caused and superseded Known Issue #1. Added an explicit design-driver statement to §1. |
| 1.2 | 2026-08-20 | Corrected §2.4: the v1.1 "default to 2-layer" rule was a generic heuristic applied without checking it against the JLCPCB Economic-tier data already in §2.1 (4-layer carries no assembly-tier penalty) or against this design's mixed-signal needs. Now defaults to 4-layer for signal-integrity and layout-simplicity reasons, per user correction. Updated the §5 P0 module-swap item to stop implying layer-count reduction as a benefit. Added §2.8, Documentation/SDK/toolchain accessibility — parts must have publicly reachable datasheets and SDKs, no NDA/MOQ/supplier-agreement gate, per user request; tied back to the ESP32-over-Qualcomm precedent already in the source data. |
| 1.3 | 2026-08-20 | **Netlist-level system design review completed → [`design-review-v1.md`](design-review-v1.md).** Corrections folded back here: **(a)** withdrew the Economic-PCBA goal entirely — every Bluetooth-Classic ESP32 part is "Standard Only" on JLCPCB, so it was never reachable; replaced §2.1 with a verified BOM-line cost model (~$1.50/unique part on Standard) and demoted the back-side-placement task that it justified. **(b)** Withdrew the v1.2 I²C pull-up recommendation — the spec's 1 kΩ came from the ES8388 user guide; I had wrongly overridden a sourced requirement with a general heuristic. **(c)** Downgraded REQ-MCU-01/04/06/07 and REQ-AUD-01/04 from ✅, and REQ-AUD-02 to ❌, on netlist evidence. **(d)** Rewrote REQ-PWR-05: the 1.8 V codec digital rail is wrong for a 3.3 V host and must become 3.3 V. **(e)** Corrected the Overview — TX mode is not implementable on v1 hardware. **(f)** Sharpened the regulator thermal reasoning for automotive ambient. **(g)** Added §3.5 proposing REQ-AUD-05 (ground-loop immunity), REQ-AUD-06 (testable audio criterion), REQ-ENV-01 (environmental/mechanical). |
| 1.4 | 2026-08-20 | Direction changes from the owner. **(a)** Added §2.2a — **RF front-end design is an explicit learning objective**, so the bare ESP32 is KEPT and the module recommendation is withdrawn (twice-made, now closed). Records the consequences knowingly accepted. **(b)** Added §2.9 — design exercises must be measurable; NanoVNA and a frequency-offset method are now project dependencies. **(c)** Added §2.1b — **Economic PCBA IS reachable** by excluding the ESP32 from assembly and hand-populating it; verified it is the only Standard-Only part. This **reverses v1.3's downgrade of the back-side-parts task**: Economic is single-sided only, so J3/J4/TP5/TP6/TP7/TP9 must move to the front or the tier is lost. **(d)** New [`battery-power-proposal.md`](battery-power-proposal.md) — lithium battery architecture, with the safety gate (lithium in a hot car) and the ground-loop synergy as its strongest argument. |
