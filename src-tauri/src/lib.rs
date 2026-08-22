pub mod audio;
mod bridge;
pub mod capture;
pub mod secure_store;
#[cfg(desktop)]
pub mod shortcuts;
mod supervisor;
pub mod window;

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
        state
            .supervisor
            .request(req)
            .await
            .map_err(|e| e.to_string())
    }

    #[tauri::command]
    pub async fn jamly_restart_engine(state: tauri::State<'_, AppState>) -> Result<(), String> {
        state
            .supervisor
            .restart_manually()
            .await
            .map_err(|e| e.to_string())
    }
}

use bridge::SidecarCommand;
use ipc_proto::{Reply, Request};
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use supervisor::{RestartPolicy, Supervisor};
use tauri::{AppHandle, Emitter, Manager};

pub struct AppState {
    pub supervisor: Arc<Supervisor>,
    pub events_observed: Arc<AtomicU64>,
}

impl AppState {
    pub async fn initialise(app: AppHandle) -> Result<Self, String> {
        let (supervisor, events) =
            Supervisor::start(SidecarCommand::default(), RestartPolicy::default())
                .await
                .map_err(|e| e.to_string())?;
        let events_observed = Arc::new(AtomicU64::new(0));

        let counter = Arc::clone(&events_observed);
        tauri::async_runtime::spawn(async move {
            let mut events = events;
            while let Some(event) = events.recv().await {
                counter.fetch_add(1, Ordering::Relaxed);
                if let Err(error) = app.emit(&event.method, event.params.clone()) {
                    eprintln!("bridge: could not forward {}: {error}", event.method);
                }
            }
        });

        Ok(Self {
            supervisor,
            events_observed,
        })
    }

    pub fn events_observed(&self) -> u64 {
        self.events_observed.load(Ordering::Relaxed)
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

#[cfg(desktop)]
fn install_overlay_shortcut(app: &tauri::App) {
    let toggle = match shortcuts::parse_toggle(shortcuts::DEFAULT_TOGGLE_SHORTCUT) {
        Ok(toggle) => toggle,
        Err(error) => {
            eprintln!("overlay: {error}");
            return;
        }
    };

    let handle = app.handle();
    if let Err(error) = handle.plugin(shortcuts::plugin(toggle)) {
        eprintln!("overlay: could not install the shortcut plugin: {error}");
        return;
    }

    if let Err(error) = shortcuts::register_toggle(handle, shortcuts::DEFAULT_TOGGLE_SHORTCUT) {
        eprintln!(
            "overlay: {} is unavailable ({error}); open the overlay from the tray instead",
            shortcuts::DEFAULT_TOGGLE_SHORTCUT
        );
    }
}

fn run_app() {
    tauri::Builder::default()
        .setup(|_app| {
            let handle = _app.handle().clone();
            tauri::async_runtime::block_on(async move {
                match AppState::initialise(handle.clone()).await {
                    Ok(state) => {
                        handle.manage(state);
                    }
                    Err(e) => {
                        eprintln!("failed to start sidecar: {e}");
                    }
                }
            });

            #[cfg(target_os = "macos")]
            _app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            #[cfg(desktop)]
            install_overlay_shortcut(_app);

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::jamly_invoke,
            commands::jamly_restart_engine
        ])
        .build(tauri::generate_context!())
        .expect("error while running jametly desktop shell")
        .run(|handle, event| {
            if matches!(event, tauri::RunEvent::ExitRequested { .. }) {
                #[cfg(desktop)]
                shortcuts::unregister_all(handle);
                #[cfg(not(desktop))]
                let _ = handle;
            }
        });
}
