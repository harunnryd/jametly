//! jametly desktop shell.
//!
//! Phase 0 ships only the IPC bridge scaffold:
//! - `bridge::Sidecar` spawns the Python AI sidecar via `tokio::process`
//!   and pipes JSON-RPC over NDJSON on stdio.
//! - `invoke_python` is the single Tauri command wired for Phase 0;
//!   it forwards a request to the sidecar and returns the reply.
//! - The `Sidecar` is spawned once at startup and stored in `AppState`.

mod bridge;

use bridge::Sidecar;
use ipc_proto::Reply;
use ipc_proto::Request;
use serde_json::Value;
use std::sync::Arc;
use tauri::async_runtime::Mutex;

pub struct AppState {
    pub sidecar: Arc<Mutex<Option<Sidecar>>>,
}

impl AppState {
    pub async fn initialise() -> Result<Self, String> {
        let sidecar = Sidecar::spawn().await.map_err(|e| e.to_string())?;
        Ok(Self {
            sidecar: Arc::new(Mutex::new(Some(sidecar))),
        })
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            sidecar: Arc::new(Mutex::new(None)),
        }
    }
}

#[tauri::command]
pub async fn invoke_python(
    state: tauri::State<'_, AppState>,
    id: String,
    method: String,
    params: Value,
) -> Result<Reply, String> {
    let req = Request { id, method, params };
    let mut guard = state.sidecar.lock().await;
    let sidecar = guard
        .as_mut()
        .ok_or_else(|| "sidecar not initialised".to_string())?;
    sidecar.request(req).await.map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|_app| {
            let handle = _app.handle().clone();
            tauri::async_runtime::block_on(async move {
                match AppState::initialise().await {
                    Ok(state) => {
                        handle.manage(state);
                    }
                    Err(e) => {
                        eprintln!("failed to start sidecar: {e}");
                    }
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![invoke_python])
        .run(tauri::generate_context!())
        .expect("error while running jametly desktop shell");
}
