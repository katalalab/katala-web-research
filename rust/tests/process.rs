use kwr::process::{OfflineRunner, ProcessRunner, ProcessStep};
#[test]
fn strict_runner_cannot_hide_mismatch_or_unused_steps() {
    let mut runner = OfflineRunner::new(vec![ProcessStep::Available {
        program: "gh".into(),
        found: false,
    }]);
    assert!(runner.available("op").is_err());
    assert!(runner.finish().is_err());
    assert!(
        OfflineRunner::new(vec![ProcessStep::Available {
            program: "gh".into(),
            found: false
        }])
        .finish()
        .is_err()
    );
}
