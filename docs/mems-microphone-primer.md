# MEMS Microphones — Primer, and What's Wrong With Ours

Written 2026-08-23 in response to the request for a walk-through of the biasing question and of
differential vs single-ended. Ends with a replacement part and the corrected circuit.

---

## 1. What's actually inside the package

An analog MEMS microphone is three things in one can:

```
   acoustic port
        │
        ▼
  ┌──────────────┐   ┌──────────────────┐   ┌─────────────────┐
  │ MEMS element │──▶│ impedance        │──▶│ output          │──▶ OUT+ / OUT−
  │ (variable    │   │ converter        │   │ amplifier       │
  │  capacitor)  │   │ (JFET/charge amp)│   │ (buffer)        │
  └──────────────┘   └──────────────────┘   └─────────────────┘
```

1. **The MEMS element** is a capacitor with a movable diaphragm. Sound moves the diaphragm, which
   changes capacitance. It has enormous source impedance (picofarads) and produces almost no
   current — utterly unusable directly.
2. **The impedance converter** sits *inside the package*, microns away, and turns that
   ultra-high-impedance signal into something a PCB trace can carry without picking up everything
   in the room. This is the whole reason MEMS mics exist as integrated parts.
3. **The output amplifier** buffers and, in differential parts, produces two complementary outputs.

**The consequence that matters for us:** by the time the signal reaches the pins, it is already a
low-impedance, internally-biased, buffered analog voltage. It needs no help. Treat it like the
output of an op-amp, not like a bare transducer.

## 2. Why our bias network is wrong

This is the distinction the current schematic misses.

### Electret capsules DO need external bias

The traditional electret capsule contains a JFET whose **drain is brought out to a pin with nothing
attached**. You must supply a bias resistor to VDD — it is the JFET's drain load, and without it the
device has no operating point and produces nothing:

```
        VDD
         │
        ┌┴┐
        │ │  R_bias  (typically 2.2k)      ← REQUIRED. This is the load resistor.
        └┬┘
         ├──────╫──────▶  to amplifier   (AC coupled)
         │
      ╔══╧══╗
      ║ JFET║  electret capsule
      ╚══╤══╝
         │
        GND
```

That 2.2 kΩ-to-VDD pattern is one of the most copied circuits in hobby electronics.

### MEMS mics do NOT

The ICS-40720 datasheet (DS-000045 rev 1.4, Table 1) states the outputs are already biased:

| Parameter | OUT+ | OUT− |
|---|---|---|
| Output DC offset | **0.66 V** | **0.70 V** |
| Output impedance (single-ended) | 340 Ω | 410 Ω |

Those are *outputs of an internal amplifier with a defined operating point*. Add an external
resistor to a rail and you are not biasing anything — you are **fighting the internal amplifier**
through a divider.

### What our circuit actually does

The schematic puts 2.2 kΩ from `OUT+` **up** to a filtered 3.3 V node, and 2.2 kΩ from `OUT−`
**down** to ground. Working each divider against the mic's own output impedance:

```
OUT+ :  (0.66/340 + 3.3/2200) / (1/340 + 1/2200)  ≈  1.01 V     (was 0.66 V, pulled UP 0.35 V)
OUT− :  (0.70/410)            / (1/410 + 1/2200)  ≈  0.59 V     (was 0.70 V, pulled DOWN 0.11 V)
```

A 40 mV difference between the two halves becomes **≈ 420 mV of DC imbalance.**

**Why this hides.** C41/C42 block DC, so nothing wrong reaches the codec and the circuit measures
fine at DC. What it costs you is **headroom, asymmetrically**. Maximum single-ended output is
0.40 Vrms ≈ 0.57 V peak, and `OUT−` now sits only 0.59 V above ground — so the negative half-cycle
runs out of room first. The microphone clips earlier on one side than the other, at high SPL, in a
way that looks like distortion of unknown origin.

**The fix is deletion:** remove R21, R22, R23, C43 and C44. Keep C41/C42 as the AC coupling into the
codec's differential input. That is the entire correct circuit.

## 3. Differential vs single-ended

### The mechanism

A differential mic sends the signal twice, inverted, on two conductors. The receiver subtracts them:

```
wanted signal:   OUT+ = +V ,  OUT− = −V   →  (+V) − (−V) = 2V     ← doubles
picked-up noise: OUT+ = +N ,  OUT− = +N   →  (+N) − (+N) = 0      ← cancels
```

