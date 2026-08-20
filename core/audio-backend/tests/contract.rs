use audio_backend::{
    AudioBackend, AudioFormat, CaptureError, CaptureKind, FrameStream, MockCapture, PcmFrame,
    BRIDGE_CHANNELS, BRIDGE_SAMPLE_RATE, FRAME_CHANNEL_CAPACITY,
};

fn bridge_format() -> AudioFormat {
    AudioFormat::bridge()
}

#[test]
fn bridge_format_is_16k_mono() {
    let format = bridge_format();
    assert_eq!(format.sample_rate, 16_000);
    assert_eq!(format.channels, 1);
    assert_eq!(BRIDGE_SAMPLE_RATE, 16_000);
    assert_eq!(BRIDGE_CHANNELS, 1);
}

#[test]
fn frame_channel_capacity_is_bounded() {
    const {
        assert!(
            FRAME_CHANNEL_CAPACITY > 0 && FRAME_CHANNEL_CAPACITY <= 4096,
            "frame backpressure must stay bounded"
        )
    };
}

#[test]
fn capture_kind_covers_the_ipc_union() {
    assert_eq!(CaptureKind::Mic.as_str(), "mic");
    assert_eq!(CaptureKind::Loopback.as_str(), "loopback");
    assert_eq!("mic".parse::<CaptureKind>().unwrap(), CaptureKind::Mic);
    assert_eq!(
        "loopback".parse::<CaptureKind>().unwrap(),
        CaptureKind::Loopback
    );
    assert!("speaker".parse::<CaptureKind>().is_err());
}

#[test]
fn frame_duration_matches_sample_count() {
    let frame = PcmFrame::new(0, bridge_format(), vec![0i16; 1_600]);
    assert_eq!(frame.duration_ms(), 100);
    assert_eq!(frame.sample_count(), 1_600);
}

#[tokio::test]
async fn mock_capture_starts_stops_and_reports_format() {
    let mut backend = MockCapture::new(bridge_format(), 160);
    assert_eq!(backend.format(), bridge_format());

    let stream = backend.start(CaptureKind::Loopback).await.unwrap();
    assert!(backend.is_running());
    drop(stream);

    backend.stop().await.unwrap();
    assert!(!backend.is_running());
}

#[tokio::test]
async fn mock_capture_rejects_double_start() {
    let mut backend = MockCapture::new(bridge_format(), 160);
    let _stream = backend.start(CaptureKind::Mic).await.unwrap();

    let err = backend.start(CaptureKind::Mic).await.unwrap_err();
    assert!(matches!(err, CaptureError::AlreadyRunning));
}

#[tokio::test]
async fn mock_capture_rejects_stop_when_idle() {
    let mut backend = MockCapture::new(bridge_format(), 160);
    let err = backend.stop().await.unwrap_err();
    assert!(matches!(err, CaptureError::NotRunning));
}

#[tokio::test]
async fn mock_capture_surfaces_a_configured_device_loss() {
    let mut backend = MockCapture::new(bridge_format(), 160).failing_with(CaptureError::DeviceLost);
    let err = backend.start(CaptureKind::Loopback).await.unwrap_err();
    assert!(matches!(err, CaptureError::DeviceLost));
    assert!(!backend.is_running());
}

#[tokio::test]
async fn mock_capture_emits_deterministic_frames() {
    let mut first = MockCapture::new(bridge_format(), 160);
    let mut second = MockCapture::new(bridge_format(), 160);

    let a = collect(first.start(CaptureKind::Mic).await.unwrap(), 4).await;
    let b = collect(second.start(CaptureKind::Mic).await.unwrap(), 4).await;

    assert_eq!(a, b, "same seed and frame size must replay identically");
    assert!(a.iter().all(|frame| frame.sample_count() == 160));
}

#[tokio::test]
async fn frame_timestamps_are_monotonic_and_gapless() {
    let mut backend = MockCapture::new(bridge_format(), 160);
    let frames = collect(backend.start(CaptureKind::Mic).await.unwrap(), 5).await;

    let step = frames[0].duration_ms();
    for pair in frames.windows(2) {
        assert!(pair[1].ts_ms > pair[0].ts_ms, "timestamps must increase");
        assert_eq!(pair[1].ts_ms - pair[0].ts_ms, step, "no gaps between frames");
    }
}

#[tokio::test]
async fn stream_drops_newest_frame_when_full_and_counts_it() {
    let (mut stream, sink) = FrameStream::bounded(2);
    let frame = |ts| PcmFrame::new(ts, bridge_format(), vec![0i16; 160]);

    assert!(sink.offer(frame(0)));
    assert!(sink.offer(frame(10)));
    assert!(!sink.offer(frame(20)), "third frame must not be accepted");
    assert_eq!(sink.dropped(), 1);

    assert_eq!(stream.recv().await.unwrap().ts_ms, 0);
    assert_eq!(stream.recv().await.unwrap().ts_ms, 10);
    assert!(sink.offer(frame(30)), "draining frees capacity");
    assert_eq!(sink.dropped(), 1);
}

#[tokio::test]
async fn stream_closes_when_the_sink_is_dropped() {
    let (mut stream, sink) = FrameStream::bounded(2);
    drop(sink);
    assert!(stream.recv().await.is_none());
}

async fn collect(mut stream: FrameStream, count: usize) -> Vec<PcmFrame> {
    let mut frames = Vec::with_capacity(count);
    for _ in 0..count {
        frames.push(stream.recv().await.expect("mock stream stays open"));
    }
    frames
}
