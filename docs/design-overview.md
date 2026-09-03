# Bluetooth Audio Adaptor — Design Overview

**Rev B (in design)** · Updated 2026-09-03 · Jason
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
                      │  Li-ion cell     │──── NTC ──► TS   temperature qualification
                      │  + 10 k NTC      │
                      └────────▲─────────┘
                               │ BAT ──[100k]──┬── BAT_ADC ──► ADC1
                               │               └──[100k]── GND
  USB-C ── VBUS 5 V ──► ┌──────┴───────┐
    ├─ USBLC6 (ESD)     │   BQ24074    │  power path · DPPM
    ├─ CC1/CC2 ──► ADC1 │   charger    │  SYS clamped ≤ 4.4 V
    └─ C47 10 µF        └──┬───────┬───┘
                           │       ├── EN1 / EN2  ◄── GPIO   input-limit select
       ILIM ISET ──────────┘       ├── /PGOOD, /CHG ──► GPIO
       ITERM TMR                   │
                               SYS │ 3.0 – 4.4 V
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
| **USBLC6-2SC6** | USB ESD | In-line on D+/D−; its `VBUS` pin stays at the connector, upstream of the charger |
| Li-ion cell + 10 k NTC | Energy | Removable. NTC bonded to cell, not PCB |

**VBUS reaches exactly three things:** the ESD array, the charger's `IN` pin, and `C47`. Every other
load in the system hangs off `SYS`, including both LDOs. That is what makes the board behave
identically on USB and on battery.

### 3.1 Power path — the five loops

In priority order. The system load always outranks the battery.

| Loop | Trips at | Behaviour |
|---|---|---|
| Input current limit | `EN1`/`EN2` + `R_ILIM` | Hard ceiling on total current into `IN`. Everything else lives inside this budget |
| VIN-DPM | V<sub>IN</sub> falls to 4.5 V | Reduces input current so a weak source cannot be crashed. **Active only in USB100/USB500 modes** |
| DPPM | V<sub>SYS</sub> falls to V<sub>O(REG)</sub> − 100 mV ≈ 4.3 V | Cuts *charge* current to hold SYS up. Charge termination is disabled while active |
| Battery supplement | V<sub>SYS</sub> < V<sub>BAT</sub> − 40 mV | Charge current already zero and the load still exceeds the input limit — BATFET turns fully on and the cell supplements. Exits above V<sub>BAT</sub> − 20 mV |
| Thermal regulation | T<sub>J</sub> ≥ 125 °C | Folds back charge current regardless of the above |

The last three slow the safety timers **in proportion to the charge-current reduction**. A
deliberately low `R_ISET` gets no such slowdown — the timer would run at full speed while the cell
trickled. This is why `R_ISET` is set *above* anything the input can deliver, and DPPM is left to
mediate (§3.3).

### 3.2 Input current limit — mode strapping

`EN2`/`EN1` select the limit. Datasheet Table 7-2 orders the columns EN2, EN1:

| EN2 | EN1 | Limit | When |
|---|---|---|---|
| 0 | **1** | **475 mA (USB500)** | **Power-on default** — and any unknown or default-USB source |
| 1 | 0 | 1.073 A (`R_ILIM`) | Firmware has confirmed a ≥1.5 A source (§3.4) |
| 0 | 0 | 95 mA (USB100) | Strict compliance on an un-enumerated host port |
| 1 | 1 | — | Standby / USB suspend |

**The default must be USB500, not USB100.** Both pins floating gives USB100 through the chip's
285 kΩ internal pulldowns, and 100 mA cannot run a 171 mA system: with a flat cell the board would
brown out before firmware ran and could never raise the limit. USB500 boots the system, matches what
a PC port allows after enumeration, and is a mode that has VIN-DPM behind it.

```
   SYS ──[R30 100k]──┬── EN1 ──► GPIO (drive open-drain)     default HIGH (3.26 V)
                     │
                (285k internal pulldown)

   GND ──[R31 100k]──┴── EN2 ──► GPIO (push-pull)            default LOW
```

