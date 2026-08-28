# Lithium Battery Power — Design Proposal

**Status:** ✅ **ACCEPTED 2026-08-23** (decision D1). Battery is in scope. Answers to the follow-up
questions are in §0 below; the rest of the document stands as the design.
**Date:** 2026-08-20
**Relates to:** [`requirements-design.md`](requirements-design.md) §7 (backlog item "Battery backup via coin cell"), [`design-review-v1.md`](design-review-v1.md) §3.1, §3.5(a)

---

## 0. Answers to the follow-up questions (2026-08-23)

### 0.1 State retention across power-off — you do not need the battery for this

**The ESP32 already persists Bluetooth pairing without any battery.** ESP-IDF's Bluedroid stack
writes bonding data — link keys and peer information — into a dedicated **NVS namespace in the
external SPI flash**, automatically, when pairing completes. NVS is non-volatile, so it survives
power-off, deep sleep and reset alike. On reconnection the stack looks the peer up and reuses the
stored key.

So the answer to "flash or deep sleep?" is **flash, and it is already happening** — it is a property
of the stack, not something you design for. Requirements are:
- an **NVS partition must exist and be initialised** (`nvs_flash_init()`), which is the default in
  every standard partition table;
- the flash chip must work, which makes the `IO2`/`IO3` swap (§7) worth fixing;
- if you ever want to *forget* devices you call the remove-bond API — the interesting problem here
  is clearing pairings, not keeping them.

**Deep sleep is a different tool for a different job.** It preserves *RTC* memory and cuts standby
current to ~10 µA; it is how you stop a battery draining between uses. It is not how you keep
pairing — that is already handled. So:

| Goal | Mechanism |
|---|---|
| Remember paired phones across power-off | **NVS in flash — automatic, no action** |
| Don't flatten the cell while parked | **Deep sleep, or a hard power switch** |
| Resume quickly without a full boot | Deep sleep + RTC memory |

**This removes use case A from the battery's justification** (§1) — retention was never a reason to
add a cell. The remaining justifications are the ground loop (B) and portable use (C), which is what
you selected. Worth stating plainly so the battery is not defended on a benefit it never provided.

**One consequence:** if you use deep sleep for standby, the ESP32 `CAP2` RC network becomes relevant
again — see §5. It only matters for sleep entry, which is exactly what you would now be doing.

### 0.2 LFP instead of LiPo — safer chemistry, but it costs you the power architecture

Good instinct, and worth taking seriously. LiFePO₄ genuinely is the safer chemistry: thermal runaway
onset near 270 °C versus ~150 °C for LCO/NMC, no oxygen release, and far better tolerance of heat in
storage. If the device were living permanently in a hot car it would be the right answer.

**But the voltage does not fit this board.**

| | Li-ion / LiPo | LiFePO₄ |
|---|---|---|
| Nominal | 3.7 V | **3.2 V** |
| Range | 4.2 → 3.0 V | 3.65 → 2.5 V |
| Time spent **above 3.55 V** (what a 3.3 V LDO needs) | **~83 % of capacity** | **almost none** |
| Regulation to 3.3 V | LDO works | **Boost converter required** |
| Charger | BQ24074 (4.2 V termination) | needs an LFP-specific 3.65 V charger |

LFP sits *below* your 3.3 V rail for essentially its whole discharge curve. You would have to put a
**switching boost converter in front of an audio codec** — which is precisely the noise source the
whole power architecture was built to avoid (the v1 decision to drop the TPS5430 buck was correct
for exactly this reason). You would also need a different charger IC, losing the BQ24074's power
path and its 4.4 V output clamp, which is what makes the LDO thermals work (§3.2).

**Recommendation: stay with Li-ion, and mitigate by usage rather than chemistry.** Since D2 confirms
the device will not live in the car, the storage hazard is largely removed by taking it inside. Keep
the two hardware mitigations that still matter:
- **NTC on the charger's `TS` pin — mandatory**, inhibits charging outside the safe window;
- **removable cell** (JST-PH or an 18650 holder), so it can be taken out of a hot car.

Revisit LFP only if the usage assumption changes — and accept a boost converter and a codec LDO
behind it if so.

