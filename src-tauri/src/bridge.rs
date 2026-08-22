use std::collections::HashMap;
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use ipc_proto::{ErrorBody, ErrorCode, Event, Reply, ReplyErr, Request, WireMessage};
use thiserror::Error;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStderr, ChildStdout, Command};
use tokio::sync::{mpsc, oneshot, Mutex};
use tokio::task::JoinHandle;

use crate::supervisor::{classify, Death, StderrTail};

const SIDECAR_CMD: &str = "uv";
const SIDECAR_ARGS: &[&str] = &["run", "--project", "ai", "python", "-m", "jamly"];

/// Overflow policy once this many events are unread: drop the newest, count it, never block.
pub const EVENT_CHANNEL_CAPACITY: usize = 256;

pub const REAP_GRACE: std::time::Duration = std::time::Duration::from_secs(5);

type PendingReplies = Arc<Mutex<HashMap<String, oneshot::Sender<Reply>>>>;
type SharedTail = Arc<Mutex<StderrTail>>;

#[derive(Debug, Error)]
pub enum BridgeError {
    #[error("sidecar spawn failed: {0}")]
    Spawn(String),
    #[error("sidecar stdin write failed: {0}")]
    Write(String),
    #[error("sidecar reply parse failed: {0}")]
    Parse(#[from] serde_json::Error),
    #[error("sidecar stdout closed before replying to {0}")]
    Closed(String),
    #[error("sidecar crashed before replying to {id}: {death}")]
    Crashed { id: String, death: String },
    #[error("sidecar is stopped after repeated crashes; restart the engine to retry")]
    EngineStopped,
}

#[derive(Debug, Clone)]
pub struct SidecarCommand {
    pub program: String,
    pub args: Vec<String>,
    pub env: HashMap<String, String>,
    pub cwd: Option<std::path::PathBuf>,
}

impl SidecarCommand {
    pub fn with_env(env: HashMap<String, String>) -> Self {
        Self {
            env,
            ..Self::default()
        }
    }

