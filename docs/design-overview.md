# Bluetooth Audio Adaptor — Design Overview

**Rev B (in design)** · Updated 2026-08-28 · Jason
Describes the **target design**. Deltas from as-built Rev A are listed in §10.

> Living document. Every confirmed design change lands here. Planning, open questions and review
> findings live in [`requirements-design.md`](requirements-design.md) and
> [`design-review-v1.md`](design-review-v1.md) — not here.

---

## 1. Function

Bluetooth audio adaptor for a car AUX input. Powered from USB-C or an internal Li-ion cell.

| Mode | Path | Status |
|---|---|---|
| **RX** (primary) | Phone → Bluetooth A2DP → codec DAC → 3.5 mm out | Rev A hardware complete |
| **TX** | 3.5 mm in → codec ADC → Bluetooth → headphones/speaker | Rev B addition |
| **HFP** handsfree | On-board mic → codec ADC → BT; BT → DAC → jack | Rev B addition |

**Key constraint:** must work with all phones, not just recent ones → **Bluetooth Classic (A2DP/HFP),
not BLE Audio**. This single requirement determines the MCU (§5).

**Out of scope:** amplified speaker output, multipoint pairing, app control.

---

## 2. Architecture

**Power tree**

```
                      ┌──────────────────┐
                      │  Li-ion cell     │
                      │  + 10 k NTC      │
                      └────────▲─────────┘
                               │ BAT (charge / discharge)
  USB-C ── VBUS 5 V ──► ┌──────┴───────┐
                        │   BQ24074    │  power path · DPPM
                        │   charger    │  SYS clamped ≤ 4.4 V
                        └──────┬───────┘
                               │ SYS  3.0 – 4.4 V
                     ┌─────────┴─────────┐
                     ▼                   ▼
              ┌─────────────┐     ┌─────────────┐
              │   LDO A     │     │   LDO B     │
              │  AP7361C    │     │  LP5907     │
              │  SOT-89 1 A │     │  low noise  │
              └──────┬──────┘     └──────┬──────┘
                     │ 3V3_A             │ 3V3_B
                     │                   │
         ESP32 · flash · CH340K       ES8388 · MEMS mic
              · LEDs  (280 mA pk)          (20 mA)
```

**Signal chain**

```
   40 MHz XTAL ──┐        ┌── W25Q32JV 4 MB flash
                 │        │
   PCB antenna   │        │ SPI          USB-C ── USBLC6 ── CH340K
   + C-L-C match─┤        │                                    │
                 ▼        ▼                                    │ UART
              ┌──────────────────────────┐                     │ + DTR/RTS
              │     ESP32-D0WD-V3        │◄────────────────────┘
              │  BT Classic + BLE        │
              └──────┬────────────┬──────┘
                 I2C │        I2S │  (MCLK/SCLK/LRCK/DSDIN/ASDOUT)
                     ▼            ▼
              ┌──────────────────────────┐
              │   ES8388 stereo codec    │
              └───▲──────────┬───────▲───┘
        LIN1/RIN1 │  LOUT1/  │       │ LIN2/RIN2
                  │  ROUT1   ▼       │
                  │      ┌───────────┴───────┐
                  │      │  TS5A23159 SPDT   │  TX / RX select
                  │      └─────────┬─────────┘
                  │                │ 1 µF AC coupling
                  │                ▼
          on-board MEMS mic   3.5 mm TRS jack
          (differential pair)
```

**Rails**

| Rail | Source | Loads | Why separate |
|---|---|---|---|
| SYS 3.0–4.4 V | BQ24074 | Both LDOs | Power path: USB when present, battery when not |
| 3V3_A | LDO A | ESP32, flash, CH340K, LEDs | Carries RF current bursts |
| 3V3_B | LDO B (LP5907) | ES8388, mic | Isolates a 96 dB codec from those bursts |

---

## 3. Power subsystem

Linear regulation throughout. A switching converter was rejected: this is a mixed-signal audio
board and the efficiency gain does not pay for the noise.

| Part | Function | Key spec |
|---|---|---|
| **BQ24074RGTR** (C54313) | Power-path charger | 1.5 A, SYS clamped ≤4.4 V, DPPM, NTC input, 10.5 V OVP |
| **AP7361C-33Y5-13** (C460397) | LDO A — digital/RF | SOT-89-5, 1 A, ultra-low dropout |
| **LP5907MFX-3.3** (C80670) | LDO B — codec analog | 6.5 µV<sub>RMS</sub>, high PSRR, no bypass cap needed |
| **USBLC6-2SC6** | USB ESD | In-line on D+/D− |
| Li-ion cell + 10 k NTC | Energy | Removable. NTC bonded to cell, not PCB |