**100 kΩ, not 0 Ω** — the GPIO must be able to override the resistor. Against the internal 285 kΩ,
EN1 sits at 4.4 × 285/385 = 3.26 V, comfortably over the 1.4 V V<sub>IH</sub>.

**Pull up to `SYS`, not `3V3_A`** — `3V3_A` does not exist until the system has booted, and the whole
point of the default is to be defined before that. `SYS` is present whenever either source is, and at
4.4 V max sits inside the EN pin's 1.4–6 V window (7 V absolute max).

Drive `EN1` open-drain: the pull-up is to 4.4 V and the GPIO drives 3.3 V. Leave both pins alone
whenever `/PGOOD` is high-Z — the EN inputs are ignored in power-down mode, and driving EN1 low would
only burn cell current through R30.

### 3.3 Charge programming

| Resistor | Value | Formula | Result |
|---|---|---|---|
| `R_ISET` | 1.2 kΩ **1 %** | I<sub>CHG</sub> = K<sub>ISET</sub>/R, K = 890 | **742 mA** (664–812 over spread) |
| `R_ILIM` | 1.5 kΩ | I<sub>IN(max)</sub> = K<sub>ILIM</sub>/R, K = 1610 | **1.073 A** |
| `R_ITERM` | 3.0 kΩ | I<sub>TERM</sub> = 0.03 × R<sub>ITERM</sub>/R<sub>ISET</sub> | **75 mA** (≈C/27 on a 2000 mAh cell) |
| `R_TMR` | 56 kΩ | t<sub>MAXCHG</sub> = 10 × K<sub>TMR</sub> × R, K = 48 s/kΩ | **7.5 h** (5.6 h worst case) |

Pre-charge falls out of the same ISET resistor: K<sub>PRECHG</sub>/R<sub>ISET</sub> = 88/1200 =
**73 mA**, the conventional 10 % of fast charge.

742 mA is 0.37C on a 2000 mAh cell and 0.25C on a 3000 mAh one — safe for either, so this resistor
does not depend on the cell decision. Use 1 % on `R_ISET`: TI calls this out specifically to avoid
tripping the internal RISET short-circuit test.

**`ILIM` must never be left open — an open `ILIM` pin disables all charging.** Worth an explicit
bring-up check.

`R_NTC_LIN` is fitted **DNP** by design: it stands in for the pack NTC if a cell without one is used,
or can be replaced by a high-value linearising resistor. It must not be populated alongside a real
NTC — see §3.6.

### 3.4 Source capability detection

The default is USB500, so detection only ever has to answer one question: **is this a ≥1.5 A
charger?** Everything else falls back safely.

**CC sensing (C-to-C only).** `R36`/`R37` tap CC1/CC2 through 1 kΩ into ADC1. With Rd = 5.1 kΩ:

| Source Rp | V<sub>CC</sub> | Advertised |
|---|---|---|
| 56 kΩ | 0.42 V | Default USB |
| 22 kΩ | 0.94 V | 1.5 A |
| 10 kΩ | 1.69 V | 3.0 A |

Thresholds: >0.2 V attached, >0.66 V ≥ 1.5 A, >1.23 V = 3.0 A. Read **both** pins — only one carries
the Rp, the other is open or is VCONN, and the pair also gives plug orientation. **No filter capacitor
on the CC nodes:** the spec caps sink CC capacitance at ~200 pF. Multisample in software instead.
Re-read periodically; a source may change its advertisement at any time.

**The limitation that shapes the architecture:** a USB-A-to-C cable is *required* by the spec to
contain a 56 kΩ Rp, so CC always reports Default USB no matter how large the charger behind it. For
the expected majority case — an A-to-C cable — CC sensing tells you nothing.

**BC1.2 (not fitted).** The only mechanism that unlocks a USB-A wall charger, by detecting that D+ is
shorted to D− through ≤200 Ω (a Dedicated Charging Port). Needs a detector IC — BQ24392 or MAX14636 —
whose integrated D+/D− isolation switch also solves the problem that the CH340K sits on that bus.
Deferred; the EN1/EN2 GPIO control above is what keeps it a firmware-plus-one-IC change rather than a
respin.

