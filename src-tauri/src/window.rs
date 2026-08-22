use tauri::{AppHandle, LogicalPosition, LogicalSize, Manager, PhysicalPosition, Runtime, WebviewWindow};

use crate::shortcuts::{support_from_env, ShortcutSupport};

pub const OVERLAY_LABEL: &str = "main";
pub const OVERLAY_WIDTH: f64 = 600.0;
pub const OVERLAY_HEIGHT: f64 = 54.0;
pub const OVERLAY_TOP_INSET: f64 = 120.0;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct MonitorGeometry {
    pub origin_x: f64,
    pub origin_y: f64,
    pub width: f64,
    pub height: f64,
}

pub fn overlay_origin(monitor: MonitorGeometry) -> LogicalPosition<f64> {
    let slack_x = (monitor.width - OVERLAY_WIDTH).max(0.0);
    let slack_y = (monitor.height - OVERLAY_HEIGHT).max(0.0);

    LogicalPosition::new(
        monitor.origin_x + slack_x / 2.0,
        monitor.origin_y + OVERLAY_TOP_INSET.min(slack_y),
    )
}

pub fn overlay<R: Runtime>(app: &AppHandle<R>) -> Option<WebviewWindow<R>> {
    app.get_webview_window(OVERLAY_LABEL)
}

fn resolve_monitor<R: Runtime>(window: &WebviewWindow<R>) -> tauri::Result<Option<tauri::Monitor>> {
    if cfg!(target_os = "linux") && support_from_env() != ShortcutSupport::Available {
        return match window.current_monitor()? {
            Some(monitor) => Ok(Some(monitor)),
            None => window.primary_monitor(),
        };
    }

    if let Ok(cursor) = window.cursor_position() {
        let point: PhysicalPosition<f64> = cursor;
        if point.x > 0.0 || point.y > 0.0 {
            if let Ok(Some(monitor)) = window.monitor_from_point(point.x, point.y) {
                return Ok(Some(monitor));
            }
        }
    }

    match window.current_monitor()? {
        Some(monitor) => Ok(Some(monitor)),
        None => window.primary_monitor(),
    }
}

fn current_geometry<R: Runtime>(
    window: &WebviewWindow<R>,
) -> tauri::Result<Option<MonitorGeometry>> {
    Ok(resolve_monitor(window)?.map(|monitor| {
        let scale = monitor.scale_factor();
        let size = monitor.size().to_logical::<f64>(scale);
        let position = monitor.position().to_logical::<f64>(scale);
        MonitorGeometry {
            origin_x: position.x,
            origin_y: position.y,
            width: size.width,
            height: size.height,
        }
    }))
}

pub fn reposition<R: Runtime>(window: &WebviewWindow<R>) -> tauri::Result<()> {
    window.set_size(LogicalSize::new(OVERLAY_WIDTH, OVERLAY_HEIGHT))?;
    if let Some(geometry) = current_geometry(window)? {
        window.set_position(overlay_origin(geometry))?;
    }
    Ok(())
}

pub fn show<R: Runtime>(window: &WebviewWindow<R>) -> tauri::Result<()> {
    if !window.is_visible().unwrap_or(false) {
        reposition(window)?;
        window.show()?;
    }
    window.set_focus()
}

pub fn hide<R: Runtime>(window: &WebviewWindow<R>) -> tauri::Result<()> {
    window.hide()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ToggleAction {
    Show,
    Hide,
}

pub fn toggle_decision(visible: bool, focused: bool) -> ToggleAction {
    if visible && focused {
        ToggleAction::Hide
    } else {
        ToggleAction::Show
    }
}

pub fn toggle<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let Some(window) = overlay(app) else {
        return Ok(());
    };

    let visible = window.is_visible().unwrap_or(false);
    let focused = window.is_focused().unwrap_or(false);

    match toggle_decision(visible, focused) {
        ToggleAction::Hide => hide(&window),
        ToggleAction::Show => show(&window),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn monitor(origin_x: f64, origin_y: f64, width: f64, height: f64) -> MonitorGeometry {
        MonitorGeometry {
            origin_x,
            origin_y,
            width,
            height,
        }
    }

    #[test]
    fn the_overlay_is_horizontally_centred_and_anchored_below_the_top_edge() {
        let origin = overlay_origin(monitor(0.0, 0.0, 1920.0, 1080.0));

        assert_eq!(origin.x, 660.0);
        assert_eq!(origin.y, OVERLAY_TOP_INSET);
    }

    #[test]
    fn positions_are_relative_to_the_monitor_the_overlay_opens_on() {
        let origin = overlay_origin(monitor(-1920.0, -220.0, 1920.0, 1080.0));

        assert_eq!(origin.x, -1260.0);
        assert_eq!(origin.y, -220.0 + OVERLAY_TOP_INSET);
    }

    #[test]
    fn a_monitor_narrower_than_the_overlay_pins_it_to_the_left_edge() {
        let origin = overlay_origin(monitor(0.0, 0.0, 480.0, 1080.0));

        assert_eq!(origin.x, 0.0);
    }

    #[test]
    fn a_monitor_shorter_than_the_top_inset_keeps_the_overlay_on_screen() {
        let origin = overlay_origin(monitor(0.0, 0.0, 1920.0, 80.0));

        assert_eq!(origin.y, 80.0 - OVERLAY_HEIGHT);
    }

    #[test]
    fn a_monitor_shorter_than_the_overlay_pins_it_to_the_top_edge() {
        let origin = overlay_origin(monitor(0.0, 0.0, 1920.0, 20.0));

        assert_eq!(origin.y, 0.0);
    }

    #[test]
    fn toggle_hides_when_visible_and_focused() {
        assert_eq!(toggle_decision(true, true), ToggleAction::Hide);
    }

    #[test]
    fn toggle_raises_when_visible_but_unfocused() {
        assert_eq!(toggle_decision(true, false), ToggleAction::Show);
    }

    #[test]
    fn toggle_shows_when_hidden() {
        assert_eq!(toggle_decision(false, false), ToggleAction::Show);
        assert_eq!(toggle_decision(false, true), ToggleAction::Show);
    }
}
