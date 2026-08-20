use std::process::Stdio;

use ipc_proto::{Reply, Request};
use thiserror::Error;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};

const SIDECAR_CMD: &str = "uv";
const SIDECAR_ARGS: &[&str] = &["run", "--project", "ai", "python", "-m", "jamly"];

#[derive(Debug, Error)]
pub enum BridgeError {
    #[error("sidecar spawn failed: {0}")]
    Spawn(String),
    #[error("sidecar stdin write failed: {0}")]
    Write(String),
    #[error("sidecar reply parse failed: {0}")]
    Parse(#[from] serde_json::Error),
    #[error("sidecar reply id mismatch (got {got:?}, expected {expected})")]
    Correlation {
        got: Option<String>,
        expected: String,
    },
}

impl From<std::io::Error> for BridgeError {
    fn from(e: std::io::Error) -> Self {
        BridgeError::Write(e.to_string())
    }
}

pub struct Sidecar {
    child: Child,
    stdin: tokio::process::ChildStdin,
    stdout: BufReader<tokio::process::ChildStdout>,
}

impl Sidecar {
    pub async fn spawn() -> Result<Self, BridgeError> {
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let repo_root = std::path::Path::new(manifest_dir)
            .parent()
            .ok_or_else(|| BridgeError::Spawn("could not determine repo root".into()))?;
        let mut child = Command::new(SIDECAR_CMD)
            .args(SIDECAR_ARGS)
            .current_dir(repo_root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .kill_on_drop(true)
            .spawn()
            .map_err(|e| BridgeError::Spawn(e.to_string()))?;
        let stdin = child.stdin.take().expect("stdin piped");
        let stdout = child.stdout.take().expect("stdout piped");
        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
        })
    }

    pub async fn request(&mut self, req: Request) -> Result<Reply, BridgeError> {
        let expected_id = req.id.clone();
        let payload = serde_json::to_string(&req)? + "\n";
        self.stdin.write_all(payload.as_bytes()).await?;
        self.stdin.flush().await?;

        let mut line = String::new();
        self.stdout.read_line(&mut line).await?;
        if line.is_empty() {
            return Err(BridgeError::Correlation {
                got: None,
                expected: expected_id,
            });
        }
        let reply: Reply = serde_json::from_str(line.trim())?;

        let got = match &reply {
            Reply::Ok(r) => r.id.clone(),
            Reply::Err(r) => r.id.clone(),
        };
        if got != expected_id {
            return Err(BridgeError::Correlation {
                got: Some(got),
                expected: expected_id,
            });
        }
        Ok(reply)
    }

    pub async fn kill_async(&mut self) -> std::io::Result<()> {
        self.child.start_kill()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::Duration;

    #[tokio::test]
    async fn sidecar_echo_round_trip() {
        let mut sidecar = Sidecar::spawn().await.expect("sidecar should spawn");
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
        let mut sidecar = Sidecar::spawn().await.expect("sidecar should spawn");
        let mut events = sidecar.take_events().expect("event receiver is available once");

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
        let mut sidecar = Sidecar::spawn().await.expect("sidecar should spawn");
        assert!(sidecar.take_events().is_some());
        assert!(sidecar.take_events().is_none());
    }

    #[tokio::test]
    async fn events_do_not_break_reply_correlation() {
        let mut sidecar = Sidecar::spawn().await.expect("sidecar should spawn");
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
        assert!(
            EVENT_CHANNEL_CAPACITY > 0 && EVENT_CHANNEL_CAPACITY <= 4096,
            "event backpressure must stay bounded, got {EVENT_CHANNEL_CAPACITY}"
        );
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