**Guard rail.** ILIM mode has no VIN-DPM, so a wrong detection has no graceful foldback. `R38`/`R39`
(100 k / 47 k) divide VBUS to `USB_VBUS_SENSE` — 5.0 V → 1.60 V, 5.5 V → 1.76 V — with `C53` 100 nF at
the tap. Firmware reverts to USB500 if VBUS sags below ~4.5 V. The divider only draws (34 µA) when USB
is present, so it costs nothing on battery.

100 nF rather than the 1 µF used on `BAT_ADC`: this is a protection function with a deadline. Against
the divider's 32 kΩ Thévenin impedance it gives τ = 3.2 ms, so a 100 ms poll sees a collapse ~30 τ
after it happens. A larger cap would average over a third of the reaction window.

**Do not** probe adaptively — stepping up to ILIM mode and watching what happens. Without VIN-DPM the
failure mode is a brownout, not a graceful foldback.

> **Accepted risk — CC pins have no ESD protection.** The USBLC6 covers D+/D− and VBUS only. CC1 and
> CC2 are exposed contacts in the receptacle and are directly touchable, so IEC 61000-4-2 contact
> discharge is a live threat. The 1 kΩ series resistors (`R36`/`R37`) protect the ADC pins but not
> `R4`/`R5` or the connector node itself. They also bound a VBUS-to-CC short — which the USB-C spec
> requires sinks to survive — to (5 − 3.6)/1 k ≈ 1.4 mA of clamp injection at the ESP32, which the pin
> tolerates; a faulty 20 V source would push 16 mA, which it does not.
>
> **Decision (2026-08-30): not mitigated in Rev B.** The fix, if it is ever wanted, is a
> low-capacitance TVS array on CC1/CC2 placed at the connector ahead of `R36`/`R37` — sub-pF against
> the ~200 pF sink CC budget, and low leakage so it does not corrupt the resistive advertisement.
> TPD4E05U06 is the obvious candidate. Revisit if field units show USB-C detection failures.

### 3.5 Safety timers

`R_TMR` = 56 kΩ gives a 7.5 h fast-charge timer (5.6 h worst case) and a 45 min pre-charge timer.
Leaving `TMR` floating selects the internal default of 5 h typ / 4 h min; grounding it disables the
timers entirely.

The timer must outlast the slowest legitimate charge. Worst case is a 3000 mAh cell charging in
USB500 mode while playing: ~304 mA of charge current against 742 mA programmed is a 0.41 reduction,
so the 5.6 h timer counts at 0.41× and covers 13.7 h of wall clock against an 8.9 h charge.

On expiry the part latches a fault and **`/CHG` flashes at ~2 Hz**. Firmware should decode that — it
is also how a TS fault surfaces, and it is otherwise invisible.

### 3.6 Battery temperature qualification

Mandatory in hardware, not firmware. `TS` sources 75 µA into the pack thermistor and compares:

```
V_HOT  = 300 mV   →  R_TS ≤ 4.0 kΩ   →  too hot    (≈50 °C on a 10 k 103AT-2)
V_COLD = 2100 mV  →  R_TS ≥ 28 kΩ    →  too cold   (≈ 0 °C)
```

The valid window is therefore **4.0 kΩ – 28 kΩ**, which a bare 10 k Type-2 NTC maps onto 0–50 °C with
3 °C hysteresis. Any added network shifts those trip points: a 10 kΩ resistor in parallel with the NTC
moves the hot trip to ~33 °C, and a 1 kΩ resistor pins R<sub>TS</sub> below 1 kΩ permanently,
inhibiting all charging. **Fit the pack NTC or `R_NTC_LIN`, never both.**

### 3.7 Status and state of charge

`/PGOOD` and `/CHG` are open-drain, pulled up to **`3V3_A`** (not `SYS`) so both nets are clean 3.3 V
logic a GPIO can read directly — pulling them to the 4.4 V SYS rail would exceed the ESP32's input
rating.

