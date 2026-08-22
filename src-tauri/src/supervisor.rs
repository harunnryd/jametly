use std::collections::VecDeque;
use std::process::ExitStatus;
use std::time::{Duration, Instant};

use ipc_proto::Event;
use serde_json::json;

pub const CRASH_EVENT: &str = "python.crash";
pub const RESTARTED_EVENT: &str = "python.restarted";
pub const NO_TRACEBACK: &str = "<no stderr captured>";

pub const TRACEBACK_MAX_BYTES: usize = 8 * 1024;
pub const TRACEBACK_MAX_LINES: usize = 64;

const MAX_BACKOFF_SHIFT: u32 = 16;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Death {
    Clean,
    Code(i32),
    Signal(i32),
    Unknown,
}

impl Death {
    pub fn is_crash(self) -> bool {
        !matches!(self, Death::Clean)
    }

    pub fn exit_code(self) -> Option<i32> {
        match self {
            Death::Clean => Some(0),
            Death::Code(code) => Some(code),
            Death::Signal(_) | Death::Unknown => None,
        }
    }

    pub fn signal(self) -> Option<i32> {
        match self {
            Death::Signal(signal) => Some(signal),
            _ => None,
        }
    }

    pub fn describe(self) -> String {
        match self {
            Death::Clean => "sidecar exited cleanly".to_string(),
            Death::Code(code) => format!("sidecar exited with exit code {code}"),
            Death::Signal(signal) => format!("sidecar was killed by signal {signal}"),
            Death::Unknown => "sidecar exited for an unknown reason".to_string(),
        }
    }
}

pub fn classify(status: ExitStatus) -> Death {
    if status.success() {
        return Death::Clean;
    }
    if let Some(code) = status.code() {
        return Death::Code(code);
    }
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        if let Some(signal) = status.signal() {
            return Death::Signal(signal);
        }
    }
    Death::Unknown
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RestartPolicy {
    pub base: Duration,
    pub cap: Duration,
    pub burst: usize,
    pub window: Duration,
    pub healthy_after: Duration,
}

impl Default for RestartPolicy {
    fn default() -> Self {
        Self {
            base: Duration::from_millis(500),
            cap: Duration::from_secs(30),
            burst: 5,
            window: Duration::from_secs(60),
            healthy_after: Duration::from_secs(10),
        }
    }
}

#[derive(Debug, Default)]
pub struct RestartState {
    attempts: u32,
    history: VecDeque<Instant>,
    gave_up: bool,
}

impl RestartState {
    pub fn attempts(&self) -> u32 {
        self.attempts
    }

    pub fn has_gave_up(&self) -> bool {
        self.gave_up
    }