**Charger behaviour.** System load takes priority over charge current (DPPM). SYS follows USB when
present, battery when not. The ≤4.4 V clamp is what makes LDO A's thermals work (§7).

**Safety.** Charging is inhibited outside the cell's temperature window in hardware via the NTC on
`TS` — not in firmware. Cell is removable; device is not stored in the vehicle.

**Why not LFP:** 3.2 V nominal sits below the 3.3 V rail for most of its discharge, forcing a boost
converter in front of the codec.

---

## 4. Audio subsystem

**ES8388** stereo codec — 24-bit, 96 dB DAC dynamic range, −83 dB THD+N. Chosen over the ESP32's
internal DAC for quality, and over a DAC-only part because HFP needs an ADC.

| Signal | Connection |
|---|---|
| Control | I²C, address **0x20** (`CE` pulled to DGND) |
| Audio | I²S, codec as **slave**; full duplex for HFP |
| Clocks | MCLK, SCLK, LRCK from ESP32 |
| Output | LOUT1/ROUT1 → 1 µF → 10 Ω → analog switch → jack |
| Input (TX) | Jack → switch → LIN2/RIN2 |
| Input (mic) | Differential LIN1/RIN1 |

**All four codec rails run at 3.3 V.** DVDD/PVDD at 1.8 V would put the codec's I/O in a different
logic domain from the 3.3 V ESP32 — see §7.

| Part | Function | Key spec |
|---|---|---|
| **ES8388** | Stereo codec | QFN-28, 0.4 mm; AVDD/HPVDD/DVDD/PVDD all 3V3 |
| **SPH8878LR5H-1** (C3171733) | MEMS microphone | LGA-6, differential **or** single-ended, MSL 1 |
| **TS5A23159DGSR** (C42751) | TX/RX path switch | Dual SPDT, 1 Ω R<sub>on</sub>, break-before-make |
| 3.5 mm TRS jack | Audio I/O | 3-pole |

**Output coupling.** 1 µF blocks the VMID bias. Into a ~10 kΩ AUX load that is a ~16 Hz corner.
Use a case size large enough that Class-II dielectric distortion stays below the codec's own THD.

**Ground loop.** Chassis ground (USB charger) and head-unit audio ground form a loop → alternator
whine. Mitigations: run on battery with USB unplugged (free), or fit 1:1 isolation transformers in
place of R7/R8. Both provisioned; footprints accept either.

---

## 5. Microcontroller & RF

**ESP32-D0WD-V3.** QFN-48, 0.35 mm pitch, dual-core Xtensa LX6.

**Selected for firmware capability, not silicon features:** it is the only Espressif part whose
radio hardware supports **Bluetooth Classic**, and the only one whose SDK provides an **A2DP sink**
and **HFP**. ESP32-S3/C3/C6/H2 and the entire Nordic nRF range are BLE-only. This choice follows
directly from §1's compatibility requirement.

| Part | Function | Key spec |
|---|---|---|
| **ESP32-D0WD-V3** | MCU + radio | BT Classic + BLE + Wi-Fi; needs external flash |
| **W25Q32JV** | Program store | 4 MB, 3.3 V (`JV` not `JW`), on VDD_SDIO |
| 40 MHz crystal | Reference | ±10 ppm required; load caps per §7 |
| PCB inverted-F antenna + C-L-C match | 2.4 GHz | 50 Ω controlled impedance, 4-layer |

**RF front end is a deliberate learning exercise.** A pre-certified module would remove the matching
network, crystal trim and impedance routing — that is precisely the work being kept. Requires a
NanoVNA (antenna S11) and a frequency-offset measurement to close.

**Stackup:** 4-layer. Signal / GND / PWR / Signal, with a solid ground plane under the RF section.

---

## 6. Programming & debug

No USB peripheral on this ESP32 variant, and no SWD (Xtensa, not ARM).

| Path | Parts | Use |
|---|---|---|
| USB auto-program | CH340K + UMH3N dual transistor on DTR/RTS | Day-to-day flashing |
| Off-board serial | J3 header (DNP) | Fallback |
| JTAG | J4 2×5 header (DNP), ESP-PROG | Debugging |

Headers are DNP — fit before a debug session. 13 test points cover I²C, mic, audio out, boot, GPIO
and rails.

---

## 7. Key calculations

**Power budget**

