# System Design Review — Bluetooth Audio Adaptor v1

**Reviewer:** Claude (acting as reviewing systems engineer)
**Date:** 2026-08-20
**Design under review:** `hw/bluetooth-audio/` at commit `369c5f9` ("Completed design with ESP32D0WD-v3")
**Companion doc:** [`requirements-design.md`](requirements-design.md) — every finding below is traced to a REQ ID where one exists, or proposes a new one where the requirement was missing.

---

## 0. How this review was done

This is a review against primary sources, not against my recollection of how these parts behave.

| Evidence source | What it was used for |
|---|---|
| **KiCad netlist export** (94 nets, 100 footprints, pin-level) | Every connectivity claim below. Generated via `kicad-cli` from `bluetooth-audio.kicad_sch`, then parsed pin-by-pin. |
| `esp32_datasheet_en.pdf` (local) | ESP32 pin functions, CAP1/CAP2, VDD_SDIO |
| `esp-hardware-design-guidelines-en-master-esp32.pdf` (local) | Crystal, RF matching, external capacitor, SDIO pin table |
| `1912111437_...ES8388_C365736.pdf` (local) | Codec pin functions, supply ranges, absolute maximums |
| `ES8388-user-guide-application-note.pdf` (local) | Codec application recommendations — this is the document the spec itself cites at Specifications!G47 |
| `2304140030_...W25Q32JVZPIQ_C571260.pdf` (local) | Flash pinout |
| `ESP32-LYRAT_V4.3-20220119.pdf` (local) | The project's own stated reference design |
| JLCPCB part pages (live, 2026-08-20) | PCBA tier eligibility, package, MSL |
| LCSC (live, 2026-08-20) | Unit pricing, stock |

**Confidence labelling used below:** *Confirmed* = verified against a primary datasheet or the netlist. *Estimated* = my calculation or a figure I did not independently verify. *Needs bench check* = cannot be settled from documents.

---

## 1. Correction to my previous review (v1.2) — I got the central cost argument wrong

Before the new findings, I need to withdraw the main recommendation from the last review.

In v1.1/v1.2 of the requirements document I argued the top priority was reaching **Economic PCBA**, and that swapping the bare ESP32-D0WD-V3 for an ESP32-WROOM-32E module plus moving six back-side parts to the front would get there. I checked JLCPCB's published *capability* table but never checked whether the actual *parts* were Economic-eligible. They aren't:

| Part | JLCPCB "PCBA Type" | Why |
|---|---|---|
| ESP32-D0WD-V3 (C967021) | **Standard Only** | QFN-48, 0.35 mm pitch — below the 0.4 mm Economic floor |
| ESP32-WROOM-32E-N4 (C701341) | **Standard Only** | Module handling / size |
| ESP32-WROOM-32 (C503587) | **Standard Only** | same |
| ES8388 (C365736) | Economic **and** Standard | QFN-28 at 0.4 mm clears the floor |

