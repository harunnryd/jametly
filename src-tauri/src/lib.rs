mod bridge;

mod commands {
    use super::*;

    #[tauri::command]
    pub async fn jamly_invoke(
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
}

use bridge::Sidecar;
use ipc_proto::{Reply, Request};
use serde_json::Value;
use std::sync::Arc;
use tauri::async_runtime::Mutex;
use tauri::Manager;

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

#[cfg(mobile)]
#[tauri::mobile_entry_point]
pub fn run() {
    run_app()
}

#[cfg(not(mobile))]
pub fn run() {
    run_app()
}

fn run_app() {
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
        .invoke_handler(tauri::generate_handler![commands::jamly_invoke])
        .run(tauri::generate_context!())
        .expect("error while running jametly desktop shell");
}