    pub fn program(program: impl Into<String>, args: &[&str]) -> Self {
        Self {
            program: program.into(),
            args: args.iter().map(|a| (*a).to_string()).collect(),
            env: HashMap::new(),
            cwd: None,
        }
    }
}

impl Default for SidecarCommand {
    fn default() -> Self {
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        Self {
            program: SIDECAR_CMD.to_string(),
            args: SIDECAR_ARGS.iter().map(|a| (*a).to_string()).collect(),
            env: HashMap::new(),
            cwd: std::path::Path::new(manifest_dir)
                .parent()
                .map(|p| p.to_path_buf()),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ExitReport {
    pub death: Death,
    pub traceback: String,
}

impl From<std::io::Error> for BridgeError {
    fn from(e: std::io::Error) -> Self {
        BridgeError::Write(e.to_string())
    }
}

fn dispatch_event(events: &mpsc::Sender<Event>, dropped: &AtomicU64, event: Event) {
    if events.try_send(event).is_err() {
        dropped.fetch_add(1, Ordering::Relaxed);
    }
}

async fn deliver_reply(pending: &PendingReplies, reply: Reply) {
    let id = match &reply {
        Reply::Ok(r) => r.id.clone(),
        Reply::Err(r) => r.id.clone(),
    };
    match pending.lock().await.remove(&id) {
        Some(waiter) => {
            let _ = waiter.send(reply);
        }
        None => eprintln!("bridge: reply for unknown id {id}"),
    }
}

fn crash_reply(id: &str, death: Death) -> Reply {
    let error = ErrorBody {
        code: ErrorCode::Internal,
        message: death.describe(),
        retryable: false,
    };
    Reply::Err(ReplyErr {
        id: id.to_string(),
        error: serde_json::to_value(error).unwrap_or(serde_json::Value::Null),
    })
}

async fn take_every_pending_waiter(
    pending: &PendingReplies,
) -> Vec<(String, oneshot::Sender<Reply>)> {
    pending.lock().await.drain().collect()
}

async fn fail_all_pending(pending: &PendingReplies, death: Death) -> usize {
    let waiters = take_every_pending_waiter(pending).await;
    let count = waiters.len();
    for (id, waiter) in waiters {
        let _ = waiter.send(crash_reply(&id, death));
    }
    count
}

async fn read_stderr(stderr: ChildStderr, tail: SharedTail) {
    let mut lines = BufReader::new(stderr).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        eprintln!("sidecar: {line}");
        tail.lock().await.push(&line);
    }
}

async fn read_stdout(
    stdout: ChildStdout,
    pending: PendingReplies,
    events: mpsc::Sender<Event>,
    dropped: Arc<AtomicU64>,
    eof: oneshot::Sender<()>,
) {
    read_stdout_lines(stdout, pending, events, dropped).await;
    let _ = eof.send(());
}

async fn read_stdout_lines(
    stdout: ChildStdout,
    pending: PendingReplies,
    events: mpsc::Sender<Event>,
    dropped: Arc<AtomicU64>,
) {
    let mut lines = BufReader::new(stdout).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        match serde_json::from_str::<WireMessage>(line) {
            Ok(WireMessage::Event(event)) => dispatch_event(&events, &dropped, event),
            Ok(WireMessage::Reply(reply)) => deliver_reply(&pending, reply).await,
            Ok(WireMessage::Request(req)) => {
                eprintln!("bridge: sidecar sent an unexpected request: {}", req.method)
            }
            Err(e) => eprintln!("bridge: unparseable sidecar line: {e}"),
        }
    }
}

pub struct Sidecar {
    child: Child,
    stdin: Option<tokio::process::ChildStdin>,
    pending: PendingReplies,
    events: Option<mpsc::Receiver<Event>>,
    events_dropped: Arc<AtomicU64>,
    reader: Option<JoinHandle<()>>,
    stderr_reader: Option<JoinHandle<()>>,
    stderr_tail: SharedTail,
    started_at: std::time::Instant,
    stdout_eof: Option<oneshot::Receiver<()>>,
}

impl Sidecar {
    pub async fn spawn() -> Result<Self, BridgeError> {
        Self::spawn_with_env(HashMap::new()).await
    }

    pub async fn spawn_with_env(
        extra_env: HashMap<String, String>,
    ) -> Result<Self, BridgeError> {
        Self::spawn_with_command(SidecarCommand::with_env(extra_env), None).await
    }

    pub async fn spawn_with_command(
        command: SidecarCommand,
        events: Option<mpsc::Sender<Event>>,
    ) -> Result<Self, BridgeError> {
        let mut builder = Command::new(&command.program);
        builder.args(&command.args);
        if let Some(cwd) = &command.cwd {
            builder.current_dir(cwd);
        }
        let mut child = builder
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .envs(&command.env)
            .spawn()
            .map_err(|e| BridgeError::Spawn(e.to_string()))?;
        let stdin = child.stdin.take().expect("stdin piped");
        let stdout = child.stdout.take().expect("stdout piped");
        let stderr = child.stderr.take().expect("stderr piped");

        let pending: PendingReplies = Arc::new(Mutex::new(HashMap::new()));
        let events_dropped = Arc::new(AtomicU64::new(0));
        let stderr_tail: SharedTail = Arc::new(Mutex::new(StderrTail::default()));

        let (event_tx, event_rx) = match events {
            Some(tx) => (tx, None),
            None => {
                let (tx, rx) = mpsc::channel(EVENT_CHANNEL_CAPACITY);
                (tx, Some(rx))
            }
        };

        let (eof_tx, eof_rx) = oneshot::channel();
        let reader = tokio::spawn(read_stdout(
            stdout,
            Arc::clone(&pending),
            event_tx,
            Arc::clone(&events_dropped),
            eof_tx,
        ));
        let stderr_reader = tokio::spawn(read_stderr(stderr, Arc::clone(&stderr_tail)));

        Ok(Self {
            child,
            stdin: Some(stdin),
            pending,
            events: event_rx,
            events_dropped,
            reader: Some(reader),
            stderr_reader: Some(stderr_reader),
            stderr_tail,
            started_at: std::time::Instant::now(),
            stdout_eof: Some(eof_rx),
        })
    }

