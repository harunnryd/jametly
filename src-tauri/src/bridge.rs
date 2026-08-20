//! Bridge between the Rust host and the Python AI sidecar.
//!
//! Phase 0 ships only the spine: an end-to-end NDJSON echo over stdio
//! via `tokio::process::Command`. The Tauri-side command is wired to
//! this bridge via the `invoke_python` function in `lib.rs`.

use std::process::Stdio;

use ipc_proto::{Reply, ReplyOk, Request};
use serde_json::Value;
use thiserror::Error;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};

const SIDECAR_CMD: &str = "uv";
const SIDECAR_ARGS: &[&str] = &["run", "--project", "ai", "python", "-m", "jamly"];

#[derive(Debug, Error)]
pub enum BridgeError {
    #[error("sidecar spawn failed: {0}")]
    Spawn(#[from] std::io::Error),
    #[error("sidecar stdin write failed: {0}")]
    Write(#[from] tokio::io::Error),
    #[error("sidecar reply parse failed: {0}")]
    Parse(#[from] serde_json::Error),
    #[error("sidecar reply id mismatch (got {got:?}, expected {expected})")]
    Correlation { got: Option<String>, expected: String },
}

pub struct Sidecar {
    child: Child,
    stdin: tokio::process::ChildStdin,
    stdout: BufReader<tokio::process::ChildStdout>,
}

impl Sidecar {
    pub async fn spawn() -> Result<Self, BridgeError> {
        let mut child = Command::new(SIDECAR_CMD)
            .args(SIDECAR_ARGS)
            .current_dir(env!("CARGO_MANIFEST_DIR").rsplit_once('/').map(|(p, _)| p).unwrap_or("."))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .kill_on_drop(true)
            .spawn()?;
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

        // Lock-step read: one line in, one line out. The Python sidecar
        // emits exactly one NDJSON line per request. (Phase 1+ adds the
        // streaming event channel.)
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

    pub fn kill(&mut self) -> std::io::Result<()> {
        self.child.kill()
    }
}

#[tauri::command]
pub async fn invoke_python(
    state: tauri::State<'_, crate::AppState>,
    id: String,
    method: String,
    params: Value,
) -> Result<Reply, String> {
    let mut guard = state.sidecar.lock().await;
    let sidecar = guard
        .as_mut()
        .ok_or_else(|| "sidecar not initialised".to_string())?;
    let req = Request { id, method, params };
    sidecar.request(req).await.map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn reply_id_extraction_is_consistent() {
        let ok = Reply::Ok(ReplyOk {
            id: "r".into(),
            result: json!({}),
        });
        let got = match &ok {
            Reply::Ok(r) => r.id.clone(),
            Reply::Err(r) => r.id.clone(),
        };
        assert_eq!(got, "r");
    }
}
