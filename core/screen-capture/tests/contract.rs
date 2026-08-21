use std::time::{Duration, SystemTime};

use screen_capture::{
    BlobStore, CaptureBackend, CaptureError, MockCapture, Monitor, Rect, RgbaFrame,
};

fn monitor() -> Monitor {
    Monitor {
        id: "primary".into(),
        width: 1_920,
        height: 1_080,
        primary: true,
    }
}

#[test]
fn region_validation_accepts_monitor_relative_bounds() {
    let rect = Rect::new(100, 50, 640, 480).unwrap();
    assert_eq!(rect.validate_within(&monitor()).unwrap(), rect);
}

#[test]
fn region_validation_rejects_zero_size_overflow_and_out_of_bounds() {
    assert!(matches!(
        Rect::new(0, 0, 0, 10),
        Err(CaptureError::InvalidRegion)
    ));
    assert!(matches!(
        Rect::new(u32::MAX, 0, 2, 1),
        Err(CaptureError::InvalidRegion)
    ));

    let rect = Rect::new(1_900, 0, 40, 20).unwrap();
    assert!(matches!(
        rect.validate_within(&monitor()),
        Err(CaptureError::InvalidRegion)
    ));
}

#[test]
fn rgba_frame_rejects_wrong_pixel_length() {
    assert!(matches!(
        RgbaFrame::new(2, 2, vec![0; 15]),
        Err(CaptureError::InvalidFrame)
    ));
}

#[test]
fn mock_capture_is_deterministic_and_crops_regions() {
    let backend = MockCapture::new(monitor());
    let full_a = backend.capture_primary().unwrap();
    let full_b = backend.capture_primary().unwrap();
    assert_eq!(full_a, full_b);

    let rect = Rect::new(10, 20, 4, 3).unwrap();
    let crop = backend.capture_region(rect).unwrap();
    assert_eq!((crop.width(), crop.height()), (4, 3));
    assert_eq!(crop.pixel(0, 0), full_a.pixel(10, 20));
}

#[test]
fn mock_surfaces_permission_and_unavailable_errors() {
    let denied = MockCapture::permission_denied(monitor());
    assert!(matches!(
        denied.capture_primary(),
        Err(CaptureError::PermissionDenied)
    ));

    let unavailable = MockCapture::unavailable();
    assert!(matches!(
        unavailable.capture_primary(),
        Err(CaptureError::Unavailable)
    ));
}

#[test]
fn blob_store_writes_png_under_its_root() {
    let temp = tempfile::tempdir().unwrap();
    let store = BlobStore::new(temp.path()).unwrap();
    let frame = MockCapture::new(monitor())
        .capture_region(Rect::new(0, 0, 4, 4).unwrap())
        .unwrap();

    let path = store.write_png("capture", &frame).unwrap();
    assert!(path.starts_with(store.root()));
    assert_eq!(path.extension().and_then(|ext| ext.to_str()), Some("png"));
    assert!(path.is_file());
    assert_eq!(&std::fs::read(&path).unwrap()[..8], b"\x89PNG\r\n\x1a\n");
}

#[test]
fn blob_store_rejects_unsafe_stems() {
    let temp = tempfile::tempdir().unwrap();
    let store = BlobStore::new(temp.path()).unwrap();
    let frame = RgbaFrame::solid(1, 1, [0, 0, 0, 255]).unwrap();

    assert!(matches!(
        store.write_png("../escape", &frame),
        Err(CaptureError::UnsafePath)
    ));
}

#[test]
fn stale_blob_cleanup_removes_only_old_regular_png_files() {
    let temp = tempfile::tempdir().unwrap();
    let store = BlobStore::new(temp.path()).unwrap();
    let old = store.root().join("old.png");
    let fresh = store.root().join("fresh.png");
    let other = store.root().join("keep.txt");
    std::fs::write(&old, b"old").unwrap();
    std::thread::sleep(Duration::from_millis(20));
    let cutoff = SystemTime::now();
    std::thread::sleep(Duration::from_millis(20));
    std::fs::write(&fresh, b"fresh").unwrap();
    std::fs::write(&other, b"other").unwrap();

    assert_eq!(store.cleanup_before(cutoff).unwrap(), 1);
    assert!(!old.exists());
    assert!(fresh.exists());
    assert!(other.exists());
}
