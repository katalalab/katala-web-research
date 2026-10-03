//! Bounded native child execution and strict offline process transcripts.
//! Arguments/output are never included in error text. No shell is invoked.
use crate::providers::{ProviderError, ProviderResult};
use std::{collections::VecDeque, path::PathBuf};

pub const OUTPUT_LIMIT: usize = 8 * 1024 * 1024;
#[derive(Clone, PartialEq, Eq)]
pub struct ProcessRequest {
    pub program: String,
    pub args: Vec<String>,
    pub timeout_ms: u64,
    pub output_limit: usize,
}
pub struct ProcessOutput {
    pub return_code: i32,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
}
pub trait ProcessRunner {
    fn available(&mut self, program: &str) -> ProviderResult<bool>;
    fn run(&mut self, request: &ProcessRequest) -> ProviderResult<ProcessOutput>;
}
pub enum ProcessStep {
    Available {
        program: String,
        found: bool,
    },
    Run {
        request: ProcessRequest,
        outcome: ProviderResult<ProcessOutput>,
    },
}
pub struct OfflineRunner {
    steps: VecDeque<ProcessStep>,
    pub calls: usize,
    failed: bool,
}
impl OfflineRunner {
    pub fn new(steps: Vec<ProcessStep>) -> Self {
        Self {
            steps: steps.into(),
            calls: 0,
            failed: false,
        }
    }
    fn unexpected(&mut self) -> ProviderError {
        self.failed = true;
        ProviderError::synthetic("FixtureError")
    }
    pub fn finish(self) -> ProviderResult<()> {
        if self.steps.is_empty() && !self.failed {
            Ok(())
        } else {
            Err(ProviderError::synthetic("FixtureError"))
        }
    }
}
impl ProcessRunner for OfflineRunner {
    fn available(&mut self, program: &str) -> ProviderResult<bool> {
        self.calls += 1;
        match self.steps.pop_front() {
            Some(ProcessStep::Available {
                program: expected,
                found,
            }) if expected == program => Ok(found),
            _ => Err(self.unexpected()),
        }
    }
    fn run(&mut self, request: &ProcessRequest) -> ProviderResult<ProcessOutput> {
        self.calls += 1;
        match self.steps.pop_front() {
            Some(ProcessStep::Run {
                request: expected,
                outcome,
            }) if expected == *request => outcome,
            _ => Err(self.unexpected()),
        }
    }
}
pub struct NativeRunner;
fn executable(program: &str) -> Option<PathBuf> {
    let path = std::path::Path::new(program);
    let candidates = if path.components().count() > 1 {
        vec![path.to_path_buf()]
    } else {
        std::env::var_os("PATH")
            .map(|paths| {
                std::env::split_paths(&paths)
                    .map(|p| p.join(program))
                    .collect()
            })
            .unwrap_or_default()
    };
    candidates.into_iter().find(|p| {
        p.metadata().is_ok_and(|m| {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                m.is_file() && m.permissions().mode() & 0o111 != 0
            }
            #[cfg(not(unix))]
            {
                m.is_file()
            }
        })
    })
}
impl ProcessRunner for NativeRunner {
    fn available(&mut self, program: &str) -> ProviderResult<bool> {
        Ok(executable(program).is_some())
    }
    fn run(&mut self, request: &ProcessRequest) -> ProviderResult<ProcessOutput> {
        #[cfg(unix)]
        {
            native_unix::run(request)
        }
        #[cfg(not(unix))]
        {
            let _ = request;
            Err(ProviderError::synthetic("NotImplementedError"))
        }
    }
}
#[cfg(unix)]
mod native_unix {
    use super::*;
    use std::{
        io::Read,
        os::unix::process::{CommandExt, ExitStatusExt},
        process::{Child, Command, Stdio},
        sync::{
            Arc, Mutex,
            atomic::{AtomicI32, AtomicUsize, Ordering},
            mpsc,
        },
        thread,
        time::{Duration, Instant},
    };
    static INTERRUPTED: AtomicI32 = AtomicI32::new(0);
    struct SignalState {
        users: usize,
        previous: Option<(libc::sigaction, libc::sigaction)>,
    }
    static SIGNALS: Mutex<SignalState> = Mutex::new(SignalState {
        users: 0,
        previous: None,
    });
    extern "C" fn receive_signal(signal: libc::c_int) {
        // Only a lock-free atomic store runs in signal context.
        INTERRUPTED.store(signal, Ordering::Relaxed);
    }
    struct SignalScope;
    impl SignalScope {
        fn enter() -> ProviderResult<Self> {
            let mut state = SIGNALS
                .lock()
                .map_err(|_| ProviderError::synthetic("OSError"))?;
            if state.users == 0 {
                INTERRUPTED.store(0, Ordering::Relaxed);
                // All-zero sigaction storage plus sigemptyset is a valid C action.
                // Preserve both previous actions and restore them when the last run exits.
                unsafe {
                    let mut action: libc::sigaction = std::mem::zeroed();
                    libc::sigemptyset(&mut action.sa_mask);
                    action.sa_sigaction = receive_signal as *const () as usize;
                    let mut previous_int = std::mem::zeroed();
                    let mut previous_term = std::mem::zeroed();
                    if libc::sigaction(libc::SIGINT, &action, &mut previous_int) != 0 {
                        return Err(ProviderError::synthetic("OSError"));
                    }
                    if libc::sigaction(libc::SIGTERM, &action, &mut previous_term) != 0 {
                        libc::sigaction(libc::SIGINT, &previous_int, std::ptr::null_mut());
                        return Err(ProviderError::synthetic("OSError"));
                    }
                    state.previous = Some((previous_int, previous_term));
                }
            }
            state.users += 1;
            Ok(Self)
        }
    }
    impl Drop for SignalScope {
        fn drop(&mut self) {
            if let Ok(mut state) = SIGNALS.lock() {
                state.users -= 1;
                if state.users == 0 {
                    if let Some((previous_int, previous_term)) = state.previous.take() {
                        // These actions were obtained from sigaction during this scope.
                        unsafe {
                            libc::sigaction(libc::SIGINT, &previous_int, std::ptr::null_mut());
                            libc::sigaction(libc::SIGTERM, &previous_term, std::ptr::null_mut());
                        }
                    }
                    INTERRUPTED.store(0, Ordering::Relaxed);
                }
            }
        }
    }
    struct OwnedChild(Child);
    impl Drop for OwnedChild {
        fn drop(&mut self) {
            if let Ok(pid) = i32::try_from(self.0.id()) {
                // This child was created in its own process group (PGID = PID).
                // A negative owned PGID targets only its descendants, never our group.
                unsafe {
                    libc::kill(-pid, libc::SIGKILL);
                }
            }
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    fn io_error(error: std::io::Error) -> ProviderError {
        let kind = match error.kind() {
            std::io::ErrorKind::NotFound => "FileNotFoundError",
            std::io::ErrorKind::PermissionDenied => "PermissionError",
            _ => "OSError",
        };
        ProviderError::synthetic(kind)
    }
    pub fn run(request: &ProcessRequest) -> ProviderResult<ProcessOutput> {
        run_observed(request, |_| {})
    }
    fn run_observed(
        request: &ProcessRequest,
        mut after_poll: impl FnMut(bool),
    ) -> ProviderResult<ProcessOutput> {
        let started = Instant::now();
        let _signals = SignalScope::enter()?;
        let mut child = OwnedChild(
            Command::new(&request.program)
                .args(&request.args)
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .process_group(0)
                .spawn()
                .map_err(io_error)?,
        );
        let stdout = child.0.stdout.take().unwrap();
        let stderr = child.0.stderr.take().unwrap();
        let used = Arc::new(AtomicUsize::new(0));
        let (tx, rx) = mpsc::channel();
        for (index, mut pipe) in [
            (0, Box::new(stdout) as Box<dyn Read + Send>),
            (1, Box::new(stderr) as Box<dyn Read + Send>),
        ] {
            let tx = tx.clone();
            let used = used.clone();
            let limit = request.output_limit;
            thread::Builder::new()
                .spawn(move || {
                    let result = (|| {
                        let mut captured = Vec::new();
                        let mut buffer = [0; 8192];
                        loop {
                            let count = pipe.read(&mut buffer).map_err(io_error)?;
                            if count == 0 {
                                return Ok(captured);
                            }
                            let previous = used.fetch_add(count, Ordering::Relaxed);
                            if previous > limit || count > limit - previous {
                                return Err(ProviderError::synthetic("OutputLimitError"));
                            }
                            captured.extend_from_slice(&buffer[..count]);
                        }
                    })();
                    let _ = tx.send((index, result));
                })
                .map_err(io_error)?;
        }
        drop(tx);
        let mut stdout = None;
        let mut stderr = None;
        let mut reads = 0;
        let mut status = None;
        loop {
            match INTERRUPTED.load(Ordering::Relaxed) {
                libc::SIGINT => return Err(ProviderError::synthetic("KeyboardInterrupt")),
                libc::SIGTERM => return Err(ProviderError::synthetic("SignalError")),
                _ => {}
            }
            while let Ok((index, result)) = rx.try_recv() {
                let data = result?;
                reads += 1;
                if index == 0 {
                    stdout = Some(data);
                } else {
                    stderr = Some(data);
                }
            }
            if status.is_none() {
                status = child.0.try_wait().map_err(io_error)?;
            }
            after_poll(reads == 2 && status.as_ref().is_some_and(|s| s.success()));
            if started.elapsed() >= Duration::from_millis(request.timeout_ms) {
                return Err(ProviderError::synthetic("TimeoutExpired"));
            }
            if reads == 2
                && let Some(status) = status
            {
                return Ok(ProcessOutput {
                    return_code: status
                        .code()
                        .unwrap_or_else(|| -status.signal().unwrap_or(1)),
                    stdout: stdout.unwrap_or_default(),
                    stderr: stderr.unwrap_or_default(),
                });
            }
            thread::sleep(Duration::from_millis(2));
        }
    }
    #[cfg(test)]
    mod tests {
        use super::*;
        #[test]
        #[ignore = "owned child executable fixture; invoked explicitly by the boundary test"]
        fn empty_child() {}
        #[test]
        fn completed_streams_after_deadline_are_not_success() {
            let request = ProcessRequest {
                program: std::env::current_exe()
                    .unwrap()
                    .to_string_lossy()
                    .into_owned(),
                args: vec![
                    "--exact".into(),
                    "process::native_unix::tests::empty_child".into(),
                    "--ignored".into(),
                ],
                timeout_ms: 100,
                output_limit: OUTPUT_LIMIT,
            };
            let mut observed_ready = false;
            let outcome = run_observed(&request, |ready| {
                if ready && !observed_ready {
                    observed_ready = true;
                    thread::sleep(Duration::from_millis(120));
                }
            });
            assert!(
                observed_ready,
                "owned child did not reach the scheduled completion boundary"
            );
            assert_eq!(outcome.err().map(|e| e.kind), Some("TimeoutExpired"));
        }
    }
}