    pub fn reset(&mut self) {
        self.attempts = 0;
        self.history.clear();
        self.gave_up = false;
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Decision {
    RestartAfter(Duration),
    GaveUp { attempts: u32 },
}

impl RestartPolicy {
    pub fn on_crash(&self, state: &mut RestartState, now: Instant, uptime: Duration) -> Decision {
        if state.gave_up {
            return Decision::GaveUp {
                attempts: state.attempts,
            };
        }

        if uptime >= self.healthy_after {
            state.attempts = 0;
            state.history.clear();
        }

        while state
            .history
            .front()
            .is_some_and(|stamp| now.duration_since(*stamp) >= self.window)
        {
            state.history.pop_front();
        }

        if state.history.len() >= self.burst {
            state.gave_up = true;
            return Decision::GaveUp {
                attempts: state.attempts,
            };
        }

        state.history.push_back(now);
        let shift = state.attempts.min(MAX_BACKOFF_SHIFT);
        let delay = self
            .base
            .saturating_mul(1u32 << shift)
            .min(self.cap);
        state.attempts += 1;
        Decision::RestartAfter(delay)
    }

    pub fn on_spawn_failure(&self, state: &mut RestartState, _now: Instant) -> Decision {
        state.gave_up = true;
        Decision::GaveUp {
            attempts: state.attempts,
        }
    }
}

#[derive(Debug)]
pub struct StderrTail {
    lines: VecDeque<String>,
    max_bytes: usize,
    max_lines: usize,
}

impl StderrTail {
    pub fn new(max_bytes: usize, max_lines: usize) -> Self {
        Self {
            lines: VecDeque::new(),
            max_bytes,
            max_lines,
        }
    }

    pub fn push(&mut self, line: &str) {
        let mut line = line.to_string();
        if line.len() > self.max_bytes {
            line.truncate(floor_char_boundary(&line, self.max_bytes));
        }
        self.lines.push_back(line);
        while self.lines.len() > self.max_lines {
            self.lines.pop_front();
        }
        while self.byte_len() > self.max_bytes && self.lines.len() > 1 {
            self.lines.pop_front();
        }
    }

    fn byte_len(&self) -> usize {
        let joined: usize = self.lines.iter().map(|line| line.len()).sum();
        joined + self.lines.len().saturating_sub(1)
    }

    pub fn render(&self) -> String {
        if self.lines.is_empty() {
            return NO_TRACEBACK.to_string();
        }
        let joined = self
            .lines
            .iter()
            .cloned()
            .collect::<Vec<_>>()
            .join("\n");
        if joined.len() <= self.max_bytes {
            return joined;
        }
        let start = joined.len() - self.max_bytes;
        joined[floor_char_boundary(&joined, start)..].to_string()
    }
}

impl Default for StderrTail {
    fn default() -> Self {
        Self::new(TRACEBACK_MAX_BYTES, TRACEBACK_MAX_LINES)
    }
}

fn floor_char_boundary(text: &str, index: usize) -> usize {
    let mut index = index.min(text.len());
    while index > 0 && !text.is_char_boundary(index) {
        index -= 1;
    }
    index
}

pub fn crash_event(death: Death, traceback: &str) -> Event {
    Event {
        method: CRASH_EVENT.to_string(),
        params: json!({
            "traceback": traceback,
            "exit_code": death.exit_code(),
            "signal": death.signal(),
        }),
    }
}

pub fn restarted_event(death: Death, pid: u32) -> Event {
    Event {
        method: RESTARTED_EVENT.to_string(),
        params: json!({
            "reason": death.describe(),
            "pid": pid,
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    const ZERO: Duration = Duration::ZERO;

    fn ms(n: u64) -> Duration {
        Duration::from_millis(n)
    }

    #[test]
    fn backoff_doubles_from_the_base_delay() {
        let policy = RestartPolicy::default();
        let mut state = RestartState::default();
        let now = Instant::now();

        assert_eq!(
            policy.on_crash(&mut state, now, ZERO),
            Decision::RestartAfter(ms(500))
        );
        assert_eq!(
            policy.on_crash(&mut state, now, ZERO),
            Decision::RestartAfter(ms(1000))
        );
        assert_eq!(
            policy.on_crash(&mut state, now, ZERO),
            Decision::RestartAfter(ms(2000))
        );
    }

    #[test]
    fn backoff_is_capped() {
        let policy = RestartPolicy {
            burst: 64,
            window: Duration::from_secs(86_400),
            ..RestartPolicy::default()
        };
        let mut state = RestartState::default();
        let now = Instant::now();

        let mut last = ZERO;
        for _ in 0..40 {
            match policy.on_crash(&mut state, now, ZERO) {
                Decision::RestartAfter(delay) => last = delay,
                Decision::GaveUp { .. } => panic!("budget should not be exhausted here"),
            }
        }
        assert_eq!(last, policy.cap);
    }

    #[test]
    fn budget_is_exhausted_after_the_burst_inside_the_window() {
        let policy = RestartPolicy::default();
        let mut state = RestartState::default();
        let now = Instant::now();

        for _ in 0..policy.burst {
            assert!(matches!(
                policy.on_crash(&mut state, now, ZERO),
                Decision::RestartAfter(_)
            ));
        }

        assert_eq!(
            policy.on_crash(&mut state, now, ZERO),
            Decision::GaveUp {
                attempts: policy.burst as u32
            }
        );
    }

    #[test]
    fn give_up_is_absorbing_once_reached() {
        let policy = RestartPolicy::default();
        let mut state = RestartState::default();
        let now = Instant::now();

        for _ in 0..policy.burst {
            policy.on_crash(&mut state, now, ZERO);
        }

        assert!(matches!(
            policy.on_crash(&mut state, now, ZERO),
            Decision::GaveUp { .. }
        ));
        assert!(matches!(
            policy.on_crash(&mut state, now, ZERO),
            Decision::GaveUp { .. }
        ));
    }

    #[test]
    fn a_slow_drip_of_crashes_never_exhausts_the_budget() {
        let policy = RestartPolicy::default();
        let mut state = RestartState::default();
        let mut now = Instant::now();

        for _ in 0..(policy.burst * 4) {
            assert!(matches!(
                policy.on_crash(&mut state, now, ZERO),
                Decision::RestartAfter(_)
            ));
            now += policy.window + ms(1);
        }
        assert!(!state.has_gave_up());
    }

    #[test]
    fn giving_up_survives_the_window_sliding_and_needs_a_manual_reset() {
        let policy = RestartPolicy::default();
        let mut state = RestartState::default();
        let start = Instant::now();

        for _ in 0..policy.burst {
            policy.on_crash(&mut state, start, ZERO);
        }
        assert!(matches!(
            policy.on_crash(&mut state, start, ZERO),
            Decision::GaveUp { .. }
        ));

        let later = start + policy.window * 10;
        assert!(matches!(
            policy.on_crash(&mut state, later, ZERO),
            Decision::GaveUp { .. }
        ));

        state.reset();
        assert!(matches!(
            policy.on_crash(&mut state, later, ZERO),
            Decision::RestartAfter(delay) if delay == policy.base
        ));
    }

    #[test]
    fn a_long_healthy_run_resets_the_backoff_and_the_budget() {
        let policy = RestartPolicy::default();
        let mut state = RestartState::default();
        let now = Instant::now();

        for _ in 0..3 {
            policy.on_crash(&mut state, now, ZERO);
        }

        assert_eq!(
            policy.on_crash(&mut state, now, policy.healthy_after),
            Decision::RestartAfter(policy.base)
        );
    }

    #[test]
    fn a_short_run_does_not_reset_the_backoff() {
        let policy = RestartPolicy::default();
        let mut state = RestartState::default();
        let now = Instant::now();

        policy.on_crash(&mut state, now, ZERO);
        assert_eq!(
            policy.on_crash(&mut state, now, policy.healthy_after - ms(1)),
            Decision::RestartAfter(ms(1000))
        );
    }

    #[test]
    fn a_missing_sidecar_binary_gives_up_without_spending_the_budget() {
        let policy = RestartPolicy::default();
        let mut state = RestartState::default();
        let now = Instant::now();

        assert_eq!(
            policy.on_spawn_failure(&mut state, now),
            Decision::GaveUp { attempts: 0 }
        );
    }

    #[test]
    fn a_clean_exit_is_not_a_crash() {
        assert!(!Death::Clean.is_crash());
        assert!(Death::Code(70).is_crash());
        assert!(Death::Signal(9).is_crash());
        assert!(Death::Unknown.is_crash());
    }

    #[test]
    fn death_reports_its_exit_code_only_when_it_has_one() {
        assert_eq!(Death::Code(70).exit_code(), Some(70));
        assert_eq!(Death::Clean.exit_code(), Some(0));
        assert_eq!(Death::Signal(9).exit_code(), None);
        assert_eq!(Death::Unknown.exit_code(), None);
    }

    #[test]
    fn stderr_tail_keeps_the_last_lines_within_the_byte_budget() {
        let mut tail = StderrTail::new(64, 3);
        for line in ["first", "second", "third", "fourth"] {
            tail.push(line);
        }

        let rendered = tail.render();
        assert!(!rendered.contains("first"));
        assert!(rendered.contains("fourth"));
        assert_eq!(rendered.lines().count(), 3);
    }

    #[test]
    fn stderr_tail_truncates_a_single_oversized_line() {
        let mut tail = StderrTail::new(16, 8);
        tail.push(&"x".repeat(1024));

        assert!(tail.render().len() <= 16);
    }

    #[test]
    fn an_empty_stderr_tail_renders_a_placeholder_not_an_empty_string() {
        let tail = StderrTail::new(64, 4);
        assert_eq!(tail.render(), NO_TRACEBACK);
    }

    #[test]
    fn crash_event_carries_a_bounded_traceback_and_the_exit_code() {
        let mut tail = StderrTail::new(256, 8);
        tail.push("Traceback (most recent call last):");
        tail.push("ZeroDivisionError: division by zero");

        let event = crash_event(Death::Code(1), &tail.render());

        assert_eq!(event.method, CRASH_EVENT);
        assert_eq!(event.params["exit_code"], serde_json::json!(1));
        let traceback = event.params["traceback"].as_str().expect("traceback string");
        assert!(traceback.contains("ZeroDivisionError"));
        assert!(traceback.len() <= 256);
    }

    #[test]
    fn crash_event_omits_the_exit_code_when_the_process_died_of_a_signal() {
        let event = crash_event(Death::Signal(9), NO_TRACEBACK);

        assert_eq!(event.params.get("exit_code"), Some(&serde_json::Value::Null));
        assert_eq!(event.params["signal"], serde_json::json!(9));
    }

    #[test]
    fn restarted_event_reports_the_new_process_identity_and_a_reason() {
        let event = restarted_event(Death::Code(1), 4242);

        assert_eq!(event.method, RESTARTED_EVENT);
        assert_eq!(event.params["pid"], serde_json::json!(4242));
        let reason = event.params["reason"].as_str().expect("reason string");
        assert!(reason.contains("exit code 1"));
    }

    #[test]
    fn restarted_event_reason_names_the_signal_when_there_was_one() {
        let event = restarted_event(Death::Signal(9), 7);
        let reason = event.params["reason"].as_str().expect("reason string");

        assert!(reason.contains("signal 9"));
    }
}