### 0.3 Ground loop with a charger in the picture — power path alone does not solve it

You are right that the equation changes, and right that isolation is still needed. Being precise
about when:

| State | Chassis-ground path via USB? | Ground loop? |
|---|---|---|
| Running on battery, USB **unplugged** | none | ✅ **No loop** — genuinely fixed |
| Running on USB, or charging while playing | present | ❌ **Loop still there** |

Power path buys you a clean listening mode, not a fix. **The loop returns the moment you plug in**,
which for a device that lives in a car is most of the time.

Three practical ways to close it, in order of what I would actually do:

**(a) Audio isolation transformers on the outputs — recommended.**
A 1:1 transformer in each output channel breaks the galvanic path at the audio side, so it works
regardless of how the board is powered. Two small parts, no active devices, no supply implications.
Provision it cheaply: **lay out R7/R8 so each position accepts either a 0 Ω link or a transformer**,
and you can test both on one board spin. Specify 600 Ω:600 Ω line-level audio isolation transformers
and check LF response — a small core rolls off bass, which is the main quality cost. *Parts not yet
selected; verify availability and tier before committing.*

**(b) Isolated DC-DC on the USB input — correct in principle, disproportionate here.**
Isolating the power breaks the loop at source. But it must carry the system *and* the charge
current: ~200 mA at 3.3 V plus ~500 mA of charging at 4.2 V is roughly **2.8 W out, ~3.5 W in**. A
3–5 W isolated converter is around 20 × 20 mm and $15–25 — more than the rest of the power section,
and a switching supply on an audio board. Against two transformers at a few dollars, it loses.

**(c) Charge when you are not listening — free, and worth stating.**
Unplug USB to play, plug in to charge. Zero parts. Given the battery is now in scope and runtime is
4–15 hours depending on cell (§6), this may cover the real usage pattern entirely. **Treat (a) as
the engineered answer and (c) as the one that might make it unnecessary** — provisioning the
transformer footprints costs nothing if you never fit them.

**Do not** rely on the charger alone. A power-path IC manages *sources*; it does not isolate
*grounds*.

## 1. Before the circuit: what is the battery actually for?

This changes the design more than any component choice, so it's worth pinning down first. Three plausible motivations, and they don't lead to the same board:

| # | Purpose | Energy needed | Implied design |
|---|---|---|---|
| **A** | **Retain state across ignition-off** — keep pairing, settings, volume; avoid a cold re-pair every trip | Tiny (µWh–mWh) | A supercapacitor or a small cell, with the ESP32 in deep sleep. No power-path complexity. |
| **B** | **Break the ground loop** — run the audio path on battery so the board is galvanically floating relative to chassis ground | Full operating load, for a drive's duration | Real cell (≥1000 mAh), power-path charging, proper regulation |
| **C** | **Portable use away from the car** — a general-purpose Bluetooth receiver | Full load, hours | Same as B, plus a bigger cell and a power switch |

**The one I'd draw your attention to is B**, because it isn't just a feature — it's a *solution to a problem you already have.*

[Design review §3.5(a)](design-review-v1.md) flagged automotive ground loop (alternator whine) as the classic failure mode for this product, currently unaddressed. The mechanism is that the board bonds chassis ground (via the cigarette-lighter USB charger) to the head unit's audio ground (via the AUX sleeve). **If the board runs on battery with USB physically disconnected, that bond doesn't exist and the loop is broken** — no isolation transformers, no isolated DC-DC, no filtering. The battery *is* the isolation.

That reframes the feature from "nice to have" to "candidate fix for REQ-AUD-05." It also implies a usage model worth designing around: **play on battery, charge when idle or when audio isn't in use.** Worth deciding whether that's acceptable ergonomically, because if it is, it's the cheapest ground-loop fix available.

