use crate::{
    AudioBackend, AudioFormat, CaptureError, CaptureKind, FrameSink, FrameStream, PcmFrame,
    FRAME_CHANNEL_CAPACITY,
};

/// A backend that synthesises frames from a fixed ramp, so two runs replay identically.
///
/// This is the only implementation that ships today; real per-OS capture is deferred until
/// the native audio dependencies clear their `@tooling-owner` gate.
#[derive(Debug)]
pub struct MockCapture {
    format: AudioFormat,
    samples_per_frame: usize,
    capacity: usize,
    running: bool,
    fail_with: Option<CaptureError>,
    pump: Option<tokio::task::JoinHandle<()>>,
}

impl MockCapture {
    pub fn new(format: AudioFormat, samples_per_frame: usize) -> Self {
        Self {
            format,
            samples_per_frame: samples_per_frame.max(1),
            capacity: FRAME_CHANNEL_CAPACITY,
            running: false,
            fail_with: None,
            pump: None,
        }
    }

    pub fn with_capacity(mut self, capacity: usize) -> Self {
        self.capacity = capacity.max(1);
        self
    }

    pub fn failing_with(mut self, error: CaptureError) -> Self {
        self.fail_with = Some(error);
        self
    }

    fn frame(&self, index: u64) -> PcmFrame {
        let start = index * self.samples_per_frame as u64;
        let samples = (0..self.samples_per_frame)
            .map(|offset| ((start + offset as u64) % 1_000) as i16)
            .collect();
        let frame = PcmFrame::new(0, self.format, samples);
        PcmFrame::new(index * frame.duration_ms(), self.format, frame.samples)
    }
}

impl AudioBackend for MockCapture {
    fn format(&self) -> AudioFormat {
        self.format
    }

    fn is_running(&self) -> bool {
        self.running
    }

    fn start(
        &mut self,
        kind: CaptureKind,
    ) -> crate::CaptureFuture<'_, Result<FrameStream, CaptureError>> {
        Box::pin(async move {
            if let Some(error) = self.fail_with.clone() {
                return Err(error);
            }
            if self.running {
                return Err(CaptureError::AlreadyRunning);
            }
            let _ = kind;

            let (stream, sink) = FrameStream::bounded(self.capacity);
            let frames: Vec<PcmFrame> = (0..self.capacity as u64).map(|i| self.frame(i)).collect();
            self.pump = Some(tokio::spawn(async move {
                pump(sink, frames).await;
            }));
            self.running = true;
            Ok(stream)
        })
    }

    fn stop(&mut self) -> crate::CaptureFuture<'_, Result<(), CaptureError>> {
        Box::pin(async move {
            if !self.running {
                return Err(CaptureError::NotRunning);
            }
            if let Some(pump) = self.pump.take() {
                pump.abort();
            }
            self.running = false;
            Ok(())
        })
    }
}

async fn pump(sink: FrameSink, frames: Vec<PcmFrame>) {
    for frame in frames {
        if !sink.offer(frame) {
            break;
        }
        tokio::task::yield_now().await;
    }
}

impl Drop for MockCapture {
    fn drop(&mut self) {
        if let Some(pump) = self.pump.take() {
            pump.abort();
        }
    }
}