    pub fn take_stdout_eof(&mut self) -> Option<oneshot::Receiver<()>> {
        self.stdout_eof.take()
    }

    pub fn pid(&self) -> Option<u32> {
        self.child.id()
    }

    pub fn uptime(&self) -> std::time::Duration {
        self.started_at.elapsed()
    }

    pub fn take_events(&mut self) -> Option<mpsc::Receiver<Event>> {
        self.events.take()
    }

    pub fn events_dropped(&self) -> u64 {
        self.events_dropped.load(Ordering::Relaxed)
    }

    pub async fn send(
        &mut self,
        req: Request,
    ) -> Result<oneshot::Receiver<Reply>, BridgeError> {
        let id = req.id.clone();
        let payload = serde_json::to_string(&req)? + "\n";
        let (waiter, reply) = oneshot::channel();
        self.pending.lock().await.insert(id.clone(), waiter);

        if let Err(e) = self.write_all(payload.as_bytes()).await {
            self.pending.lock().await.remove(&id);
            return Err(e);
        }
        Ok(reply)
    }

    pub async fn request(&mut self, req: Request) -> Result<Reply, BridgeError> {
        let id = req.id.clone();
        let reply = self.send(req).await?;
        reply.await.map_err(|_| BridgeError::Closed(id))
    }

    async fn write_all(&mut self, payload: &[u8]) -> Result<(), BridgeError> {
        let stdin = self
            .stdin
            .as_mut()
            .ok_or_else(|| BridgeError::Write("sidecar stdin already closed".into()))?;
        stdin.write_all(payload).await?;
        stdin.flush().await?;
        Ok(())
    }

    pub async fn kill_async(&mut self) -> std::io::Result<()> {
        self.child.start_kill()
    }

    async fn join_readers_so_buffered_replies_arrive_before_reaping(&mut self) {
        if let Some(reader) = self.reader.take() {
            let _ = reader.await;
        }
        if let Some(stderr_reader) = self.stderr_reader.take() {
            let _ = stderr_reader.await;
        }
    }

    fn close_stdin_to_request_a_clean_exit(&mut self) {
        drop(self.stdin.take());
    }

