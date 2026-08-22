use std::str::FromStr;

use tauri::{AppHandle, Runtime};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Shortcut, ShortcutState};
use thiserror::Error;

use crate::window;

pub const DEFAULT_TOGGLE_SHORTCUT: &str = "CmdOrCtrl+Shift+Space";

#[derive(Debug, Error, PartialEq)]
pub enum ShortcutError {
    #[error("shortcut accelerator {0:?} is not a valid combination")]
    Unparsable(String),
    #[error(
        "shortcut accelerator {0:?} binds a media key, which needs input-monitoring permission \
         and fails silently without it"
    )]
    MediaKey(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ShortcutSupport {
    Available,
    UnsupportedSession,
}

impl ShortcutSupport {
    pub fn describe(self) -> &'static str {
        match self {
            ShortcutSupport::Available => "global shortcuts are available",
            ShortcutSupport::UnsupportedSession => {
                "global shortcuts do not work on Wayland; this build ships no built-in \
                 Wayland opener (a tray icon is scoped to JAM-0017)"
            }
        }
    }
}

fn is_media_key(code: Code) -> bool {
    matches!(
        code,
        Code::MediaPlayPause
            | Code::MediaStop
            | Code::MediaTrackNext
            | Code::MediaTrackPrevious
            | Code::AudioVolumeUp
            | Code::AudioVolumeDown
            | Code::AudioVolumeMute
    )
}

pub fn parse_toggle(accelerator: &str) -> Result<Shortcut, ShortcutError> {
    let shortcut = Shortcut::from_str(accelerator)
        .map_err(|_| ShortcutError::Unparsable(accelerator.to_string()))?;

    if is_media_key(shortcut.key) {
        return Err(ShortcutError::MediaKey(accelerator.to_string()));
    }

    Ok(shortcut)
}

pub fn support_for(session_type: Option<&str>, wayland_display: Option<&str>) -> ShortcutSupport {
    if !cfg!(target_os = "linux") {
        return ShortcutSupport::Available;
    }

    let wayland_session = session_type.is_some_and(|value| value.eq_ignore_ascii_case("wayland"));
    if wayland_session || wayland_display.is_some_and(|value| !value.is_empty()) {
        return ShortcutSupport::UnsupportedSession;
    }

    ShortcutSupport::Available
}

pub fn support_from_env() -> ShortcutSupport {
    let session_type = std::env::var("XDG_SESSION_TYPE").ok();
    let wayland_display = std::env::var("WAYLAND_DISPLAY").ok();
    support_for(session_type.as_deref(), wayland_display.as_deref())
}

pub fn register_toggle<R: Runtime>(app: &AppHandle<R>, accelerator: &str) -> Result<(), String> {
    let shortcut = parse_toggle(accelerator).map_err(|error| error.to_string())?;

    let support = support_from_env();
    if support == ShortcutSupport::UnsupportedSession {
        return Err(support.describe().to_string());
    }

    let manager = app.global_shortcut();
    if manager.is_registered(shortcut) {
        manager.unregister(shortcut).map_err(|e| e.to_string())?;
    }

    manager.register(shortcut).map_err(|e| e.to_string())
}

pub fn unregister_all<R: Runtime>(app: &AppHandle<R>) {
    let _ = app.global_shortcut().unregister_all();
}

pub fn plugin<R: Runtime>(toggle: Shortcut) -> tauri::plugin::TauriPlugin<R> {
    tauri_plugin_global_shortcut::Builder::new()
        .with_handler(move |app, shortcut, event| {
            if shortcut != &toggle || event.state() != ShortcutState::Pressed {
                return;
            }
            if let Err(error) = window::toggle(app) {
                eprintln!("overlay: could not toggle the window: {error}");
            }
        })
        .build()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_default_accelerator_parses() {
        assert!(parse_toggle(DEFAULT_TOGGLE_SHORTCUT).is_ok());
    }

    #[test]
    fn an_unknown_accelerator_is_rejected_by_name() {
        assert_eq!(
            parse_toggle("Ctrl+Banana"),
            Err(ShortcutError::Unparsable("Ctrl+Banana".to_string()))
        );
    }

    #[test]
    fn media_keys_are_rejected_because_they_need_input_monitoring() {
        assert_eq!(
            parse_toggle("MediaPlayPause"),
            Err(ShortcutError::MediaKey("MediaPlayPause".to_string()))
        );
    }

    #[test]
    fn a_wayland_session_reports_shortcuts_as_unavailable() {
        let support = support_for(Some("wayland"), None);

        if cfg!(target_os = "linux") {
            assert_eq!(support, ShortcutSupport::UnsupportedSession);
            let message = support.describe();
            assert!(message.contains("Wayland"));
            assert!(message.contains("do not work"));
            assert!(message.contains("JAM-0017"));
        } else {
            assert_eq!(support, ShortcutSupport::Available);
        }
    }

    #[test]
    fn a_wayland_display_alone_is_enough_to_report_unavailable() {
        let support = support_for(None, Some("wayland-0"));

        if cfg!(target_os = "linux") {
            assert_eq!(support, ShortcutSupport::UnsupportedSession);
        } else {
            assert_eq!(support, ShortcutSupport::Available);
        }
    }

    #[test]
    fn an_x11_session_reports_shortcuts_as_available() {
        assert_eq!(support_for(Some("x11"), None), ShortcutSupport::Available);
        assert_eq!(
            support_for(Some("x11"), Some("")),
            ShortcutSupport::Available
        );
    }
}
