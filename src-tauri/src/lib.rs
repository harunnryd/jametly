pub mod audio;
mod bridge;
pub mod capture;

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
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tauri::async_runtime::Mutex;
use tauri::Manager;

pub struct AppState {
    pub sidecar: Arc<Mutex<Option<Sidecar>>>,
    pub events_observed: Arc<AtomicU64>,
}

impl AppState {
    pub async fn initialise() -> Result<Self, String> {
        let mut sidecar = Sidecar::spawn().await.map_err(|e| e.to_string())?;
        let events = sidecar
            .take_events()
            .ok_or_else(|| "sidecar event receiver already taken".to_string())?;
        let events_observed = Arc::new(AtomicU64::new(0));

        let counter = Arc::clone(&events_observed);
        tauri::async_runtime::spawn(async move {
            let mut events = events;
            while let Some(event) = events.recv().await {
                counter.fetch_add(1, Ordering::Relaxed);
                eprintln!("bridge event: {}", event.method);
            }
        });

        Ok(Self {
            sidecar: Arc::new(Mutex::new(Some(sidecar))),
            events_observed,
        })
    }

    pub fn events_observed(&self) -> u64 {
        self.events_observed.load(Ordering::Relaxed)
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            sidecar: Arc::new(Mutex::new(None)),
            events_observed: Arc::new(AtomicU64::new(0)),
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