**Every Bluetooth-Classic-capable ESP32 option on JLCPCB is Standard Only.** Since REQ-MCU-01 (works with all phones → Bluetooth Classic → original ESP32 only, [confirmed](https://esp32.com/viewtopic.php?t=23059): S3/C3/C6/H2 are BLE-only and physically lack Classic radio hardware), **Economic PCBA is unreachable for this product, full stop.** Nothing in the layout or part selection changes that.

Two consequences:
1. The "move the six back-side parts to the front" task loses its cost justification. It's still mild good practice, but it is no longer a P0 and should not consume a redesign cycle on its own.
2. My v1.1 note that the ES8388's 0.4 mm pitch was a "borderline" Economic risk is resolved: it's fine, and it was never the constraint.

**What actually drives cost on Standard PCBA is different, and more actionable — see §5.1.** The module recommendation survives, but for entirely different and better-evidenced reasons (§4.1).

---

## 2. Headline findings

Severity: **S1** = will not work as intended / risks damaging a part. **S2** = latent or conditional failure. **S3** = quality, cost, or process.

| # | Sev | Finding | Affects | Fix effort |
|---|---|---|---|---|
| 1 | **S1** | ES8388 digital I/O rail (PVDD) is at 1.8 V while the ESP32 drives 3.3 V. Breaks the record path and exceeds the codec's absolute-maximum input rating. | REQ-AUD-02, REQ-MCU-03, REQ-AUD-01 | Small — delete a rail |
| 2 | **S1** | ES8388 `CE` (pin 26) is floating. Datasheet forbids this; it sets the I²C address. | REQ-AUD-01 | One resistor |
| 3 | **S1** | ESP32 `CAP1` (pin 48) is missing its **required** 10 nF capacitor. | REQ-MCU-01 | One capacitor |
| 4 | **S2** | SPI flash `IO2`/`IO3` are swapped. Boots in DIO, corrupts in QIO. | REQ-MCU-04 | Swap two nets |
| 5 | **S2** | No provision for automotive ground-loop isolation (alternator whine) — the classic failure mode for this exact product. | *No requirement exists* | Design work |
| 6 | **S2** | Crystal load caps (18 pF) look mis-derived for a 10 pF-CL crystal → likely negative frequency offset; Espressif requires ±10 ppm. | REQ-MCU-06 | Recalculate + bench |
| 7 | **S2** | Codec analog supply shares the ESP32's noisy 3.3 V rail; no AVDD↔HPVDD isolation resistor. Both contrary to the codec user guide. | REQ-AUD-01 | Small |
| 8 | **S3** | 1 µF and 10 µF each split across 3–4 redundant BOM lines, plus inconsistent value strings. Directly wastes feeder fees. | §2.3 constraint | Trivial |
| 9 | **S3** | Blue LED runs at ~0.3 mA — effectively invisible, especially in a car. | REQ-MCU-07 | Resistor value |
| 10 | **S2** | Mic bias network is wrong for a self-biased MEMS part — asymmetric external bias costs ~420 mV of DC imbalance and asymmetric headroom. Looks like an electret circuit misapplied. | REQ-AUD-04 | Delete 5 parts |
| 11 | **S3** | Microphone (ICS-40720) is **discontinued**, and serves only a deferred feature. | REQ-AUD-04 | Decide scope |
| 12 | **S3** | §1 of the requirements doc describes a TX mode the hardware cannot do. | REQ overview | Doc fix |

---

## 3. Subsystem reviews

### 3.1 Power subsystem

**As it stands:** USB-C (J2) → VBUS → NCP1117-3.3 (U7, SOT-223) → +3V3 rail → TLV71318 (U3, SOT-23-5) → +1V8 rail. CC1/CC2 have 5.1 kΩ pulldowns (R4/R5). USBLC6-2SC6 (U5) on the data lines. One power LED (D2).

**What's right — and worth stating explicitly:**
- **The 5.1 kΩ CC pulldowns are correct** for a USB-C sink. This is a commonly-botched detail; it's right here.
- **Choosing linear regulation over the originally-planned buck converter was the correct call, and for a better reason than "simplicity"** (which is how the requirements doc currently justifies it). This is a mixed-signal audio board. A switching regulator puts a 650 kHz noise source and its harmonics directly into the same ground and supply system as a 95 dB-SNR codec. The LDO's poor efficiency buys real audio performance. **Recommend re-recording this decision with the audio-noise rationale, not just the parts-count rationale.**
- Decoupling is generous and well distributed (15× 100 nF, plus bulk).

**Issues:**

**(a) Thermal margin in automotive ambient is tighter than the requirements doc implies.** *Estimated:* at 5 V in / 3.3 V out and ~200 mA average, U7 dissipates 1.7 V × 0.2 A = **0.34 W**. SOT-223 with moderate copper is roughly 60–100 °C/W. That's a 27–34 °C rise. Fine on a bench at 25 °C; in a car interior that can reach 60–70 °C ambient, junction lands near 100–110 °C against a 125 °C limit. Workable, but not the comfortable margin I claimed in v1.1.

Critically, this **inverts** the standing "need to find a smaller regulator" note (REQ-PWR-02): a smaller package is thermally *worse*. An AP2112K in SOT-23-5 (~200 °C/W) at the same dissipation would rise ~68 °C, putting the junction near 138 °C at automotive ambient — over the limit. **Recommendation: formally close "find a smaller regulator" as won't-fix, and record that SOT-223 is a deliberate thermal choice, so nobody "optimises" it later.**

**(b) The 1.8 V rail should be deleted entirely** — see finding S1-1 in §3.2. This removes U3, its caps, and a whole rail, which also satisfies the requirements doc's own §2.4 "minimise distinct regulated rails" guideline.

**(c) No dedicated codec supply.** The ES8388 user guide states plainly that one LDO should feed the codec because it is analog and noise-sensitive. Here AVDD/HPVDD hang directly on the same 3.3 V rail as the ESP32 — a load that draws ~250 mA current bursts every Bluetooth transmit slot. That current modulates the shared rail and lands in the codec's analog supply. The LyraT reference design the project cites has a separate `Codec_3V3` net for exactly this reason. **Recommend: repurpose U3's position as a dedicated 3.3 V codec LDO** (e.g. TLV70233 or AP2112K-3.3). Same part count as today, fixes both the level-shift problem and the supply-noise problem in one move. This is the single most elegant change available.

**(d) `J3` pin 1 is +3V3.** An external programmer that also supplies 3.3 V would fight U7's output — no series resistor or diode. Minor, but worth a series resistor or a documented "do not power from both" note.

**(e) No TVS on VBUS.** Acceptable *given* power comes via a USB car charger (which absorbs load dump). U5 offers ESD-level clamping only. This is correctly scoped — but it is an assumption that must not silently change; already tracked in requirements §6.1.

---

### 3.2 Audio subsystem

**As it stands:** ES8388 (U4) as I²S slave; ESP32 provides MCLK on GPIO0, SCLK GPIO27, LRCK GPIO25, DSDIN GPIO26; codec returns ASDOUT on GPIO35. I²C config on GPIO18/GPIO23. LOUT1/ROUT1 → 1 µF → 10 Ω → TRRS jack. Differential analog MEMS mic (MK1) → LIN1/RIN1. LOUT2/ROUT2 and LIN2/RIN2 broken out to test points only.

**What's right:**
- **I²S signal assignment is correct and, importantly, forced.** ESP32 can only emit MCLK on GPIO0/1/3; GPIO1 and GPIO3 are the UART, so GPIO0 is the only option. Using the BOOT strapping pin for MCLK looks alarming but is exactly what LyraT does and is safe here, because the codec's MCLK pin is a high-impedance input and cannot hold GPIO0 low at reset.
- **ASDOUT on GPIO35 respects that GPIO34–39 are input-only.** Correct direction.
- Reference pin decoupling (VREF, ADCVREF, VMID — each with a 10 µF + 100 nF pair) follows the datasheet application circuit properly.
- Differential mic input matches the user guide's explicit recommendation.

**Issues:**

**(a) S1 — The 1.8 V digital rail makes the codec electrically incompatible with the ESP32.** This is the most serious finding in the review.

*Confirmed from the ES8388 datasheet, page 6 pin table:*
> Pin 2 `DVDD` — Digital **core** supply. Pin 3 `PVDD` — Digital **IO** supply.

`PVDD` is the pad supply — it sets the logic levels for MCLK, SCLK, LRCK, DSDIN, ASDOUT, CCLK, CDATA. In this design **both DVDD and PVDD sit on +1V8**, while the ESP32 is a 3.3 V part. That breaks in both directions:

- **ESP32 → codec:** absolute maximum input voltage is `DVDD + 0.3 V` = **2.1 V** (datasheet §8.1). The ESP32 drives 3.3 V into MCLK, SCLK, LRCK and DSDIN — 1.2 V beyond absolute maximum, continuously, on four pins. That is an ESD-diode conduction and long-term reliability problem, not a marginal spec quibble.
- **Codec → ESP32:** the codec's `VOH` is referenced to PVDD ≈ 1.8 V. *Confirmed from the ESP32 datasheet DC characteristics:* `VIH(min)` = 0.75 × VDD = **2.475 V**, `VIL(max)` = 0.25 × VDD = **0.825 V**.

  **1.8 V lands in neither state — it sits in the forbidden zone between them.** This is worse than a clean failure: the ESP32's input is undefined, so behaviour depends on the individual die, temperature and supply, and can shift between bench and car. It may well appear to work during development and fail intermittently in the vehicle — the hardest possible class of bug to chase. `ASDOUT`, the ADC data line, is the casualty, so **REQ-AUD-02 (full-duplex) is not met despite being marked ✅, and the deferred HFP feature (REQ-MCU-03) has no working hardware path.**
- **I²C is a partial exception that masks the problem:** it's open-drain with 4.7 kΩ pull-ups to **3.3 V**, so the bus idles at 3.3 V (again over the codec's 2.1 V abs-max), but the codec only ever pulls *down*, and the ESP32 reads that fine. So **register writes may appear to work while the part is being over-stressed and the record path stays dead** — the worst kind of bug, because it looks like partial success.

*The fix is simple and strictly beneficial.* The datasheet's recommended operating range for the digital supply is **1.5 V – 3.6 V** (typ 1.8 V), and the user guide says *"Digital supply range (Core) DVDD 1.8V to 3.3V"* and *"(Buffer) PVDD 1.8V to 3.3V"*. **Running both at 3.3 V is fully in spec** — and it is what the project's own reference design does: the LyraT v4.3 schematic feeds PVDD/DVDD/AVDD/HPVDD from `Codec_3V3` and has no 1.8 V rail at all.

Cost of the change: codec power rises from ~16 mW to ~59 mW (datasheet §8.5) — about 13 mA more. Irrelevant on a car-powered device.

**Root cause worth noting:** the 1.8 V figure traces back to `calculations.xlsx` → ESP-32!B12 *"Digital VDD = 1.8V"*, which is the datasheet's **typical** value. It was adopted without checking it against the host MCU's logic levels. That's a requirements-process gap, not just a schematic slip — see §5.2.

**(b) S1 — `CE` (pin 26) is floating.** The netlist shows `I2C_AD` connecting **only** `U4.26` and test point `TP14`. No pull-up, no pull-down.

*Confirmed, ES8388 user guide §4:*
> "Don't connect CE pin to IO of MCU, CPU or DSP. CE pin should be pulled up to PVDD or pulled down to DGND."
> "The chip address for I2C is 0x20 if CE pin is pulled down to DGND. The chip address for I2C is 0x22 if CE pin is pulled up to PVDD."

A floating CMOS input gives an indeterminate I²C address and can float around the switching threshold (extra supply current, possible oscillation). Since the ESP-ADF ES8388 driver conventionally targets the 0x20 address, **recommend a pull-down to DGND**. One resistor — but without it the codec may simply not be addressable, i.e. no audio at all.

**(c) S2 — no AVDD↔HPVDD isolation.** User guide: *"One 10ohm resister is recommended between AVDD and HPVDD if AVDD and HPVDD share the same power supply."* Here U4.16 (HPVDD) and U4.17 (AVDD) both sit directly on +3V3 with nothing between them. The headphone driver's output-stage current then modulates the sensitive analog supply.

There is a plausible mix-up here worth flagging kindly: the design *does* contain four 10 Ω resistors (R7–R10) — but they are on the **audio outputs**, not between AVDD and HPVDD. The recommendation appears to have been applied to the wrong node.

**(d) S3 — audio coupling capacitor dielectric.** C23/C25 (1 µF, 0402) DC-block LOUT1/ROUT1. *This is the user's own open TODO from the "PCB checks" sheet, and it is a legitimate concern.* A 1 µF part in 0402 will be X5R/X7R Class II ceramic, which has a strong voltage coefficient and is piezoelectric — both produce measurable distortion on an audio-coupling duty where the cap sits at the VMID bias. Against REQ-AUD-01 ("high quality audio") this is the single most likely audible weak point in the analog chain.
Options, cheapest first: (i) move to a larger case size (0805/1206) in the same value to cut the voltage coefficient; (ii) use film; (iii) raise the value and accept the size. *Estimated* high-pass corner into a typical 10 kΩ car AUX input with 1 µF is ~16 Hz, so there is room to trade value for dielectric quality.

**(e) S2 — the microphone bias network is wrong for this part.** *Confirmed against the ICS-40720 datasheet (DS-000045 rev 1.4, Table 1).*

The ICS-40720's outputs are **already internally biased**: `Output DC Offset` = 0.66 V on OUTPUT+ and 0.70 V on OUTPUT−, with output impedances of 340 Ω and 410 Ω. It needs nothing but AC coupling.

The design instead adds an external bias network, **asymmetrically**: R21 (2.2 kΩ) pulls OUT+ *up* toward a filtered 3.3 V node (via R23/C43/C44), while R22 (2.2 kΩ) pulls OUT− *down* to GND. Working the resulting dividers against the mic's own output impedance:

| Node | Internal bias | With external network | Shift |
|---|---|---|---|
| OUT+ | 0.66 V | ≈ **1.01 V** | +0.35 V |
| OUT− | 0.70 V | ≈ **0.59 V** | −0.11 V |

That converts a ~40 mV DC difference between the two halves into roughly **420 mV of DC imbalance**. Because C41/C42 block DC, none of this reaches the codec — so it won't show up as an obvious fault. What it does do is **eat headroom asymmetrically**: the mic's maximum single-ended output is 0.40 Vrms (≈0.57 V peak) at its 124 dB SPL overload point, and OUT− now sits only 0.59 V above ground. The negative half-cycle runs out of room first, so the microphone clips asymmetrically at high SPL — earlier on one side than the other, which is exactly the kind of distortion that is hard to diagnose after the fact.

This network looks like a **leftover from an electret-capsule reference circuit**, where a bias resistor to VDD genuinely is required. A self-biased MEMS mic does not want one. **Fix: delete R21, R22, R23, C43 and C44 entirely** and let C41/C42 do the coupling — which also removes several BOM lines. (The 10 nF C39/C40 to ground are fine; with the mic's output impedance they form ~39–47 kHz low-pass corners, safely above the audio band, and act as useful RF filtering.)

**(f) S3 — mic supply is unfiltered.** `MK1.1 (VDD)` sits directly on +3V3 with no local RC or ferrite. The datasheet gives PSRR of only **−45 dB at 1 kHz**, on a rail shared with an ESP32 transmitting Bluetooth — so supply noise lands in the audio with little attenuation. Supply current is just 375 µA at 3.3 V, so an RC filter is nearly free (a 100 Ω / 10 µF pair costs ~40 mV of drop). Standard practice for analog MEMS mics, and it matters here.

*Both (e) and (f) are moot if the mic is dropped from v2 — see §4.8, which is the recommendation.*

**(f) Note — LOUT2/ROUT2 and LIN2/RIN2 go to test points only.** Intentional per the spec's "spare" entries. Fine, and cheap optionality.

---

### 3.3 Microcontroller & RF subsystem

**What's right:**
- **SDIO flash pin group matches Espressif's Slot 0 table exactly** (CMD→GPIO11, CLK→GPIO6, D0→GPIO7, D1→GPIO8) — apart from finding (b) below.
- **RF matching topology is a C-L-C Pi network** (C37 shunt → L1 series → C38 shunt), which is precisely what the Espressif guidelines call for: *"For the chip matching circuit... A CLC structure is preferred."* Topology correct; values unverified.
- **`R26`, the 4.7 kΩ pull-up on MTDI/GPIO12, is correctly marked DNP.** This deserves credit: GPIO12 is the VDD_SDIO strapping pin, and populating that resistor would select 1.8 V for a 3.3 V flash and brick the boot. The JTAG pull-ups on TMS (R24) and pull-down on TCK (R25) *are* populated, and neither is a strapping pin. Somebody thought carefully about this.
- The EN-pin RC (10 kΩ / 1 µF) and the UMH3N two-transistor auto-program circuit are the standard, correct arrangement; the direct-link alternatives R3/R14 are properly DNP'd so they don't fight it.

**Issues:**

**(a) S1 — `CAP1` (pin 48) is missing a required capacitor.** Both CAP1 and CAP2 are unconnected in the netlist. This resolves the user's own "Check CAP1, CAP2 pins on ESP32" TODO, and the answer differs per pin:

*Confirmed, ESP32 Hardware Design Guidelines §3.12:*
> "C5 (10nF) that connects to CAP1 should be of 10% tolerance and **is required for proper operation of ESP32**."
> "RC circuit between CAP1 and CAP2 pins **may be omitted** under certain conditions. This circuit is used when entering Deep-sleep mode... If particular application of ESP32 is not using Deep-sleep mode... then this circuit is not required."

So: **CAP1 needs a 10 nF ±10 % cap to GND — currently absent, and it is not optional.** CAP2's 3.3 nF ∥ 20 kΩ network is genuinely optional here, because a permanently car-powered adapter never deep-sleeps. **Verdict: add one capacitor; leave CAP2 unpopulated deliberately and note why.**

**(b) S2 — SPI flash IO2/IO3 are swapped.** *Confirmed* against the W25Q32JV datasheet 8-pin pinout (pin 3 = /WP (IO2), pin 7 = /HOLD (IO3)):

| ESP32 pin | Should reach | Actually reaches |
|---|---|---|
| GPIO9 (SD_DATA_2) | flash pin 3 (IO2) | flash **pin 7 (IO3)** |
| GPIO10 (SD_DATA_3) | flash pin 7 (IO3) | flash **pin 3 (IO2)** |

In **DIO/DOUT** mode only IO0/IO1 carry data and IO2/IO3 are held inactive-high, so the swap is harmless — the board will boot and appear healthy. In **QIO/QOUT** mode IO2/IO3 are live data lines, so bits 2 and 3 of every nibble transpose and flash reads return garbage. This is a dormant bug that detonates the day someone enables quad mode for speed. Fix is a two-net swap in the schematic — or it vanishes entirely with a module (§4.1).

**(c) S2 — crystal load capacitors look mis-derived.** Y1 is labelled *"Crystal 40 MHz 10pF"* with C35 = C36 = 18 pF. Using Espressif's own formula `CL = (C1×C2)/(C1+C2) + Cstray`, 18 pF/18 pF gives 9 pF + stray (~2–3 pF) ≈ **11.5–12 pF against a 10 pF spec**. Per the guidelines, excess load capacitance pulls the frequency *low*; they require the offset be trimmed to within ±10 ppm and warn that failing this causes Wi-Fi/Bluetooth connection failures. A calculated starting point for a 10 pF crystal would be nearer 15 pF/15 pF.
This is **needs bench check** — the correct value depends on real stray capacitance, and Espressif's stated method requires a spectrum analyser and their Certification/Test Tool to measure the actual offset. **A hobbyist realistically cannot close this out**, which is a strong argument for §4.1.

**(d) S3 — series element on XTAL_P is 0 Ω.** The guidelines say: *"Please add a series component (resistor or inductor) on the XTAL_P clock trace. Initially, it is suggested to use an inductor of 24nH to reduce the impact of high-frequency crystal harmonics on RF performance."* The placeholder (R13) is correctly there; the value is not the suggested starting point. Low severity, affects spurious emissions.

**(e) S3 — JTAG + GPIO12 is a documented ESP32 hazard.** Even with R26 DNP, an attached JTAG adapter driving TDI high across a reset selects 1.8 V VDD_SDIO and the 3.3 V flash fails to boot. The [documented fix](https://docs.espressif.com/projects/esptool/en/latest/esp32/espefuse/set-flash-voltage-cmd.html) is to burn the `XPD_SDIO_*` eFuses to force 3.3 V, after which GPIO12 is ignored as a strapping pin. **This belongs in a bring-up procedure, not discovered mid-debug.** (eFuses are one-way — worth stating.)

**(f) RF layout obligations remain open**, as already tracked in REQ-MCU-08: 50 Ω controlled impedance is *required* by the guidelines, and matching values need tuning against the real antenna and stackup. Unchanged from the previous review, but see §4.1 — this is the risk the module retires.

---

### 3.4 Programming & debug subsystem

Genuinely well provisioned, and I'd soften my earlier criticism of it. Three paths (on-board CH340K auto-program; off-board serial via J3; JTAG via J4 for ESP-PROG) cost a handful of passives, and for a board whose main chip has no USB peripheral and no SWD, redundancy in *getting code on and getting visibility out* is reasonable insurance rather than over-provisioning. The auto-program circuit is the standard correct topology.

Minor points: J3 and J4 are both on the back side (see §1 — no longer cost-relevant, but consider front placement for probe access); J3 pin 1 back-powering (§3.1(d)); and the eFuse item above.

---

### 3.5 Cross-cutting / system level

**(a) S2 — Automotive ground loop is unaddressed, and it is the classic failure mode for this exact product.** This is the biggest *systems* gap — not a component error, but a missing requirement.

The board bonds two grounds that sit at different potentials: chassis ground (via the cigarette-lighter USB charger) and the head unit's audio ground (via the AUX cable's sleeve, `J1.S`/`J1.G` → GND). Current circulating between them appears in the audio as engine-speed-dependent whine. There is a single GND net and no isolation anywhere.

Notably, **the project already knew about this and lost it**: `calculations.xlsx` → System design!B5 is literally *"Noise and interference"* linking a diyAudio thread titled *"Bluetooth Audio Receiver — Possible solution for All Kind of Noise"* — which is still the top search result for this problem. It never made it into the finalised spec or the schematic.

Practical on-board options, in order of effectiveness:
1. **1:1 audio isolation transformers** in series with LOUT1/ROUT1 — galvanically breaks the loop; the standard fix. Costs board area and money, and needs a decent part to avoid hurting LF response.
2. **Isolated DC-DC on VBUS** — breaks it on the power side. A 1 W isolated brick only gives ~200 mA at 5 V, which is *marginal-to-insufficient* for this design's ~200 mA average at 3.3 V (input current is higher). Would need a larger, pricier module.
3. Common-mode chokes + single-point ground join — partial mitigation only.

**Recommendation:** don't commit blind. Lay the outputs out so the two 10 Ω resistors (R7/R8) can be replaced by either 0 Ω links *or* transformer footprints, so v2 can be tested both ways on one board spin. Cheap insurance against a problem that otherwise only appears after the boards exist, in a car. **This needs to become a real requirement — proposed as REQ-AUD-05 in §5.2.**

**(b) S3 — the stated product concept exceeds the hardware.** The requirements Overview (§1, taken verbatim from `Specifications!A29`) describes a **TX mode**: *"When in TX mode, the device receives analog audio from the 3.5 mm jack, and outputs it over bluetooth."* The netlist shows `J1` connects only to `LOUT1`/`ROUT1` — **outputs**. There is no path from the jack into the codec's inputs (LIN2/RIN2 terminate at test point TP5). **v1 hardware is RX-only.** Either the Overview should be corrected to describe an RX-only sink, or a v2 input path (with switching, since the jack can't be both) needs designing. This is a scope statement that was never reconciled against the design — exactly what a requirements doc exists to catch.

**(c) S3 — TRRS jack where TRS is wanted.** J1 is a 4-pole `AudioJack4_Ground` with the second ring (`R2`) unconnected. For a stereo line-out to a car AUX, a 3-pole TRS jack is the correct, cheaper, unambiguous part. A TRS plug inserted into a TRRS socket will bridge R2 to sleeve, which is harmless here but sloppy. **Recommend switching to a 3-pole jack unless the 4th pole is reserved for a defined future purpose** (which would only make sense alongside (b)).

**(d) S3 — LED brightness.** *Estimated:* D1 (blue, Vf ≈ 3.0 V) with R12 = 1 kΩ on a 3.3 V rail gives ~0.3 mA — essentially invisible, and hopeless in daylight in a car. D3 (green) fares a little better at ~1.3 mA. **Recommend ~330 Ω** for a few mA. Trivial fix, but a status indicator you can't see is a defect against REQ-MCU-07.

**(e) Mechanical/environmental is entirely unspecified.** There is no enclosure, operating temperature range, connector strain relief, or vibration consideration anywhere in the requirements. For a device living in a car this is a real gap — the thermal analysis in §3.1(a) had to *assume* an ambient because none is specified. **Proposed as REQ-ENV-01 in §5.2.**

---

## 4. Part-by-part evaluation

Prices are LCSC single-unit, checked 2026-08-20; treat as indicative, and re-verify before ordering (requirements §2.3).

### 4.1 U1 — ESP32-D0WD-V3 (main MCU) — ✅ **KEEP. Module recommendation withdrawn.**

> **Superseded 2026-08-20.** The owner has stated that **designing the RF front end is an explicit learning objective** for this project — that is *why* bare silicon was chosen. That is a legitimate requirement and it outranks the cost/risk argument below, which is retained only for the record. It is now written into [requirements §2.2a](requirements-design.md) so this stops being re-litigated.
>
> **The plan is instead: exclude the ESP32 from JLCPCB assembly and hand-populate it on a reflow plate, putting the rest of the board on Economic PCBA.** Verified viable — the ESP32 is the only Standard-Only part ([requirements §2.1b](requirements-design.md)). Availability for single-unit purchase is good: **Mouser 8,829 @ $1.84**, LCSC 6,259 @ $1.58, DigiKey thinner (3 @ $1.84).
>
> **What this obliges, since a module would have absorbed them:**
> - Flash `IO2`/`IO3` swap (§3.3(b)) — **must** be fixed, no longer optional
> - Crystal load capacitance and frequency offset (§3.3(c)) — **must** be measured and trimmed
> - RF matching network sizing and 50 Ω controlled impedance (§3.3(f)) — the learning exercise itself
> - Instrumentation is now a project dependency, not a nicety — see [requirements §2.9](requirements-design.md)
>
> **Hand-assembly notes for a 0.35 mm-pitch QFN-48 with a thermal pad** — this is doable on a reflow plate but is genuinely one of the harder hand jobs, and two specifics matter more than technique:
> - **The exposed pad currently has open thermal vias** (footprint `..._EP3.7x3.7mm_ThermalVias`). On a hotplate, molten solder wicks down open vias, starving the pad — you get a weak thermal joint, a tilted part, and, critically, **a poor RF ground reference**, which will corrupt the very antenna measurements you're doing this to learn from. Fix by specifying via-in-pad plugged/capped at fab, or move the vias outside the pad.
> - **Use a segmented ("windowpane") stencil aperture on the EP**, roughly 50–70 % paste coverage. Full coverage floats the part on excess solder and lifts the perimeter pins.
> - Order the **framed laser-cut stencil** with the board; 0.35 mm pitch is not a hand-dispense job.
> - The part is **MSL 3** — if it has been open to humidity for a while, bake before reflow or risk popcorning.
> - You cannot visually inspect the joints. Plan electrical verification (continuity on accessible nets, then boot) as the acceptance test.

*Original assessment retained below for the record:*

| | |
|---|---|
| **Role** | Bluetooth Classic A2DP sink, I²S master, I²C master |
| **Suitability** | **Correct and effectively forced.** REQ-MCU-01 (all phones) → Bluetooth Classic → and only the original ESP32 line has Classic hardware at all. S3/C3/C6/H2 are BLE-only. This selection is well-founded and should not be revisited. |
| **Manufacturability** | Poor for this context. QFN-48, 0.35 mm pitch, MSL 3, Standard-Only. Drags in external flash, crystal + load caps, and a hand-tuned RF match. |
| **Cost / availability** | **$1.58**, 6,259 in stock (C967021) |
| **Verdict** | Right *silicon*, wrong *packaging choice* for a hobbyist build. |

**Recommended alternative 1 — ESP32-WROOM-32E-N4 (C701341), $2.61, 8,458 in stock.** Same ESP32-D0WD-V3 die, so Bluetooth Classic is retained and REQ-MCU-01 is unaffected. Integrates flash, crystal, load caps, RF matching and antenna, and carries FCC/CE/SRRC certification.

The unit price is higher, but that is the wrong comparison. On **Standard PCBA every unique part carries a ~$1.50 feeder-loading fee** regardless of build quantity, so BOM *lines* dominate at small volume. The module deletes six lines (flash, crystal, 18 pF, 2.2 nH, 3.3 pF, 0 Ω) plus the PCB antenna:

*Estimated,* using $1.58 ESP32 + ~$0.60 flash + ~$0.15 crystal + ~$0.08 passives ≈ $2.41/board across 7 BOM lines:

| Build qty | Bare chip | WROOM-32E-N4 | Module saving |
|---|---|---|---|
| 5 boards | $12.05 + $10.50 = **$22.55** | $13.05 + $1.50 = **$14.55** | **$8.00** |
| 10 boards | $24.10 + $10.50 = **$34.60** | $26.10 + $1.50 = **$27.60** | **$7.00** |
| 45 boards | ~$119 | ~$119 | break-even |

**Below roughly 45 boards the module is outright cheaper** — before counting the risks it retires. And it retires the expensive ones: the crystal-offset problem (§3.3(c)) that needs a spectrum analyser to close, the RF matching tuning that needs a VNA, the 50 Ω controlled-impedance obligation, and the flash IO2/IO3 swap (§3.3(b)) — all gone, because they're inside a pre-certified module.

Note honestly: it does **not** unlock Economic PCBA (§1), and it costs board area (25.5 × 18 mm).

**Recommended alternative 2 — ESP32-WROOM-32UE-N4 (C701344).** Identical but with a U.FL connector instead of the PCB antenna. Worth considering *only* if the enclosure turns out to be metal or the antenna keep-out can't be honoured; otherwise it adds cost and an assembly step. This also cleanly supersedes the old "RF switch for external antenna" backlog idea (requirements §7) — buying the variant is simpler than switching between two antennas.

---

### 4.2 U4 — ES8388 (audio codec) — **keep the part, fix the circuit**

| | |
|---|---|
| **Role** | Stereo ADC + DAC, headphone/line drivers, mic preamp |
| **Suitability** | **Good.** Stereo in *and* out in one cheap part; directly supported by ESP-ADF; used by the LyraT reference. Datasheet 96 dB DAC dynamic range / −83 dB THD+N comfortably exceeds anything a car AUX input will resolve. |
| **Manufacturability** | Fine. QFN-28 at 0.4 mm clears Economic; **"Economic and Standard"** on JLCPCB (so it is *not* the tier constraint — correcting my v1.1 note). |
| **Cost / availability** | **$0.51** (C365736) — cheaper than DAC-only alternatives |
| **Verdict** | **Keep.** But three circuit defects must be fixed: PVDD/DVDD to 3.3 V (§3.2(a)), CE pulled down (§3.2(b)), AVDD↔HPVDD 10 Ω (§3.2(c)). |

**Alternative 1 — PCM5102A (C107671), $0.84.** DAC-only, hardware-configured (no I²C at all), 112 dB dynamic range — genuinely better playback specs and a much simpler bring-up, since an entire class of register-configuration bugs disappears. **But it has no ADC**, so it permanently forecloses HFP (REQ-MCU-03) and the mic. Worth serious consideration *if* you decide the handsfree feature is never happening — it would be cheaper overall (deletes the mic and its network too) and lower-risk. This is a scope decision, not a parts decision.

**Alternative 2 — TLV320AIC3204 (C24109), $0.67.** Stereo codec with on-chip DSP (programmable biquads), integrated LDOs and a PLL. Technically superior and could absorb the "controllable equaliser" idea from the requirements backlog into hardware. Costs more complexity to bring up and has far less ESP32-specific example code than the ES8388. **Not recommended now** — it trades the project's best asset (a directly-applicable reference design) for capability that isn't required.

---

### 4.3 U6 — W25Q32JVZP (SPI flash) — **likely deleted**

| | |
|---|---|
| **Role** | 4 MB program storage for the ESP32 (REQ-MCU-04) |
| **Suitability** | Correct part, correct 3.3 V variant (`JV` = 2.7–3.6 V; the 1.8 V `JW` would have been wrong). 4 MB is ample for an A2DP sink. |
| **Manufacturability** | Easy — WSON-8, 1.27 mm pitch. |
| **Issue** | **IO2/IO3 swapped** (§3.3(b)). |
| **Verdict** | **Disappears entirely if U1 → WROOM module**, which also erases the swap bug. If the bare chip is kept, swap the two nets. |

**Alternative if kept:** GD25Q32E (GigaDevice) — pin-compatible, usually cheaper and often better stocked. Verify JLCPCB stock/tier before committing.

---

### 4.4 U2 — CH340K (USB-UART bridge) — **keep**

| | |
|---|---|
| **Role** | USB↔UART + DTR/RTS auto-program (REQ-MCU-09, REQ-DEV-01) |
| **Suitability** | Good, and **necessary** — the original ESP32 has no USB peripheral, and the Bluetooth Classic requirement blocks the S3/C3 parts that do. Well-trodden with esptool. |
| **Manufacturability** | Easy — SSOP-10, 1 mm pitch. |
| **Cost** | ~$0.30–0.40, very well stocked (Chinese-domestic part, strong LCSC availability) |
| **Verdict** | **Keep.** Cheapest sensible option. |

**Alternative 1 — CP2102N.** Better driver reputation on macOS/Linux and a more established brand; roughly 3–5× the price and no functional gain here. The original spec considered and rejected CP2102 — that call still holds.
**Alternative 2 — CH343P.** Higher baud ceiling, similar price/availability. Only worth it if flashing speed becomes annoying.

*Caveat consistent with requirements §2.8:* CH340 documentation is thinner and largely Chinese-language, though drivers are widely distributed and the part is fully public. It passes the accessibility rule, but it is the weakest part in the BOM on that axis.

---

### 4.5 U7 — NCP1117-3.3 (3.3 V LDO) — **keep, and stop trying to shrink it**

| | |
|---|---|
| **Role** | Main 3.3 V rail (REQ-PWR-01/02/03/04) |
| **Suitability** | Good. 1 A rating against a ~200–300 mA load; dropout ~1.2 V max is satisfied from 5 V VBUS even at USB's 4.75 V minimum. |
| **Manufacturability** | Easy, and **SOT-223 is the right package thermally** (§3.1(a)). |
| **Cost** | ~$0.15–0.25, extremely common |
| **Verdict** | **Keep. Close the "find a smaller regulator" note as won't-fix**, and record the thermal reasoning so it isn't reopened. |

**Alternative 1 — AMS1117-3.3.** Cheaper and ubiquitous, but worse dropout and quiescent current, and quality varies by vendor. A downgrade for negligible saving.
**Alternative 2 — a synchronous buck (e.g. TPS562201, already in the repo's datasheet folder).** Would solve the thermal question outright via efficiency. **Recommend against** for this product: it reintroduces switching noise into a mixed-signal audio board, which is precisely what the v1 architecture correctly moved away from. Revisit only if a future variant takes 12 V directly, where a linear regulator's dissipation would become untenable.

---

### 4.6 U3 — TLV71318 (1.8 V LDO) — **repurpose or delete**

| | |
|---|---|
| **Role** | 1.8 V for codec DVDD/PVDD (REQ-PWR-05) |
| **Suitability** | The part is fine; **the rail should not exist** (§3.2(a)). |
| **Verdict** | **Delete the 1.8 V rail.** Best option: keep the footprint and fit a **3.3 V** LDO instead, giving the codec its own quiet supply as the user guide recommends (§3.1(c)) — same part count, two problems solved. |

**Recommended replacement — TLV70233 (SOT-23-5, 3.3 V, 300 mA)** or **AP2112K-3.3 (600 mA)**. Both cheap and well stocked. Confirm the codec's ~60 mW peak draw plus mic leaves ample headroom — it does, by a wide margin. **REQ-PWR-05 needs rewriting accordingly (§5.2).**

---

### 4.7 U5 — USBLC6-2SC6 (USB ESD) — **keep**

Correct in-line wiring (D− through pins 6→1, D+ through 4→3), low capacitance suited to USB data, and the industry-default choice. ~$0.15, universally stocked, tiny SOT-23-6. **No change.** Alternatives (PRTR5V0U2X, SRV05-4) offer no advantage; SRV05-4 has higher capacitance and is a mild downgrade for data lines.

---

### 4.8 MK1 — ICS-40720 (analog MEMS microphone) — **must change or drop**

| | |
|---|---|
| **Role** | Mic input for deferred HFP (REQ-AUD-04, supporting REQ-MCU-03) |
| **Suitability** | The *part* is a good match — differential analog output is exactly what the ES8388 user guide recommends, and 70 dB SNR is strong. The *circuit around it* is not: it applies an electret-style asymmetric bias network to a self-biased MEMS output (§3.2(e)), and leaves VDD unfiltered against a −45 dB PSRR (§3.2(f)). |
| **Availability** | **Discontinued by TDK InvenSense.** Still listed at JLCPCB (C3171779) and some distributors, but it is end-of-life. |
| **Verdict** | **Do not carry a discontinued part forward for a feature that isn't implemented — especially not with a bias network that needs rework anyway.** |

Two honest options:
1. **Drop the mic from v2.** It serves only HFP (REQ-MCU-03, explicitly *Future*); its signal path is broken anyway until §3.2(a) is fixed; its bias network is wrong and needs rework regardless (§3.2(e)); and the part is EOL. Removing it deletes MK1, R21, R22, R23 and four capacitors — several BOM lines, and one of the cheapest simplifications available. **This is my recommendation**, unless HFP is imminent.
2. **If keeping it,** select a current differential-analog MEMS mic and re-verify against the ES8388 differential input, checking JLCPCB stock and tier first. Do this at the point HFP is actually being built, not speculatively.

Either way, **REQ-AUD-04's status should not remain ✅** while it depends on an EOL part and a broken interface.

---

### 4.9 Y1 / ANT1 / L1 — crystal and RF front end — **superseded by the module**

Topology is right (C-L-C Pi per Espressif; series element present on XTAL_P). The problems are all *values that can only be closed with instruments a hobbyist doesn't have*: crystal load capacitance (§3.3(c)), matching network values, and 50 Ω trace impedance. **If U1 becomes a WROOM module, all of this is deleted and pre-certified.** That is the strongest single argument in this review.

---

### 4.10 J1 / J2 / Q1 — connectors and glue

- **J1 audio jack** — switch to a 3-pole TRS (§3.5(c)) unless the 4th pole gains a defined purpose.
- **J2 USB-C (GCT USB4110)** — correct sink implementation with 5.1 kΩ CC pulldowns. Verify the footprint against the datasheet (it's on the user's own PCB-checks TODO list). Through-hole-anchored USB-C receptacles are strongly preferred for mechanical durability in a car; confirm this variant has them.
- **Q1 UMH3N** — dual digital transistor with integrated bias resistors; standard for the auto-program circuit and saves discrete parts. Keep. Verify JLCPCB stock, as specific digital-transistor part numbers move around.

---

## 5. Requirements impact

### 5.1 Corrected cost model (replaces requirements §2.1's framing)

The previous review optimised for the wrong variable. On Standard PCBA — which this product cannot escape (§1) — cost at hobbyist volume is dominated by **unique BOM lines at ~$1.50 each**, not component pitch.

Current design: **35 billable BOM lines ≈ $52.50** in feeder fees before a single component is paid for.

Immediate, zero-risk reductions available:

| Action | Lines saved | *Est.* saving |
|---|---|---|
| Consolidate **1 µF** — currently three separate lines (0402 ×9, 0603 ×3, 1206 ×1) | 2 | $3.00 |
| Consolidate **10 µF** — currently four lines across 0402/0603/1206, *and* inconsistent value strings ("10u" vs "10uF") that generate duplicate BOM entries | 3 | $4.50 |
| Delete the 1.8 V rail (§3.2(a)) | 1 | $1.50 |
| Move U1 to a WROOM module (§4.1) | 6 | $9.00 |
| Drop the discontinued mic (§4.8) | ~2 | $3.00 |
| **Total** | **~14** | **~$21** |

That takes the design from 35 to ~21 lines — a *40 % reduction in the dominant small-batch cost driver*, while simultaneously removing a discontinued part, a broken rail, and the entire RF/crystal risk class.

**The "10u" vs "10uF" inconsistency is worth fixing regardless of cost** — identical values written differently become separate BOM lines and separate purchase decisions. This should be a standing rule; proposed for requirements §2.

### 5.2 Proposed requirement changes

| Action | Requirement | Change |
|---|---|---|
| **Correct** | REQ-PWR-05 | "Audio codec DVDD = 1.8 V" is **wrong for this system** and must become: *codec digital supply = 3.3 V, matched to the ESP32's logic levels; preferably from a dedicated LDO for analog noise isolation.* |
| **Correct** | REQ-AUD-02 | Currently ✅. Should be ❌ until §3.2(a) is fixed — full-duplex does not work; ASDOUT cannot be read. |
| **Correct** | REQ-AUD-04 | Currently ✅. Should be ⚠️ — depends on a discontinued part and a non-functional interface. |
| **Correct** | Overview §1 | Remove TX mode, or raise it as explicit future scope. v1 hardware is RX-only (§3.5(b)). |
| **Correct** | requirements §2.1 + §5 | Replace the Economic-PCBA goal with the BOM-line cost model (§1, §5.1). |
| **Correct** | requirements §5 P2-6 | **My earlier I²C pull-up call was wrong.** I recommended changing the spec's "1 kΩ" to match the schematic's 4.7 kΩ, reasoning 4.7 kΩ is more standard. In fact the ES8388 user guide explicitly states *"Two 1K pull up resisters are recommended to I2C bus"* — the spec was right and traceable to the vendor document; the schematic deviates. 4.7 kΩ will very likely work fine in practice, but **the spec should not have been changed to match the schematic.** Also unimplemented: the guide's recommended R-C low-pass on CCLK. |
| **Add** | **REQ-AUD-05** (new) | *Audio output shall not exhibit audible ground-loop noise (alternator whine) when the device is powered from the vehicle's electrical system and connected to the head unit's AUX input.* Verification: listen across the engine's RPM range. Provision transformer-or-link footprints on LOUT1/ROUT1 to allow both options on one spin (§3.5(a)). |
| **Add** | **REQ-ENV-01** (new) | *Define operating ambient temperature range* (suggest −20 °C to +70 °C for a car interior), enclosure, and connector retention. Currently entirely unspecified, which forced §3.1(a)'s thermal analysis to assume an ambient. |
| **Add** | **REQ-AUD-06** (new) | *Give REQ-AUD-01 "high quality audio" a measurable criterion* — the requirements doc already flags this gap (§2.5). Suggest: no audible hiss at max volume with no signal, and no audible distortion at full scale into a 10 kΩ AUX load. Informal but testable, and appropriate for a hobbyist build. |
| **Add** | Bring-up procedure | Document the `XPD_SDIO_*` eFuse step before JTAG debugging (§3.3(e)), noting eFuses are irreversible. |

---

## 6. Prioritised action list

**Fix before any v2 layout — these are correctness, not optimisation:**
1. Move ES8388 DVDD/PVDD to 3.3 V; delete the 1.8 V rail. Ideally refit U3's footprint as a dedicated 3.3 V codec LDO. *(§3.2(a), §3.1(c))*
2. Pull ES8388 `CE` down to DGND (address 0x20). *(§3.2(b))*
3. Add the required 10 nF ±10 % on ESP32 `CAP1`; deliberately leave CAP2 unpopulated and note why. *(§3.3(a))*
4. Decide U1: **WROOM-32E-N4 module recommended** *(§4.1)*. If the bare chip is kept, swap flash IO2/IO3 *(§3.3(b))* and budget instrument time for crystal and RF tuning *(§3.3(c))*.

**Design decisions needed from you (these change scope, so I haven't assumed):**
5. Ground-loop strategy — provision transformer footprints, or accept the risk? *(§3.5(a))*
6. Is HFP/mic ever happening? Drives whether the mic is dropped and whether ES8388 stays over a simpler DAC. *(§4.8, §4.2)*
7. Is TX mode in or out of the product? *(§3.5(b))*
8. Confirm build quantity and cost target — the whole cost model in §5.1 depends on it, and requirements §2.7 is still a placeholder.

**Cheap wins, do them alongside the above:**
9. Add AVDD↔HPVDD 10 Ω. *(§3.2(c))*
10. Re-spec audio coupling caps for dielectric. *(§3.2(d))*
11. LED resistors 1 kΩ → ~330 Ω. *(§3.5(d))*
12. Consolidate 1 µF / 10 µF BOM lines and normalise value strings. *(§5.1)*
13. 3-pole TRS jack instead of TRRS. *(§3.5(c))*
14. Add a schematic warning note at R26 explaining why it must stay DNP. *(§3.3)*
15. If the mic is kept: delete the bogus bias network (R21/R22/R23/C43/C44) and add an RC filter on mic VDD. If it's dropped (recommended), both disappear. *(§3.2(e)(f), §4.8)*

**Still open from previous review:** fix all DRC errors; verify USB-C footprint; verify flash SPI power pin. *(requirements §6.4)*

---

## 7. Overall assessment

The **architecture is sound and the hard system-level calls were made correctly**: Bluetooth Classic over BLE Audio (forced by the compatibility requirement, and correctly identified early); a dedicated codec over the ESP32's internal DAC; linear regulation over switching on a mixed-signal board; and a reference design (LyraT) chosen to lean on. The I²S pin assignment, the SDIO flash group, the USB-C sink implementation, the auto-program circuit, and the awareness of the GPIO12 strapping trap are all evidence of careful work.

What went wrong is concentrated in one recognisable pattern: **datasheet "typical" values and generic conventions were adopted without checking them against this specific system.** The 1.8 V digital rail is the datasheet's typical value — correct for a 1.8 V host, wrong for a 3.3 V ESP32. The JTAG pull-up convention is right in general and wrong on a strapping pin (caught, and correctly DNP'd — the process worked there). The 10 Ω resistor the codec guide asks for went onto the outputs rather than between AVDD and HPVDD. `CE` and `CAP1` were treated as no-connects because nothing forced attention to them.

The single most valuable process change is the one already written into the requirements document at §2.3 but not yet applied to *electrical* review: **verify against the primary document, at the pin level, before freezing.** Three of the four S1 findings here were sitting in datasheets the repo already contains — and two of them were already on the user's own TODO list ("Check CAP1, CAP2 pins", "Check dielectrics for audio in-line caps"). The instincts were right; the follow-through stalled.

Fixed as listed, this is a solid, manufacturable design.

---

## 8. Revision history

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-20 | Initial system design review. Netlist-level audit against primary datasheets; withdrew the previous review's Economic-PCBA cost argument and replaced it with a BOM-line cost model; identified three S1 defects and the missing ground-loop requirement. |