    pub async fn await_exit(&mut self, requested: bool) -> ExitReport {
        if requested {
            self.close_stdin_to_request_a_clean_exit();
        }
        self.join_readers_so_buffered_replies_arrive_before_reaping().await;

        let status = match tokio::time::timeout(REAP_GRACE, self.child.wait()).await {
            Ok(Ok(status)) => Some(status),
            Ok(Err(_)) => None,
            Err(_) => {
                let _ = self.child.start_kill();
                self.child.wait().await.ok()
            }
        };

        let death = status.map(classify).unwrap_or(Death::Unknown);
        fail_all_pending(&self.pending, death).await;

        ExitReport {
            death,
            traceback: self.stderr_tail.lock().await.render(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::Duration;

    static SCRATCH_SEQ: AtomicU64 = AtomicU64::new(0);

    struct ScratchHome(std::path::PathBuf);
    impl ScratchHome {
        fn new() -> Self {
            let n = SCRATCH_SEQ.fetch_add(1, Ordering::Relaxed);
            let dir = std::env::temp_dir().join(format!(
                "jametly-bridge-{}-{n}",
                std::process::id()
            ));
            std::fs::create_dir_all(&dir).expect("scratch dir");
            Self(dir)
        }
    }
    impl Drop for ScratchHome {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    async fn spawn_isolated() -> Sidecar {
        let home = ScratchHome::new();
        Sidecar::spawn_with_env(HashMap::from([(
            "JAMETLY_HOME".into(),
            home.0.to_string_lossy().into_owned(),
        )]))
        .await
        .expect("sidecar should spawn")
    }

    #[tokio::test]
    async fn sidecar_echo_round_trip() {
        let mut sidecar = spawn_isolated().await;
        let reply = sidecar
            .request(Request {
                id: "rust-test".into(),
                method: "echo".into(),
                params: json!({"x": "hi"}),
            })
            .await
            .expect("sidecar should reply");

        match reply {
            Reply::Ok(ok) => {
                assert_eq!(ok.id, "rust-test");
                assert_eq!(ok.result, json!({"x": "hi"}));
            }
            Reply::Err(err) => panic!("expected echo success, got {err:?}"),
        }
    }

    #[tokio::test]
    async fn sidecar_surfaces_events_through_the_event_channel() {
        let mut sidecar = spawn_isolated().await;
        let mut events = sidecar
            .take_events()
            .expect("event receiver is available once");

        let reply = sidecar
            .request(Request {
                id: "stream-1".into(),
                method: "debug.stream".into(),
                params: json!({"count": 2}),
            })
            .await
            .expect("sidecar should reply");

        match reply {
            Reply::Ok(ok) => {
                assert_eq!(ok.id, "stream-1");
                assert_eq!(ok.result, json!({"count": 2}));
            }
            Reply::Err(err) => panic!("expected debug.stream success, got {err:?}"),
        }

        let mut kinds = Vec::new();
        for _ in 0..3 {
            let ev = tokio::time::timeout(Duration::from_secs(10), events.recv())
                .await
                .expect("event should arrive within 10s")
                .expect("event channel should stay open");
            assert_eq!(ev.method, "stream.event");
            assert_eq!(ev.params["correlation_id"], "stream-1");
            kinds.push(ev.params["kind"].as_str().unwrap().to_string());
        }
        assert_eq!(kinds, ["token", "token", "done"]);
        assert_eq!(sidecar.events_dropped(), 0);
    }

    #[tokio::test]
    async fn event_receiver_is_only_handed_out_once() {
        let mut sidecar = spawn_isolated().await;
        assert!(sidecar.take_events().is_some());
        assert!(sidecar.take_events().is_none());
    }

    #[tokio::test]
    async fn events_do_not_break_reply_correlation() {
        let mut sidecar = spawn_isolated().await;
        let _events = sidecar.take_events();

        for i in 0..3 {
            let id = format!("seq-{i}");
            let reply = sidecar
                .request(Request {
                    id: id.clone(),
                    method: "debug.stream".into(),
                    params: json!({"count": 1}),
                })
                .await
                .expect("sidecar should reply");
            match reply {
                Reply::Ok(ok) => assert_eq!(ok.id, id),
                Reply::Err(err) => panic!("expected success for {id}, got {err:?}"),
            }
        }
    }

    #[test]
    fn event_channel_capacity_is_bounded() {
        const {
            assert!(
                EVENT_CHANNEL_CAPACITY > 0 && EVENT_CHANNEL_CAPACITY <= 4096,
                "event backpressure must stay bounded"
            )
        };
    }

    #[tokio::test]
    async fn dispatch_event_drops_newest_when_the_channel_is_full() {
        let (tx, _rx) = tokio::sync::mpsc::channel::<Event>(2);
        let dropped = Arc::new(AtomicU64::new(0));
        let ev = |kind: &str| Event {
            method: "stream.event".into(),
            params: json!({"kind": kind}),
        };

        dispatch_event(&tx, &dropped, ev("token"));
        dispatch_event(&tx, &dropped, ev("token"));
        assert_eq!(dropped.load(Ordering::Relaxed), 0);

        dispatch_event(&tx, &dropped, ev("done"));
        assert_eq!(
            dropped.load(Ordering::Relaxed),
            1,
            "the newest event is dropped and counted once the buffer is full"
        );
    }
}