| /PGOOD | /CHG | State |
|---|---|---|
| Hi-Z | Hi-Z | Running on battery |
| Low | Low | Charging |
| Low | Hi-Z | Charge complete, or suspended |
| Low | **2 Hz flash** | Fault — safety timer expired, or TS out of range |

`R28`/`R29` are 330 Ω, giving ~2.7 mA per LED at 3.3 V — visible, and inside the 5 mA the `/PGOOD`
and `/CHG` open-drain outputs are specified to sink. Both LEDs are dark on battery, since the pins go
high-impedance with no input present.

**State of charge** is voltage-based: `R34`/`R35` form a 100 k / 100 k divider from `BAT` to ground,
tapped as `BAT_ADC` (4.2 V → 2.1 V, inside ADC1's usable 150–2450 mV window at 11 dB attenuation).
It costs 21 µA continuously, ~15 mAh/month — negligible against the cell.

**`C52` 100 nF at the tap is not optional, and it is not impedance matching.** It does two jobs:

- **Charge reservoir.** The ESP32's ADC is successive-approximation: closing the sampling switch
  requires an internal sample-and-hold capacitor of a few pF to charge to the input voltage *through
  the external source impedance*, in a few microseconds. The divider's Thévenin impedance is
  100 k ‖ 100 k = **50 kΩ**, five times Espressif's <10 kΩ guideline, so without a local cap each
  conversion drags the node down and the converter digitises the droop. At ~10⁴ times the S/H
  capacitance, `C52` supplies that charge with no measurable sag and refills through the 50 kΩ
  between samples.
- **Low-pass filter.** f_c = 1/(2π × 50 k × 100 nF) = **31.8 Hz**, τ = 5 ms. `BAT_ADC` is a
  high-impedance trace crossing the board — exactly the node that collects switching and RF noise —
  and cell voltage moves over minutes, so heavy filtering is free accuracy. Allow ~25 ms after
  power-up before trusting a reading.

The alternative was a lower-impedance divider: 10 k / 10 k needs no cap but draws 210 µA from the cell
permanently instead of 21 µA. The capacitor is the cheaper trade.

Calibrate with `esp_adc_cal` and the eFuse Vref, and multisample; raw ADC error is ±6 %, which is
±250 mV of cell voltage and useless.

Two limits define what this can deliver. The reading is meaningless while charging — the charger is
driving V<sub>BAT</sub> toward 4.2 V — so firmware uses the `/PGOOD`+`/CHG` state instead and snaps to
100 % on termination. And the Li-ion OCV curve is flat from roughly 20 % to 80 % SoC, so voltage alone
gives ±10–15 % there. **This is a four-segment gauge and a dependable low-battery warning, not a
trustworthy percentage.** If a real percentage is ever needed over AVRCP, add a MAX17048 to the
existing I²C bus.

### 3.8 ESP32 GPIO map (committed 2026-08-31, netlist-verified)

Complete map. The budget is **full**: one spare (`GPIO33`). `S` marks an ESP32 strapping pin — its
level is latched at reset, so anything on it must present the right level at boot (see the implications
list below). All analog is on **ADC1** because ADC2 is dead whenever the radio is on.

| GPIO | Pin | Signal | Dir | S | Boot level / notes |
|---|---|---|---|---|---|
| 0 | 23 | `MCLK` (I²S) | out | **S** | Must be HIGH at boot. Internal PU; codec MCLK input is Hi-Z at reset. Auto-boot pulls it low for download. |
| 1 | 41 | `UART_TX` (U0TXD → CH340 RXD) | out | | Boot-log UART. |
| 2 | 22 | `CHARGE_EN` (→ charger `/CE`) | out | **S** | Must be LOW/float at boot — and `R32` (1 k→GND) holds it low, which also = **charging enabled**. FW drives HIGH to pause charging; any reset re-enables (fail-safe). Keeps TP4. |
| 3 | 40 | `UART_RX` (U0RXD ← CH340 TXD) | in | | |
| 4 | 24 | `AUDIO_VCC_EN` (→ LDO B EN) | out | | `R33` pulldown → codec rail **off at boot**; FW raises to power codec. |
| 5 | 34 | `AUDIO_SW` (→ TS5A23159 IN1+IN2) | out | **S** | Internal PU → HIGH at boot = **TX** by default. **Do not add an external pull.** FW sets **LOW = RX**, HIGH = TX. |
| 6–11 | 31,32,33,28,29,30 | SPI flash (`CLK`/`SD0-3`/`CMD`) | — | | Reserved for `VDD_SDIO` flash. Not available. |
| 12 | 18 | `MTDI` (JTAG TDI) | I/O | **S** | **VDD_SDIO voltage select — must be LOW at boot for 3.3 V flash.** Pull-up `R26` is **DNP — do not populate.** A debugger driving TDI high across reset bricks boot. |
| 13 | 20 | `MTCK` (JTAG) | I/O | | J4 DNP header. |
| 14 | 17 | `MTMS` (JTAG) | I/O | | J4 DNP header. |
| 15 | 21 | `MTDO` (JTAG TDO) | I/O | **S** | Must be HIGH at boot (enables boot log). Internal PU. |
| 16 | 25 | `EN1` (charger limit) | out (OD) | | Drive **open-drain** (pull-up is to 4.4 V SYS). Ext 100 k→SYS = USB500 default at boot. |
| 17 | 27 | `EN2` (charger limit) | out | | Ext 100 k→GND = default LOW at boot. |
| 18 | 35 | `I2C_CLK` | I/O | | To ES8388 + codec bus. |
| 19 | 38 | `LED_GREEN` | out | | |
| 21 | 42 | `CH340_EN` (→ Q2 gate) | out | | `R40` pulldown → **default ON** so the bridge is powered for flashing; FW drives HIGH to disable on battery. |
| 22 | 39 | `LED_BLUE` | out | | |
| 23 | 36 | `I2C_DATA` | I/O | | |
| 25 | 14 | `LRCK` (I²S) | I/O | | |
| 26 | 15 | `DSDIN` (I²S) | out | | |
| 27 | 16 | `SCLK` (I²S) | I/O | | |
| 32 | 12 | `/CHG` (charger status) | in | | ADC1_CH4 used as digital in. |
| 33 | 13 | **spare** | — | | ADC1_CH5. Fit a no-connect flag. |
| 34 | 10 | `BAT_ADC` | in | | ADC1_CH6, input-only. |
| 35 | 11 | `ASDOUT` (I²S data in) | in | | ADC1_CH7, input-only — correct home for an input-only signal. |
| 36 | 5 | `USB_CC1` | in | | ADC1_CH0, input-only. |
| 37 | 6 | `USB_CC2` | in | | ADC1_CH1, input-only. |
| 38 | 7 | `/PGOOD` (charger status) | in | | ADC1_CH2, input-only. |
| 39 | 8 | `USB_VBUS_SENSE` | in | | ADC1_CH3, input-only. |

**Strapping-pin implications (the ones that bite):**

- **GPIO0 / GPIO2** — the boot-mode pair. Normal boot needs GPIO0 high, GPIO2 low. GPIO0 doubles as
  MCLK (codec input Hi-Z at reset, so safe) and the auto-boot circuit pulls it low to flash. GPIO2 =
  `CHARGE_EN`, held low by `R32` — which satisfies both "low at boot" *and* "charging enabled by
  default." FW must only drive GPIO2 high (pause charge) *after* boot.
- **GPIO12 (MTDI)** — sets flash voltage at reset. It **must be low** (→ 3.3 V); `R26` is the 1.8 V
  pull-up and is **DNP by design**. HW: never populate `R26`. FW/bench: an attached JTAG debugger can
  drive TDI high across reset and select 1.8 V, bricking boot — either detach during power-up or burn
  the `XPD_SDIO_*` eFuses to force 3.3 V (irreversible).
- **GPIO15 (MTDO)** must be high at reset (internal PU handles it); leave it undriven at boot.
- **GPIO5 (AUDIO_SW)** samples high at reset (SDIO-timing strap, irrelevant here). Consequence: the
  audio switch defaults to **TX** at boot. Harmless (no audio yet); FW drives it **low = RX** on init.
  The only HW rule: **do not tie an external pull to GPIO5**, or it fights the strap.
- General FW rule: every strapping pin used as an output must be left as an input (Hi-Z) through reset
  and only driven once the app starts — external pulls (or the internal strap pull) set the boot state.

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

**Charge current and time.** `R_ISET` programs 742 mA, but the input limit is what actually binds in
every mode except ILIM. CC delivers ~85 % of capacity; the CV tail to a 75 mA termination adds ~0.5 h.

| Mode | Input | System | Charge | 2000 mAh | 3000 mAh |
|---|---|---|---|---|---|
| USB500, idle | 475 mA | ~20 mA | 455 mA | 4.2 h | 6.1 h |
| USB500, playing | 475 mA | 171 mA | 304 mA | 6.1 h | 8.9 h |
| ILIM, either | 1.073 A | 20–171 mA | **742 mA** (ISET binds) | 2.8 h | 3.9 h |

**Charger thermal.** Linear, so the charger burns (V_IN − V_BAT) × I_CHG plus the pass-FET loss.
Worst case is the start of fast charge, V_BAT ≈ 3.0 V, in ILIM mode:

```
P = (5.0 − 4.4) × 0.913  +  (4.4 − 3.0) × 0.742  =  0.55 + 1.04  =  1.59 W
VQFN-16 RGT, θJA = 44.5 °C/W  →  ΔT = 71 °C  →  Tj ≈ 96 °C at 25 °C ambient     ✓
                                                Tj ≈ 116 °C at 45 °C ambient    ✓ (reg. point 125 °C)
USB500 mode: P = 0.71 W  →  ΔT = 32 °C  →  Tj ≈ 57 °C                           ✓
```

The input current limit is what guarantees this — raising `R_ISET` cannot overheat the part, because
`ILIM` caps the current before it gets there.

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
| **Flash mode** | Either works: IO2/IO3 uncrossed on the schematic 2026-08-31 (delta #4 applied), so QIO is now safe. DIO remains a fine default. |
| **JTAG + GPIO12** | MTDI is the VDD_SDIO strapping pin. A debugger driving TDI high across reset selects 1.8 V and the 3.3 V flash fails. Fix: burn `XPD_SDIO_*` eFuses to force 3.3 V. **Irreversible.** |
| **Codec I²C address** | 0x20 (`CE` low). ESP-ADF's ES8388 driver default. |
| **I²S full duplex** | Required for HFP. Configure both TX and RX channels. |
| **TX/RX switch** | `AUDIO_SW` (GPIO5) drives both TS5A23159 control inputs (IN1+IN2 tied — the two switches are the L/R channels of one select). **LOW = RX** (jack ← LOUT1/ROUT1), **HIGH = TX** (jack → LIN2/RIN2). GPIO5 is a strapping pin: boot default is HIGH (=TX); FW must set LOW for playback on init. |
| **Charge enable** | `CHARGE_EN` (GPIO2) → charger `/CE`, active-low. `R32` holds it low = charging enabled at boot; FW drives HIGH to pause charging. GPIO2 is a strapping pin (must be low at boot) — the pulldown satisfies both. A reset re-enables charging (fail-safe); the NTC still guards temperature regardless. |
| **Deep sleep** | If used for battery standby, populate the CAP2 RC network. |
| **Charger limit sequencing** | Boot default is USB500 (§3.2). Firmware may raise to ILIM mode only after confirming a ≥1.5 A source. Drive `EN1` open-drain; leave both pins alone when `/PGOOD` is high-Z. |
| **CC read** | `USB_CC1`/`USB_CC2` on **ADC1**. Read both, take the one in a valid band. An A-to-C cable always reports Default USB — do not treat that as a fault. |
| **`/CHG` fault** | A ~2 Hz flash is a latched fault (timer expiry or TS out of range), not "charging". Decode it; clear by toggling `CE` or the input. |
| **SoC blindness** | `BAT_ADC` is meaningless while charging. Report charger state instead, and snap to 100 % when `/CHG` releases. |
| **Codec rail** | `AUDIO_VCC_EN` is pulled low, so LDO B is **off at reset**. Firmware must enable it before touching the codec on I²C/I²S, or the ESP32 will back-power the ES8388 through its ESD diodes. |
| **CH340K gate** | Bridge is on a GPIO-controlled switch. Keep it off when USB is absent (~10 mA of battery budget) and during any BC1.2 detection. |

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
| 13 | Charger input limit made firmware-selectable (`EN1`/`EN2` on GPIOs, 100 kΩ pulls) | Fixed strap cannot adapt to source capability; default USB500 boots on a flat cell |
| 14 | `/PGOOD`, `/CHG` pull-ups moved SYS → 3V3_A and routed to GPIOs | 4.4 V exceeds the ESP32 input rating; status was LED-only |
| 15 | Add `BAT_ADC` divider, CC1/CC2 sense taps | State of charge (REQ-PWR-10) and source detection |
| 16 | Gate the CH340K on a GPIO | ~10 mA of battery budget with USB absent |

**Still open:** cell choice (2000 mAh pouch vs 3000 mAh 18650) and therefore charge time; whether to
fit BC1.2 detection; ground-loop mitigation (transformers vs battery-only playback); crystal offset
measurement; RF match tuning; BOM line consolidation.

**Accepted risks:** CC pins carry no ESD protection (§3.4) — decided 2026-08-30, not mitigated in
Rev B.

**Micro-sheet status** (§3 describes the target). Tracking the 2026-08-31 micro-sheet review
([`design-review-micro.md`](design-review-micro.md)) and the fixes applied since.

*Applied on the schematic (verified against netlist 2026-08-31):*
- ✅ **UART TX/RX crossover fixed** — `UART_RX` = {ESP32 U0RXD, CH340 TXD}, `UART_TX` = {U0TXD, CH340
  RXD}. Board can now be flashed. (was S1)
- ✅ **Flash IO2/IO3 uncrossed** — SPIWP(GPIO9)→IO2, SPIHD(GPIO10)→IO3. QIO-safe now. (delta #4, was S1)
- ✅ **Digital rail unified** — micro `+3V3` renamed to `+3V3_SYS`, tied to the LDO A output (U7.5).
  The stray `+3V3` symbol on the ESP32 `EN` pull-up (R11) was also switched to `+3V3_SYS`, so `EN`
  is no longer floating.
- ✅ **CH340K load switch drawn** (delta #16) — `Q2` AO3401A (SOT-23, LCSC C15127) high-side P-FET:
  source `+3V3_SYS` → drain `CH340_VCC` → CH340 VCC/V3 + C19. Gate `CH340_EN` on **GPIO21**, with
  `R40` 100 kΩ **pull-down = default-ON** (so the ROM bootloader is powered for flashing with no
  firmware). Firmware drives GPIO21 **high to disable** the bridge on battery. Note: when off, the
  bridge's UART/DTR/RTS pins can still back-feed its dead VCC through clamp diodes — tristate the
  ESP32 UART pins when disabling, or accept the small leakage.

- ✅ **Full ESP32 interface wired** (§3.8) — `EN1`/`EN2`/`/PGOOD`/`/CHG`/`BAT_ADC`/`USB_CC1`/`USB_CC2`/
  `USB_VBUS_SENSE`/`AUDIO_VCC_EN`/`CHARGE_EN` all land on GPIOs; all four analog senses on ADC1. The
  TX/RX switch (`AUDIO_SW`, GPIO5) drives both TS5A23159 control inputs (delta #9 now controllable).
  Charge enable (`CHARGE_EN`, GPIO2) is now firmware-controllable.

*Still to do on the micro sheet:*
- **Crystal load caps still 18 pF** (delta #12 not applied; target ~15 pF then trim).
- **Firmware LEDs D1/D3 still 1 kΩ** (delta #7 hit the power LEDs only; blue ≈ 0.3 mA, invisible).
- **`GPIO33` spare** — fit a no-connect flag so it doesn't ERC.
- **Schematic hygiene:** stale library-symbol caches, off-grid endpoints, annotation errors — ERC
  cleanup due.

**Rev A→B deltas still unapplied:** #7 (LED resistors — micro sheet only), #12 (crystal caps).
Deltas #4, #9, #13–16 are now on the schematic.

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
- WCH CH340 datasheet v3B (`WCH-CH340-datasheet-v3B.pdf`) — TXD=output, RXD=input; V3→VCC at 3.3 V
- ESP32-LyraT v4.3 schematic — reference design for the codec section
- AN043 2.4 GHz PCB Antenna · Antennas for IoT

**External**

- [JLCPCB PCB assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities)
- [ESP-ADF ES8388 driver](https://docs.espressif.com/projects/esp-adf/en/latest/api-reference/abstraction/es8388.html)
- [esptool — set flash voltage eFuses](https://docs.espressif.com/projects/esptool/en/latest/esp32/espefuse/set-flash-voltage-cmd.html)

**Project**

- [`requirements-design.md`](requirements-design.md) — requirements, constraints, traceability
- [`design-review-v1.md`](design-review-v1.md) — netlist audit and findings (initial)
- [`design-review-micro.md`](design-review-micro.md) — micro-sheet review, 2026-08-31
- [`battery-power-proposal.md`](battery-power-proposal.md) — battery architecture
- [`mems-microphone-primer.md`](mems-microphone-primer.md) — mic theory and selection

---

## 13. Revision history

| Rev | Date | Change |
|---|---|---|
| A | 2025-04-05 | As-built schematic, commit `369c5f9` |
| B | 2026-08-24 | This document created. Scope decisions resolved; 12 deltas in §10 |
| B | 2026-08-30 | §3 expanded to cover the full charger configuration: power-path loops, EN1/EN2 strapping, charge programming, source detection, safety timers, TS qualification, SoC and GPIO map. Deltas 13–16 |
| B | 2026-08-30 | Power sheet complete: `R_ITERM`/`R_TMR` populated, LEDs to 330 Ω, ADC anti-droop caps and VBUS sense divider added. CC ESD recorded as an accepted risk |
| B | 2026-08-31 | Micro-sheet review ([`design-review-micro.md`](design-review-micro.md)): found UART TX/RX swap (S1) and confirmed flash IO2/IO3 still crossed; corrected the §9 "flash fixed" claim and the §3.8 GPIO map (added TX/RX switch, fixed the free-output count); expanded §10 with the undrawn micro↔power interface and unapplied deltas |
| B | 2026-08-31 | Micro-sheet fixes landed: UART crossover, flash IO2/IO3, rail unified to `+3V3_SYS` (EN pull-up reconnected), and CH340K high-side load switch drawn (Q2 AO3401A + R40 100 kΩ pull-down, gate `CH340_EN` on GPIO21, default-ON). Netlist-verified. Remaining: interface wiring to ESP32, TX/RX switch GPIO, crystal caps, D1/D3 resistors |
| B | 2026-08-31 | Full ESP32 GPIO map committed (§3.8) with strapping-pin FW/HW implications: interface signals wired to the ESP32 (EN1/EN2, /PGOOD, /CHG, ADC senses, AUDIO_VCC_EN, CHARGE_EN→GPIO2), `AUDIO_SW`→GPIO5 driving both TS5A23159 inputs (LOW=RX, HIGH=TX). Verified TS5A23159 pinout against TI datasheet — COM=jack/NC=codec-out/NO=codec-in, both channels symmetric (a prior review note claiming asymmetry was wrong, now withdrawn). Remaining: crystal caps, D1/D3 resistors, GPIO33 NC flag, ERC hygiene |
