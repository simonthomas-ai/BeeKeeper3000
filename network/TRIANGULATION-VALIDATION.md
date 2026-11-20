# Bearing triangulation: uncertainty and validation

The numerical solver returns a **search hypothesis**, never a verified nest location.

## Measurement contract

Each bearing is associated with a unique station ID, station coordinate, azimuth clockwise from true north, calibrated one-standard-deviation angular uncertainty in degrees, and a timezone-aware observation timestamp.

- Azimuth must be finite and in the range 0 to less than 360 degrees.
- Angular uncertainty must be finite and in the range 0.5 to 45 degrees.
- At least three independent station IDs are required.
- The default maximum observation-time difference is 30 minutes.
- All stations must lie within a local projection area (default maximum dimension 30 km).
- Every accepted estimate must be in front of each inlier station's measured bearing ray.
- Poor crossing geometry and non-finite or unbounded covariance fail closed.

The uncertainty parameter is not a generic confidence score. It must be calibrated for the whole sensor chain: camera/optics alignment, compass or encoder error, installation orientation, tripod/mount movement, magnetic declination correction (where applicable), operator alignment and timestamp uncertainty.

## Estimator

The implementation projects stations into a local east/north tangent approximation. It initializes from the weighted intersection of bearing lines, then minimizes wrapped angular residuals by iterative weighted least squares with a Huber influence function.

For station i, with estimated target displacement (dx,dy) in local east/north metres, predicted azimuth is:

- theta_hat_i = atan2(dx, dy)
- residual_i = wrap(theta_hat_i - observed_azimuth_i)
- weight_i = 1 / sigma_i^2, where sigma_i is in radians

The Jacobian is evaluated in local metres. Unlike weighting a metre residual by angular sigma alone, this makes a fixed angular error correctly imply a larger cross-track uncertainty for a more distant station.

A bounded outlier pass can reject up to the configured number of observations whose normalized angular residual exceeds the threshold. The default is at most one outlier at five sigma. This is deliberately conservative: with only three observations, no observation may be removed by default because at least three must remain. If more errors are present than the configured allowance, the solver fails closed.

## 95% uncertainty ellipse

The reported major/minor axes and bearing are derived from the inverse local Fisher information matrix, using the calibrated angular standard deviations and a two-dimensional 95% chi-square factor. The result is a local linearized Gaussian approximation.

It does **not** account automatically for:
- systematic compass/optical calibration bias shared by several stations,
- correlated measurements or shared installation errors,
- non-Gaussian bearing errors, multipath or moving targets,
- uncertainty in the station coordinates or map datum,
- terrain/obstruction effects and refraction,
- selection bias from manually choosing observations.

The ellipse must therefore be treated as a statistical approximation, not a certified containment boundary. Operators should compare it with known surveyed targets and use wider operational search buffers until field validation establishes an empirical error model.

## Validation gates

Before operational field use:
1. Calibrate each station against a surveyed target at several azimuths and distances.
2. Record calibration date, device/mount identifier, reference direction and measured angular error distribution.
3. Verify station coordinates against an authoritative GNSS/survey source.
4. Run at least 30 known-target trials across the intended operating range and geometry; include adverse geometry and deliberately perturbed bearings.
5. Compare predicted 95% ellipses with observed target errors. If coverage is below 95%, recalibrate or inflate the model empirically and document the method.
6. Validate synchronization and maximum observation window under real station clocks.
7. Test separately on each deployment geography; the local projection recommendation is not a nationwide projection.

No field calibration or real-world validation is implied by the unit tests. GeoJSON display and nest confirmation are separate workflow stages. A competent person must validate any candidate location before any nest intervention.
