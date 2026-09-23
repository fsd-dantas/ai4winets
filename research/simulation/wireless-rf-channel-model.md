# Wireless RF, antenna and channel model

**Status: normative methodology.** [Framework](README.md)

This document defines the RF and channel abstractions a study declares whenever it makes claims involving
coverage, SINR, interference, throughput, error rate, radio resource allocation, handover, link reliability or
radio energy use. A study whose radio behaviour is out of scope declares the classes here `out_of_scope` once,
with the claims that rules out.

## Modelling hierarchy

RF modelling distinguishes the following phenomena. They are not silently merged into one unexplained loss
term:

1. Geometry and visibility
2. Antenna and radio front-end properties
3. Large-scale path loss
4. Shadow fading
5. Small-scale fading and multipath
6. Doppler and time, frequency and spatial selectivity
7. Thermal noise and receiver impairments
8. Co-channel and adjacent-channel interference
9. PHY abstraction, error-rate mapping, retransmission and link adaptation

## Link budget

The received-power abstraction states:

$$
P_{\mathrm{rx}}[\mathrm{dBm}] = P_{\mathrm{tx}}[\mathrm{dBm}] + G_{\mathrm{tx}}[\mathrm{dBi}]
+ G_{\mathrm{rx}}[\mathrm{dBi}] - L_{\mathrm{path}}[\mathrm{dB}] - L_{\mathrm{misc}}[\mathrm{dB}].
$$

$L_{\mathrm{misc}}$ is decomposed wherever relevant: feeder and cable loss, penetration loss, body loss,
polarisation mismatch, implementation loss and scenario-specific margins. An impairment injected as extra loss
is declared as such, with what it stands for.

## Free-space baseline

The Friis equation is an analytical baseline for unobstructed far-field propagation:

$$
P_{\mathrm{rx}} = P_{\mathrm{tx}} G_{\mathrm{tx}} G_{\mathrm{rx}} \left(\frac{\lambda}{4\pi d}\right)^2,
$$

with the equivalent free-space path loss

$$
L_{\mathrm{FSPL}}[\mathrm{dB}] = 32.44 + 20\log_{10}(f_{\mathrm{MHz}}) + 20\log_{10}(d_{\mathrm{km}}).
$$

Friis is not an implicit universal propagation model. It applies where conditions reasonably approximate clear
free-space far-field propagation, and serves as a sanity-check baseline, a controlled line-of-sight reference,
or the reference loss at a close-in distance. A study that uses it outside those conditions declares it
`abstracted` and states which claims it cannot support.

## RF declaration

A scenario making radio claims declares at least (values illustrative):

```json
{
  "rf_channel_model": {
    "carrier_frequency_hz": 900000000,
    "bandwidth_hz": 10000000,
    "duplexing": "FDD",
    "tx_power_definition": "conducted_power",
    "tx_power_dbm": 23,
    "antenna": {
      "tx_gain_dbi": 0,
      "rx_gain_dbi": 0,
      "pattern": "omnidirectional_or_reference",
      "polarization": "vertical",
      "height_m": 10
    },
    "large_scale_path_loss": {
      "model": "log_distance_or_standard_model",
      "parameter_source": "measurement_standard_or_justified_assumption"
    },
    "shadowing": {
      "enabled": true,
      "std_db": 6,
      "spatial_correlation_distance_m": 50,
      "cross_link_correlation": "declared"
    },
    "small_scale_fading": {
      "model": "rayleigh_rician_nakagami_or_geometry_based",
      "time_correlation": "declared"
    },
    "noise_and_receiver": {
      "noise_figure_db": 5,
      "implementation_loss_db": 0,
      "receiver_sensitivity_dbm": null
    },
    "interference": {
      "cochannel": true,
      "adjacent_channel": false,
      "external_world_source": "world_model"
    },
    "phy_abstraction": {
      "type": "waveform_or_link_to_system_mapping",
      "bler_mapping": "declared",
      "harq": "declared",
      "cqi_delay_ms": null
    }
  }
}
```