| Load | Rail | Current |
|---|---|---|
| ESP32, BT Classic streaming (avg) | A | 130 mA |
| ESP32 transmit peak | A | 250 mA |
| SPI flash | A | 5 mA |
| CH340K (USB attached only) | A | 10 mA |
| 2× LED @ 330 Ω | A | 8 mA |
| **Rail A** | | **155 mA avg · 280 mA peak** |
| ES8388 @ 3.3 V, playback + record | B | 18 mA |
| MEMS mic | B | 0.4 mA |
| **Rail B** | | **~20 mA** |

**LDO A thermal.** Bluetooth bursts last 1–2 ms; package time constant is seconds, so the junction
integrates to the average, not the peak.

```
P_avg = (4.4 − 3.3) × 0.155 = 0.17 W
SOT-89, θJA ≈ 100 °C/W  →  ΔT = 17 °C  →  Tj ≈ 87 °C at 70 °C ambient      ✓
SOT-23-5, θJA ≈ 200 °C/W →  ΔT = 34 °C  →  Tj ≈ 104 °C                     ✓ but tight
```

**LDO A dropout → usable battery.** Dropout, not current, is the binding spec.

```
Cutoff = 3.3 V + V_dropout(280 mA)

  150 mV → 3.45 V → ~87 % of cell
  250 mV → 3.55 V → ~83 %
  400 mV → 3.70 V → ~75 %
  1.2 V  → 4.50 V → will not run on battery       (NCP1117, Rev A — removed)
```

**Runtime** (LDO path, ~83 % usable): 1000 mAh ≈ 4.8 h · 2000 mAh ≈ 9.7 h · 3000 mAh ≈ 14.5 h.

**Crystal load capacitance.**

```
CL = (C1 × C2)/(C1 + C2) + C_stray        C_stray ≈ 2–5 pF

Rev A: 18 pF ‖ 18 pF → 9 + 3 ≈ 12 pF against a 10 pF crystal → over-loaded, frequency low
Rev B: ≈ 15 pF ‖ 15 pF → 7.5 + 3 ≈ 10.5 pF, then trim on measured offset (±10 ppm required)
```

**Logic-level compatibility (why all codec rails are 3.3 V).**

```
ESP32   VIH(min) = 0.75 × 3.3 = 2.475 V     VIL(max) = 0.825 V
Codec at PVDD 1.8 V: VOH ≈ 1.8 V  →  lands between VIL and VIH = undefined
Codec abs-max input = DVDD + 0.3 V = 2.1 V  →  3.3 V drive exceeds it
```

**Audio output coupling.** `f = 1/(2π · 10 kΩ · 1 µF) ≈ 16 Hz`.

---

## 8. Conceptual circuits

**Microphone — differential, no external bias.** MEMS outputs are internally biased (0.66/0.70 V,
340/410 Ω). An electret-style bias resistor fights the internal amplifier and costs headroom.

```
   3V3_B ──[100 Ω]──┬────────── MIC VDD          RC filter: mic PSRR is only −45 dB
                    │
                 [1 µF]
                    │
                   GND

   OUT+ ──┬──╫ 100 nF ──► ES8388 LIN1     Route OUT+/OUT− as a matched parallel
          │                                pair — common-mode rejection depends on
       [10 nF]                             both picking up identical noise.
          │
         GND                               10 nF + 340 Ω ≈ 47 kHz — RF shunt only,
   OUT− ──┬──╫ 100 nF ──► ES8388 RIN1      above the audio band.
          │
       [10 nF]
          │
         GND
```

**TX/RX switch — placement is critical.**

```
              ┌──────────────┐
  LOUT1 ──────┤ NO           │
              │   TS5A23159  ├── COM ──╫ 1 µF ──► jack tip
  LIN2  ──────┤ NC           │
              └──────┬───────┘
                     │ IN ── ESP32 GPIO
```

Switch sits on the **codec side** of the coupling capacitor. Both throws are at VMID (~1.65 V),
inside the switch's 0–3.3 V supply rails. On the jack side the signal is centred at 0 V and every
negative half-cycle would clip.

**RF match — C-L-C Pi, per Espressif.**

```
  ESP32 LNA_IN ──┬──[ L series ]──┬────── PCB antenna
                 │                │
              [C shunt]        [C shunt]        Values tuned on measured S11.
                 │                │             50 Ω controlled-impedance trace.
                GND              GND
```

---

## 9. Firmware dependencies

Hardware choices that constrain firmware, or vice versa.