Interference couples into both traces roughly equally (it's **common-mode**), so subtraction rejects
it. The wanted signal is **differential**, so subtraction reinforces it.

### What you actually gain

| | Single-ended | Differential |
|---|---|---|
| Sensitivity | −38 dBV | **−32 dBV** (+6 dB, from the doubling above) |
| Common-mode noise rejection | none | **high** — the main reason to use it |
| Supply-noise immunity | poor — PSRR only | better; supply noise is largely common-mode |
| Traces needed | 1 + ground | 2, routed as a matched pair |
| Codec input | 1 input | 2 inputs (LIN1/RIN1 here) |

**On this board the noise argument is decisive.** The mic shares a PCB with a Bluetooth transmitter
producing ~250 mA current bursts. The ICS-40720's PSRR is only **−45 dB at 1 kHz** — supply and
ground noise passes through with little attenuation. Differential is not a refinement here; it is
the thing that makes an on-board mic viable next to a radio.

### Layout follows from the mechanism

The rejection only works if both conductors pick up the *same* noise. So:

- **Route OUT+ and OUT− as a tightly-coupled parallel pair**, same length, same layer, same
  neighbours. The ES8388 user guide says exactly this: *"The signal MIC_INP and MIC_INN must be
  parallel with each other on PCB layout."*
- Keep the pair short and away from the antenna, the switching edges and the USB lines.
- Don't split them around an obstacle — a detour on one side destroys the common-mode assumption.

## 4. The other MEMS specs worth understanding

**Sensitivity (dBV)** — output for a 94 dB SPL (1 Pa) input. Less negative = hotter. Only meaningful
alongside noise.

**SNR (dBA)** — the number that actually matters for voice. Sets how quiet a sound is usable.
65 dB is ordinary; **70 dB is good; 74 dB is excellent.** Ours is 70.

**Equivalent Input Noise (EIN)** — the same information as SNR, expressed as the SPL of the mic's own
noise floor. 24 dBA SPL means the mic hears its own hiss at the level of a very quiet room.

**Acoustic Overload Point (AOP)** — SPL at 10 % THD, i.e. where it clips. 120 dB is fine for voice;
you want more only for very loud sources. Note this is the *acoustic* ceiling — our bias-network
bug lowers the *electrical* ceiling below it, which is exactly why that finding matters.

**PSRR / PSR** — rejection of supply noise. Critical when sharing a board with a radio. Drives the
RC-filtered supply recommendation.

**Port location — bottom vs top.** Bottom-ported parts have the hole in the *PCB*, and the enclosure
seals against the board. Top-ported have it in the lid. **This is a mechanical decision made at
schematic time**: a bottom port needs an acoustic hole in the PCB and a gasket, and it constrains
the enclosure. Decide it before layout, not after.

**Package** — LGA with no visible leads; solder joints are hidden. **Never wash the board after
assembly** unless the part is rated for it — liquid in the acoustic port ruins it.

## 5. Replacement part

The **ICS-40720 is discontinued.** Two credible successors:

| | Knowles **SPH8878LR5H-1** | TDK **ICS-40730** |
|---|---|---|
| LCSC/JLCPCB | **C3171733** | check availability |
| JLCPCB tier | ✅ **Economic and Standard** | verify |
| Package | LGA-6, 3.5 × 2.7 mm, **MSL 1** | LGA, MSL to verify |
| Output | **Differential *and* single-ended** | Differential |
| SNR | ~66 dB | **74 dB** |

**Recommendation: SPH8878LR5H-1.** It is confirmed available, confirmed Economic-tier (so it does
not jeopardise the §2.1b assembly plan), MSL 1 (no baking), and it supports **both** output modes —
so you keep the differential connection the ES8388 wants while retaining a single-ended fallback if
the differential routing proves troublesome. The ICS-40730 has meaningfully better SNR (74 vs 66 dB)
and is the direct lineage successor; worth checking its JLCPCB tier and stock if microphone quality
turns out to matter more than the flexibility.

Either way: **verify stock and PCBA tier at selection time** (requirements §2.3), and re-check EOL —
that is what caught us on the ICS-40720.

## 6. The corrected circuit

```
        3V3_CODEC ──[ 100 Ω ]──┬──────────── MK1.VDD
                               │
                          [ 1 µF ]          ← RC supply filter: PSRR is only −45 dB,
                               │              and this rail feeds an analog part
                              GND

        MK1.OUT+ ──┬──╫ 100 nF ╫──▶ ES8388 LIN1
                   │
              [ 10 nF ]                      ← optional RF/EMI shunt. With the mic's
                   │                           ~340 Ω output this is a ~47 kHz corner,
                  GND                          safely above the audio band

        MK1.OUT− ──┬──╫ 100 nF ╫──▶ ES8388 RIN1
                   │
              [ 10 nF ]
                   │
                  GND
```

**Deleted from the current design:** R21, R22, R23, C43, C44 — the entire electret-style bias
network. **Added:** a series resistor on VDD to make the existing decoupling into a real RC filter.

Net effect: fewer parts, fewer BOM lines, correct operating point, and a supply that is actually
filtered.

## 7. Where to read more

- **ES8388 user guide** (`hw/app notes/ES8388-user-guide-application-note.pdf`, p.6) — the codec's own
  requirements: differential mic recommended, `MIC_INP`/`MIC_INN` parallel on the PCB, and the
  supply/decoupling notes. Start here; it is the document this design must satisfy.
- **ICS-40720 datasheet** (DS-000045) — Table 1 is the worked example of everything in §2. Read the
  Output Characteristics rows and compare them against what our schematic does to those pins.
- **TDK InvenSense application notes on MEMS microphone PCB design** — port sealing, gasket choice,
  bottom-port hole sizing, and the "do not wash the board" rule. The mechanical side is where most
  first-time MEMS designs actually fail.
- **Knowles application notes** — good, short treatments of differential vs single-ended and of
  acoustic port design.
- For the underlying theory, any treatment of **balanced audio interconnects** covers the
  common-mode rejection argument in §3 more rigorously; the mechanism is identical to balanced line
  audio, just at chip scale.