## Large-scale propagation options

A scenario selects and justifies one or more of:

- free-space (Friis) baseline;
- log-distance model;
- dual-slope or multi-slope log-distance model;
- two-ray ground reflection;
- terrain- and clutter-aware empirical model;
- site-general or indoor empirical model;
- 3GPP geometry-based stochastic channel model [3GPP TR 38.901];
- deterministic or hybrid ray tracing, or a dominant-path model;
- measurement-calibrated radio map.

For a log-distance model:

$$
PL(d) = PL(d_0) + 10\,n \log_{10}\!\left(\frac{d}{d_0}\right) + X_\sigma,
$$

where $n$ is the path-loss exponent and $X_\sigma$ a shadow-fading term. Report $d_0$, the reference loss, $n$,
the shadowing distribution and the parameter source. Simulator model libraries document the assumptions of
their implementations [ns-3 propagation]; a study cites the one it runs.

## Antennas and MIMO

Declare, where applicable:

- conducted power, EIRP, regulatory constraints and the power-control rule;
- azimuth and elevation pattern, downtilt, sidelobes and polarisation;
- array geometry and element count;
- SISO, SIMO, MISO, SU-MIMO or MU-MIMO regime;
- beamforming method, codebook, training and tracking overhead, alignment error;
- CSI availability, delay, quantisation and ageing;
- spatial correlation, channel rank, and pilot and estimation assumptions.

## Channel dynamics

Where mobility, latency, beam management or prediction are material, declare:

- LOS/NLOS and blockage state transitions;
- delay spread, power-delay profile and frequency selectivity;
- angular spread and spatial consistency;
- relative velocity and Doppler behaviour;
- coherence time and the channel-update policy;
- correlation across time, frequency, nearby users and links.

Doppler may be approximated by $f_D = \dfrac{v}{\lambda}\cos\theta$.

## Noise and interference

Thermal noise is consistent with bandwidth and receiver noise figure:

$$
N[\mathrm{dBm}] = -174 + 10\log_{10}(B[\mathrm{Hz}]) + NF[\mathrm{dB}].
$$

The receiver model states whether performance depends on SNR, SINR, SINR with implementation loss or another
metric:

$$
\mathrm{SINR} = \frac{P_s}{N + \sum_{i=1}^{K} P_{I,i}}.
$$

Interference assumptions state, as relevant:

- co-channel and inter-cell interference;
- adjacent-channel leakage and selectivity;
- hidden and exposed terminals;
- cross-tier and cross-RAT interference;
- time correlation from scheduling, load and retransmission;
- coordination, cancellation or avoidance;
- external interference from the [spatial world model](spatial-world-model.md).

A surrogate for interference, such as an adjacency or conflict graph, is declared `abstracted`, with what it
omits: SINR dependence, partial overlap and nonplanar conflict structure.

## PHY and link-to-system abstraction

A scenario states whether it uses:

- explicit waveform or baseband simulation;
- packet-level PHY with a threshold model;
- link-to-system mapping, such as effective SINR to BLER curves;
- trace-driven error or performance tables.

A reduced PHY model reports its calibration source, operating range, MCS set, CQI and reporting delay, HARQ
configuration, retransmission cap, and the conditions outside which the mapping is not claimed valid.

## Minimum validation checks

- Compare free-space and link-budget sanity checks with analytical calculations.
- Check the selected channel or path-loss behaviour against the standard, measurement or literature source of
  its parameters.
- Confirm that noise floor, receiver sensitivity and bandwidth units are consistent.
- Verify that interference changes when spatial load, transmit power or the guard or external population
  changes.
- Test limiting cases: no fading, no interference, static user, ideal CSI and zero offered load.

## References

- 3GPP TR 38.901, *Study on channel model for frequencies from 0.5 to 100 GHz* (`3gpp38901` in
  [references.bib](../../literature/references.bib)).
- ns-3 *Propagation* model library documentation (`ns3propagation` in
  [references.bib](../../literature/references.bib)).
