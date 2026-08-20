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
}