| Item | Note |
|---|---|
| **Bluetooth Classic** | Only the original ESP32 has Classic radio hardware. A2DP sink + HFP come from ESP-IDF/ESP-ADF. Drives the entire MCU selection. |
| **Pairing persistence** | Bluedroid writes bonding keys to **NVS in flash** automatically. Survives power-off with no battery. Requires an initialised NVS partition. |
| **MCLK pin** | ESP32 can emit MCLK only on GPIO0/1/3. GPIO1/3 are the UART, so **GPIO0** — which is also the BOOT strapping pin. Safe: the codec's MCLK input is high-Z at reset. |
| **ADC** | Use **ADC1 only** (battery sense). ADC2 is unusable while the radio is active. GPIO32–39 free. |
| **Flash mode** | Configure **DIO**. QIO requires IO2/IO3 correct — fixed in Rev B, but DIO is the safe default. |
| **JTAG + GPIO12** | MTDI is the VDD_SDIO strapping pin. A debugger driving TDI high across reset selects 1.8 V and the 3.3 V flash fails. Fix: burn `XPD_SDIO_*` eFuses to force 3.3 V. **Irreversible.** |
| **Codec I²C address** | 0x20 (`CE` low). ESP-ADF's ES8388 driver default. |
| **I²S full duplex** | Required for HFP. Configure both TX and RX channels. |
| **TX/RX switch** | One GPIO selects the audio path. Firmware must track mode. |
| **Deep sleep** | If used for battery standby, populate the CAP2 RC network. |

---

## 10. Deltas from Rev A (as built)

| # | Change | Reason |
|---|---|---|
| 1 | Codec rails 1.8 V → 3.3 V; delete 1.8 V LDO, add dedicated codec LDO | Logic-level incompatibility + supply noise |
| 2 | `CE` pulled to DGND | Was floating — indeterminate I²C address |
| 3 | Add 10 nF on ESP32 `CAP1` | Required by datasheet; was absent |
| 4 | Swap flash IO2/IO3 | Crossed; corrupts QIO reads |
| 5 | Delete mic bias network (R21/R22/R23/C43/C44); add RC on mic VDD | Electret circuit on a self-biased part |
| 6 | Mic → SPH8878LR5H-1 | ICS-40720 discontinued |
| 7 | LED resistors 1 kΩ → 330 Ω | ~0.3 mA was invisible |
| 8 | TRRS → 3-pole TRS jack | 4th pole unused |
| 9 | Add TX input path + analog switch | TX mode now in scope |
| 10 | Add battery charger, NTC, cell connector, VBAT sense | Battery in scope |
| 11 | NCP1117 → low-dropout LDO in SOT-89 | 1.2 V dropout cannot run from a cell |
| 12 | Crystal load caps 18 pF → ~15 pF, then trim | Over-loaded; ±10 ppm required |

**Still open:** ground-loop mitigation (transformers vs battery-only playback); crystal offset
measurement; RF match tuning; BOM line consolidation.

---

## 11. Manufacturing

**JLCPCB**, 4-layer, **Economic PCBA** with the ESP32 excluded from assembly and hand-populated
(it is the only Standard-Only part). All other parts verified Economic-tier.

Constraints: single-sided placement (satisfied — nothing on the back is assembled), 0402 minimum
passive, 0.4 mm minimum IC pitch.

Build: 5 assembled + 5 bare. Target $20 USD landed per unit.

Hand assembly: 0.35 mm-pitch QFN requires a laser-cut stencil, plugged/capped via-in-pad on the
thermal pad (open vias wick solder and degrade the RF ground), and ~50–70 % paste coverage on the
exposed pad.

---

## 12. References

**Local** (`hw/datasheets/`, `hw/app notes/`)

- ESP32 datasheet · ESP32 Hardware Design Guidelines · ESP32 Technical Reference Manual
- ES8388 datasheet rev 5.0 · ES8388 User Guide
- W25Q32JV datasheet rev G
- ESP32-LyraT v4.3 schematic — reference design for the codec section
- AN043 2.4 GHz PCB Antenna · Antennas for IoT

**External**

- [JLCPCB PCB assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities)
- [ESP-ADF ES8388 driver](https://docs.espressif.com/projects/esp-adf/en/latest/api-reference/abstraction/es8388.html)
- [esptool — set flash voltage eFuses](https://docs.espressif.com/projects/esptool/en/latest/esp32/espefuse/set-flash-voltage-cmd.html)

**Project**

- [`requirements-design.md`](requirements-design.md) — requirements, constraints, traceability
- [`design-review-v1.md`](design-review-v1.md) — netlist audit and findings
- [`battery-power-proposal.md`](battery-power-proposal.md) — battery architecture
- [`mems-microphone-primer.md`](mems-microphone-primer.md) — mic theory and selection

---

## 13. Revision history

| Rev | Date | Change |
|---|---|---|
| A | 2025-04-05 | As-built schematic, commit `369c5f9` |
| B | 2026-08-24 | This document created. Scope decisions resolved; 12 deltas in §10 |