> **Recommendation:** design for **B/C** (they're electrically the same board), and treat A as a free side-effect. Below assumes that.

---

## 2. The gating issue: lithium in a parked car

I want to put this before the circuit design, because it can change the answer.

**Typical lithium-ion (LCO/NMC pouch or 18650) temperature limits:**

| Condition | Typical limit | Car interior reality |
|---|---|---|
| **Charging** | 0 °C to **45 °C** | Summer cabin air 60–70 °C; dash surfaces higher |
| Discharging | −20 °C to 60 °C | Marginal in summer |
| Storage | Degrades rapidly above 60 °C | Routinely exceeded |

Charging a Li-ion cell above ~45 °C causes lithium plating — permanent capacity loss and a real fire/venting risk. Storing a pouch cell at 60 °C+ causes swelling and eventual venting. **Swollen cells from cars left in the sun are a common, well-documented failure**, not a theoretical edge case.

The requirements document has no operating temperature range at all — [review §3.5(e)](design-review-v1.md) proposed **REQ-ENV-01** for exactly this reason, and adding a battery makes it *mandatory* rather than good practice.

**Three honest ways forward:**

1. **NTC thermistor + charger with temperature qualification (non-negotiable).** The BQ24074 has a `TS` pin for this; charging is inhibited outside the safe window. **This solves charging safety but does nothing about storage** — a cell sitting at 70 °C for a summer afternoon degrades whether or not you're charging it.
2. **Removable cell / removable device.** Practical for a hobby build: JST-PH connector, and you take the unit (or at least the cell) out of the car when parked in summer. This is the pragmatic answer, and it's honest about the limitation rather than engineering around it.
3. **LiFePO₄ (LFP) instead.** Substantially safer chemistry — thermal runaway onset around 270 °C vs ~150 °C for LCO/NMC, no oxygen release, better high-temp tolerance. **But it doesn't suit this board electrically:** LFP is 3.2 V nominal (2.5–3.65 V), which is *below* your 3.3 V rail for most of its discharge curve, forcing a boost converter — a switching supply on an audio board, which is what the design deliberately avoided. It also needs a different charger (3.65 V termination, not 4.2 V).

**My recommendation:** standard Li-ion with **NTC temperature qualification (mandatory)** plus a **removable cell**, and write the "don't leave it baking in the car" constraint into REQ-ENV-01 explicitly rather than pretending the circuit solves it. If the device must live permanently in a hot car, I'd push back on lithium altogether and go with option A (supercapacitor, state retention only).

---

## 3. Recommended architecture

```
                        ┌──────────────────────────────────────┐
  USB-C VBUS (5 V) ────▶│  BQ24074  power-path charger         │
                        │  • OUT regulated, never exceeds 4.4V │
                        │  • DPPM: system load has priority    │
                        │  • TS pin → NTC temperature qual.    │
                        │  • ILIM / ISET set by resistors      │
                        └───┬──────────────────────────┬───────┘
                            │ OUT (SYS: 3.0 – 4.4 V)   │ BAT
                            │                          ▼
                            │                   JST-PH 2-pin
                            │                   Li-ion cell (protected)
                            │                   + 10 k NTC bonded to cell
                            │
              ┌─────────────┴──────────────┐
              ▼                            ▼
    ┌───────────────────┐       ┌────────────────────┐
    │ LDO → 3V3_DIG     │       │ LDO → 3V3_ANA      │
    │ ESP32, flash,     │       │ ES8388 only        │
    │ CH340K            │       │ (see review 3.1(c))│
    └───────────────────┘       └────────────────────┘

    VBAT ──[1 M / 1 M divider]──▶ ESP32 ADC1 (GPIO36/37/38/39/34 all free)
```

### 3.1 Why linear regulation, not a buck-boost

The obvious objection to LDOs on a battery is wasted capacity — but the numbers don't support it as strongly as intuition suggests.

A Li-ion cell spends most of its discharge above 3.5 V. Approximate capacity distribution at moderate load:

| Cell voltage band | Share of capacity |
|---|---|
| 4.2 → 3.9 V | ~20 % |
| 3.9 → 3.7 V | ~40 % |
| 3.7 → 3.6 V | ~15 % |
| 3.6 → 3.5 V | ~10 % |
| 3.5 → 3.0 V | ~15 % |

With a genuine LDO (≈250 mV dropout at 200 mA), you need ~3.55 V input for a 3.3 V output — so you use roughly **82–85 % of the cell** before cutoff.

A buck-boost recovers that last ~15–18 % and runs ~90 % efficient, netting maybe **25–30 % more runtime**. In exchange it puts a switching converter on a board whose entire power architecture was deliberately chosen to be linear because [this is a mixed-signal audio device](design-review-v1.md#31-power-subsystem) — and you'd very likely add a post-LDO for the codec anyway, giving back part of the efficiency.

**For 25–30 % more runtime, on a device that is mains-powered most of the time, that's a bad trade.** Recommend LDO. If runtime later proves insufficient, a bigger cell is the cheaper, quieter fix than a buck-boost.

### 3.2 A useful side-effect: the hot-car thermal problem gets better

[Review §3.1(a)](design-review-v1.md) flagged that U7 has tighter thermal margin than v1.1 claimed, because a car interior can hit 70 °C ambient. The BQ24074 **regulates its OUT pin to never exceed 4.4 V**, so the downstream LDO drops 1.1 V instead of the 1.7 V it currently drops from raw 5 V USB:

| | Dissipation @ 200 mA | Rise in SOT-223 (~80 °C/W) | Junction @ 70 °C ambient |
|---|---|---|---|
| Today (5 V → 3.3 V) | 0.34 W | ~28 °C | ~98 °C |
| With BQ24074 (4.4 V → 3.3 V) | **0.22 W** | ~18 °C | **~88 °C** |

**A 35 % reduction in regulator dissipation, for free.** The battery circuit makes the existing thermal problem better, not worse.

---

## 4. Part selection

### 4.1 Charger — BQ24074RGTR (TI)

| | |
|---|---|
| **LCSC** | C54313, **$1.19**, in stock |
| **JLCPCB PCBA tier** | ✅ **"Economic and Standard"** — QFN-16-EP (3×3 mm), 0.5 mm pitch, clears the 0.4 mm floor |
| **Why this part** | True power path (system runs from USB while the cell charges separately — not "load sharing" bodged onto a charge-only IC); OUT regulated ≤4.4 V so downstream regulators are safe; DPPM automatically throttles charge current to prioritise the system load; `TS` pin for the mandatory NTC; 10.5 V input OVP protects against a misbehaving car charger; no external compensation cap needed. |

**⚠️ Do not use the TP4056** — it's the default hobbyist choice ($0.07, everywhere) and it is the **wrong part here**. It has *no power path*. Connecting a load in parallel with the cell means the charger can't distinguish load current from charge current, so charge termination never triggers correctly, and the cell gets cycled continuously while the device runs. It's fine for a charge-only cradle; it is not fine for a device that runs while plugged in. Related alternatives worth a look only if BQ24074 becomes unavailable: **MCP73871** (power path, 1 A) — but the BQ24074 is dynamically stable without an extra cap and clamps OUT, which the MCP73871 doesn't.

**Support components:** `ISET` resistor (charge current), `ILIM` resistor (input current limit), `TS` NTC network, `/CHG` and `/PGOOD` status outputs (drive existing LEDs, or read on spare GPIOs).

### 4.2 The 3.3 V regulator must change — this is not optional

**The current NCP1117-3.3 cannot work on battery.** Its dropout is up to 1.2 V, so it needs ≥4.5 V input. On a cell at 3.8 V it would output ~2.6 V — the board simply won't run. Adding a battery *forces* this re-selection.

Requirements for the replacement:
- **Dropout ≤ 300 mV at 200 mA** (this is the whole point)
- **≥ 500 mA rated**
- **Package with real thermal capability** — SOT-223, SOT-89, or a DFN with an exposed pad. [Review §4.5](design-review-v1.md) established that shrinking to SOT-23-5 is thermally wrong for a hot car; that still applies, though the 4.4 V cap eases it.
- Good PSRR at audio frequencies, since one of these feeds the codec

Candidates to evaluate (verify stock + PCBA tier before committing, per requirements §2.3): **AP7361C-33** (SOT-223, 1 A, low dropout), **TLV75733P**, **RT9080-33**, **MIC5219-3.3**. I have not verified these against live stock — treat as a shortlist, not a selection.

### 4.3 Cell

| Option | Capacity | Notes |
|---|---|---|
| **LiPo pouch, 1000–2000 mAh** | 1000–2000 mAh | Compact, JST-PH 2-pin standard. **Must be a *protected* cell** (integrated PCM) or add protection. Mechanically fragile — never route traces or place components where the pouch could be punctured, and give it a retained pocket. |
| **18650 in a holder** | 2500–3500 mAh | More robust, replaceable, protected cells widely available, better thermal mass. Bulky. **My preference for a first build** — easier to handle safely and to swap out if you cook one. |

**Protection is mandatory either way.** Use a cell with an integrated protection module, or add one (DW01A + dual MOSFET is the cheap route; a BQ297xx is the better-engineered one). Over-discharge below ~2.5 V damages the cell and creates a hazard on the next charge. Do not rely on the ESP32 to enforce this in firmware.

**NTC:** a 10 kΩ B=3435 thermistor **bonded to the cell body** (not just sitting on the PCB — it has to sense cell temperature, not board temperature) into the BQ24074 `TS` pin.

### 4.4 State-of-charge monitoring

Two options, both cheap:

1. **Resistor divider → ESP32 ADC1.** From the netlist, ADC1 channels on GPIO36, 37, 38, 39, 34, 32 and 33 are **all unconnected** — seven free channels. Use a 1 MΩ/1 MΩ divider (2.1 µA standby drain, negligible) to bring 4.2 V max down to 2.1 V, inside ADC1's range with 11 dB attenuation. **Important:** use ADC**1**, not ADC2 — ADC2 is unusable while the radio is active, which for this device is always. Accuracy is mediocre (ESP32 ADC needs calibration and is non-linear) but adequate for a 4-bar indicator.
2. **MAX17048 fuel gauge** on the **existing I²C bus** — no new bus, one small part, proper coulomb-free ModelGauge SoC estimation. Better data for perhaps $1.

Recommend starting with (1) since it costs two resistors and the pins are already free.

### 4.5 Power switching / standby

If the cell stays connected with the car off, standby drain matters. Options:
- **ESP32 deep sleep** (~10 µA) woken by a button — elegant, but see §5 for a consequence.
- **Hard load switch / latching power button** — simplest and guarantees zero drain.
- BQ24074's own low-power mode handles the charger side.

---

## 5. Knock-on effect: deep sleep re-opens the CAP2 question

Worth flagging because it's exactly the kind of coupling that gets missed.

[Review §3.3(a)](design-review-v1.md) concluded that the ESP32's `CAP2` RC network (3.3 nF ∥ 20 kΩ) could be **deliberately omitted**, because Espressif states it only matters when entering deep sleep — and a permanently car-powered adapter never sleeps.

**A battery changes that premise.** If standby drain is managed via deep sleep (§4.5), the CAP2 network becomes relevant again: without it, the internal rail transition on sleep entry takes longer and deep-sleep current is higher — which is precisely the thing you added the network to optimise.

**Decision rule:** if you implement deep sleep, populate the CAP2 RC. If you use a hard power switch instead, leave it off. Either way `CAP1`'s 10 nF remains **required** regardless — that finding is unconditional.

---

## 6. Runtime and charge time

**Load budget** (at 3.3 V, streaming A2DP — *estimated*, needs bench measurement):

| Load | Current |
|---|---|
| ESP32, Bluetooth Classic A2DP streaming (average) | ~130 mA |
| ES8388 at 3.3 V | ~18 mA |
| CH340K (idle, USB absent) | ~10 mA |
| SPI flash (mostly idle) | ~5 mA |
| 2× status LEDs at *corrected* brightness (~4 mA each) | ~8 mA |
| **Total** | **≈171 mA** |

> Note the LEDs: at the current 1 kΩ they draw almost nothing because they're barely lit ([review §3.5(d)](design-review-v1.md)). Fixing brightness to ~330 Ω makes them a real ~5 % of the battery budget. On battery, PWM-dim them or light them only on events.

**Runtime** (LDO path, ~83 % of capacity usable):

| Cell | Runtime |
|---|---|
| 1000 mAh LiPo | **≈ 4.8 h** |
| 2000 mAh LiPo | **≈ 9.7 h** |
| 3000 mAh 18650 | **≈ 14.5 h** |

Even the smallest option comfortably covers a drive, which is what use case B needs.

**Charging.** Your USB-C port presents only 5.1 kΩ CC pulldowns, which requests *default* USB current — you cannot assume more than 500 mA without BC1.2 detection or CC negotiation. Budget accordingly: with `ILIM` set to 500 mA and the system drawing ~171 mA, DPPM leaves roughly 330 mA for charging → a 1000 mAh cell recharges in about **3–4 hours**. Acceptable for overnight or multi-trip charging. If you want faster, that's a separate conversation about advertising a higher current on CC.

---

## 7. Impact on the existing design

| Change | Detail |
|---|---|
| **Add** | BQ24074 + ISET/ILIM/TS resistors, JST-PH connector, NTC, VBAT divider, input/output caps |
| **Change** | **NCP1117 → a true LDO** (§4.2) — forced, not optional |
| **Possibly add** | Second LDO for the codec (already recommended independently in [review §3.1(c)](design-review-v1.md) — the battery work is a natural time to do it) |
| **Possibly add** | Load switch / power button |
| **Conditional** | CAP2 RC network, if deep sleep is used (§5) |
| **BOM lines** | roughly **+6 to +9** |

**Cost impact.** Under the Economic-tier plan (see chat), per-part feeder fees largely go away, so the added cost is mostly component cost: BQ24074 $1.19 + LDO ~$0.30 + passives/connector ~$0.50 ≈ **$2 per board**, plus the cell. That's a very reasonable price for both a genuine feature *and* a candidate fix for the ground-loop requirement.

**Manufacturability.** ✅ Verified: BQ24074 is **"Economic and Standard"** on JLCPCB, so the battery circuit does **not** jeopardise the Economic-tier plan.

---

## 8. Proposed requirements

| ID | Requirement |
|---|---|
| **REQ-PWR-06** | Device shall operate from an internal rechargeable lithium cell for ≥4 hours of continuous A2DP playback. |
| **REQ-PWR-07** | Device shall charge the cell from USB while simultaneously powering the system (power-path), with system load taking priority over charge current. |
| **REQ-PWR-08** | Charging shall be inhibited outside the cell's safe temperature window, enforced in hardware by an NTC bonded to the cell — **not** in firmware. |
| **REQ-PWR-09** | The cell shall have over-charge, over-discharge and over-current protection independent of the ESP32. |
| **REQ-PWR-10** | Device shall report state of charge to firmware. |
| **REQ-ENV-01** *(revised)* | Must now explicitly state the lithium storage constraint — see §2. The cell shall be removable, and documentation shall state it must not be stored in a vehicle in high ambient temperature. |
| **REQ-AUD-05** *(amended)* | Add battery operation as an accepted mitigation path for ground-loop noise — see §1. |

---

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Lithium cell in a hot parked car** | **High — safety** | NTC charge qualification (mandatory), removable cell, explicit documented constraint. Reconsider chemistry or drop to a supercapacitor if the device must live in the car. §2 |
| Regulator re-selection missed → board won't run on battery | High | NCP1117's 1.2 V dropout is fatal here. Called out explicitly in §4.2. |
| TP4056 substituted for cost | Medium | No power path — cell cycles continuously while running. §4.1 |
| Switching noise if buck-boost is chosen later | Medium | Prefer LDO (§3.1); if a buck-boost becomes necessary, keep the codec behind its own LDO. |
| Charge current starves the system on a weak charger | Low | BQ24074 DPPM handles this automatically. |
| Standby drain flattens the cell between uses | Medium | Hard load switch, or deep sleep + CAP2 network (§5). |

---

## 10. Open questions for you

1. **Which use case — A, B, or C?** (§1) If B, the battery becomes a candidate answer to REQ-AUD-05 and I'd re-scope the ground-loop work around it.
2. **Will the device live permanently in the car?** This is the safety gate (§2) and it may change the recommendation away from lithium entirely.
3. **Pouch cell or 18650?** I lean 18650-in-a-holder for a first build — more robust, replaceable, easier to handle safely.
4. **Deep sleep or hard power switch?** Determines whether the CAP2 network gets populated (§5).
