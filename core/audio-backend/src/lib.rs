use std::fmt;
use std::future::Future;
use std::pin::Pin;
use std::str::FromStr;

use thiserror::Error;
use tokio::sync::mpsc;

mod mock;

pub use mock::MockCapture;

pub const BRIDGE_SAMPLE_RATE: u32 = 16_000;
pub const BRIDGE_CHANNELS: u16 = 1;

/// Overflow policy once this many frames are unread: drop the newest, count it, never block.
///
/// Capture runs on a clock nobody can pause, so a slow consumer must lose frames rather than
/// stall the device. Mirrors the event-channel policy in `src-tauri/src/bridge.rs`.
pub const FRAME_CHANNEL_CAPACITY: usize = 64;

pub type CaptureFuture<'a, T> = Pin<Box<dyn Future<Output = T> + Send + 'a>>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CaptureKind {
    Mic,
    Loopback,
}

impl CaptureKind {
    pub fn as_str(self) -> &'static str {
        match self {
            CaptureKind::Mic => "mic",
            CaptureKind::Loopback => "loopback",
        }
    }
}

impl fmt::Display for CaptureKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Debug, Error, PartialEq, Eq)]
#[error("unknown capture kind `{0}`, expected `mic` or `loopback`")]
pub struct UnknownCaptureKind(String);

impl FromStr for CaptureKind {
    type Err = UnknownCaptureKind;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "mic" => Ok(CaptureKind::Mic),
            "loopback" => Ok(CaptureKind::Loopback),
            other => Err(UnknownCaptureKind(other.to_string())),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AudioFormat {
    pub sample_rate: u32,
    pub channels: u16,
}

impl AudioFormat {
    pub fn new(sample_rate: u32, channels: u16) -> Self {
        Self {
            sample_rate,
            channels,
        }
    }

    /// The format every backend must present at the bridge boundary: 16 kHz mono.
    pub fn bridge() -> Self {
        Self::new(BRIDGE_SAMPLE_RATE, BRIDGE_CHANNELS)
    }

    pub fn is_bridge_ready(self) -> bool {
        self == Self::bridge()
    }

    fn frames_per_channel(self, sample_count: usize) -> u64 {
        let channels = u64::from(self.channels.max(1));
        sample_count as u64 / channels
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PcmFrame {
    pub ts_ms: u64,
    pub format: AudioFormat,
    pub samples: Vec<i16>,
}

impl PcmFrame {
    pub fn new(ts_ms: u64, format: AudioFormat, samples: Vec<i16>) -> Self {
        Self {
            ts_ms,
            format,
            samples,
        }
    }

    pub fn sample_count(&self) -> usize {
        self.samples.len()
    }

    pub fn duration_ms(&self) -> u64 {
        let rate = u64::from(self.format.sample_rate.max(1));
        self.format.frames_per_channel(self.sample_count()) * 1_000 / rate
    }
}

/// Split a frame so no piece exceeds `max_ms`, preserving sample order and total duration.
pub fn chunk(frame: &PcmFrame, max_ms: u32) -> Vec<PcmFrame> {
    let channels = usize::from(frame.format.channels.max(1));
    let rate = u64::from(frame.format.sample_rate.max(1));
    let per_chunk = (u64::from(max_ms.max(1)) * rate / 1_000).max(1) as usize * channels;

    let mut chunks = Vec::new();
    let mut ts_ms = frame.ts_ms;
    for window in frame.samples.chunks(per_chunk) {
        let piece = PcmFrame::new(ts_ms, frame.format, window.to_vec());
        ts_ms += piece.duration_ms();
        chunks.push(piece);
    }
    chunks
}

#[derive(Debug, Clone, Error, PartialEq, Eq)]
pub enum CaptureError {
    #[error("capture is already running")]
    AlreadyRunning,
    #[error("capture is not running")]
    NotRunning,
    #[error("audio device lost")]
    DeviceLost,
    #[error("capture kind `{0}` is not supported by this backend")]
    UnsupportedKind(CaptureKind),
    #[error("audio backend failure: {0}")]
    Backend(String),
}

/// The consumer half of a bounded frame stream.
#[derive(Debug)]
pub struct FrameStream {
    rx: mpsc::Receiver<PcmFrame>,
}

/// The producer half. `offer` never blocks, so a realtime capture callback can call it.
#[derive(Debug, Clone)]
pub struct FrameSink {
    tx: mpsc::Sender<PcmFrame>,
    dropped: std::sync::Arc<std::sync::atomic::AtomicU64>,
}

impl FrameStream {
    pub fn bounded(capacity: usize) -> (Self, FrameSink) {
        let (tx, rx) = mpsc::channel(capacity.max(1));
        let sink = FrameSink {
            tx,
            dropped: std::sync::Arc::new(std::sync::atomic::AtomicU64::new(0)),
        };
        (Self { rx }, sink)
    }

    pub async fn recv(&mut self) -> Option<PcmFrame> {
        self.rx.recv().await
    }

    pub fn try_recv(&mut self) -> Option<PcmFrame> {
        self.rx.try_recv().ok()
    }
}

impl FrameSink {
    /// Returns false when the frame was dropped because the consumer is behind or gone.
    pub fn offer(&self, frame: PcmFrame) -> bool {
        if self.tx.try_send(frame).is_ok() {
            return true;
        }
        self.dropped
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        false
    }

    pub fn dropped(&self) -> u64 {
        self.dropped.load(std::sync::atomic::Ordering::Relaxed)
    }
}

/// A capture source. Implementors own device acquisition; the contract here is platform-neutral.
pub trait AudioBackend {
    fn format(&self) -> AudioFormat;

    fn is_running(&self) -> bool;

    fn start(&mut self, kind: CaptureKind) -> CaptureFuture<'_, Result<FrameStream, CaptureError>>;

    fn stop(&mut self) -> CaptureFuture<'_, Result<(), CaptureError>>;
}
