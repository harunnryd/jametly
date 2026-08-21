use std::path::{Path, PathBuf};
use std::time::SystemTime;

use image::{ImageBuffer, Rgba};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum CaptureError {
    #[error("invalid capture region")]
    InvalidRegion,
    #[error("invalid RGBA frame")]
    InvalidFrame,
    #[error("screen capture permission denied")]
    PermissionDenied,
    #[error("screen capture is unavailable")]
    Unavailable,
    #[error("unsafe blob path")]
    UnsafePath,
    #[error("screen capture I/O failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("PNG encoding failed: {0}")]
    Png(#[from] image::ImageError),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Monitor {
    pub id: String,
    pub width: u32,
    pub height: u32,
    pub primary: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rect {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

impl Rect {
    pub fn new(x: u32, y: u32, width: u32, height: u32) -> Result<Self, CaptureError> {
        if width == 0
            || height == 0
            || x.checked_add(width).is_none()
            || y.checked_add(height).is_none()
        {
            return Err(CaptureError::InvalidRegion);
        }
        Ok(Self {
            x,
            y,
            width,
            height,
        })
    }

    pub fn validate_within(self, monitor: &Monitor) -> Result<Self, CaptureError> {
        let right = self
            .x
            .checked_add(self.width)
            .ok_or(CaptureError::InvalidRegion)?;
        let bottom = self
            .y
            .checked_add(self.height)
            .ok_or(CaptureError::InvalidRegion)?;
        if right > monitor.width || bottom > monitor.height {
            return Err(CaptureError::InvalidRegion);
        }
        Ok(self)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RgbaFrame {
    width: u32,
    height: u32,
    pixels: Vec<u8>,
}

impl RgbaFrame {
    pub fn new(width: u32, height: u32, pixels: Vec<u8>) -> Result<Self, CaptureError> {
        let expected = usize::try_from(width)
            .ok()
            .and_then(|w| usize::try_from(height).ok().and_then(|h| w.checked_mul(h)))
            .and_then(|pixels| pixels.checked_mul(4));
        if expected != Some(pixels.len()) {
            return Err(CaptureError::InvalidFrame);
        }
        Ok(Self {
            width,
            height,
            pixels,
        })
    }

    pub fn solid(width: u32, height: u32, pixel: [u8; 4]) -> Result<Self, CaptureError> {
        let count = usize::try_from(width)
            .ok()
            .and_then(|w| usize::try_from(height).ok().and_then(|h| w.checked_mul(h)))
            .ok_or(CaptureError::InvalidFrame)?;
        let mut pixels = Vec::with_capacity(count * 4);
        for _ in 0..count {
            pixels.extend_from_slice(&pixel);
        }
        Self::new(width, height, pixels)
    }

    pub fn width(&self) -> u32 {
        self.width
    }
    pub fn height(&self) -> u32 {
        self.height
    }

    pub fn pixel(&self, x: u32, y: u32) -> [u8; 4] {
        let offset = ((y * self.width + x) * 4) as usize;
        self.pixels[offset..offset + 4]
            .try_into()
            .expect("validated pixel offset")
    }

    fn crop(&self, rect: Rect) -> Result<Self, CaptureError> {
        if rect.x.checked_add(rect.width).is_none()
            || rect.y.checked_add(rect.height).is_none()
            || rect.x + rect.width > self.width
            || rect.y + rect.height > self.height
        {
            return Err(CaptureError::InvalidRegion);
        }
        let mut pixels = Vec::with_capacity((rect.width * rect.height * 4) as usize);
        for y in rect.y..rect.y + rect.height {
            let start = ((y * self.width + rect.x) * 4) as usize;
            let end = start + (rect.width * 4) as usize;
            pixels.extend_from_slice(&self.pixels[start..end]);
        }
        Self::new(rect.width, rect.height, pixels)
    }
}

pub trait CaptureBackend {
    fn capture_primary(&self) -> Result<RgbaFrame, CaptureError>;
    fn capture_region(&self, rect: Rect) -> Result<RgbaFrame, CaptureError>;
}

#[derive(Debug, Clone)]
pub struct MockCapture {
    monitor: Monitor,
    failure: Option<MockFailure>,
}

#[derive(Debug, Clone, Copy)]
enum MockFailure {
    PermissionDenied,
    Unavailable,
}

impl MockCapture {
    pub fn new(monitor: Monitor) -> Self {
        Self {
            monitor,
            failure: None,
        }
    }
    pub fn permission_denied(monitor: Monitor) -> Self {
        Self {
            monitor,
            failure: Some(MockFailure::PermissionDenied),
        }
    }
    pub fn unavailable() -> Self {
        Self {
            monitor: Monitor {
                id: "none".into(),
                width: 0,
                height: 0,
                primary: false,
            },
            failure: Some(MockFailure::Unavailable),
        }
    }

    fn image(&self) -> Result<RgbaFrame, CaptureError> {
        if let Some(error) = self.failure {
            return Err(match error {
                MockFailure::PermissionDenied => CaptureError::PermissionDenied,
                MockFailure::Unavailable => CaptureError::Unavailable,
            });
        }
        let mut pixels =
            Vec::with_capacity((self.monitor.width * self.monitor.height * 4) as usize);
        for y in 0..self.monitor.height {
            for x in 0..self.monitor.width {
                pixels.extend_from_slice(&[(x % 256) as u8, (y % 256) as u8, 0, 255]);
            }
        }
        RgbaFrame::new(self.monitor.width, self.monitor.height, pixels)
    }
}

impl CaptureBackend for MockCapture {
    fn capture_primary(&self) -> Result<RgbaFrame, CaptureError> {
        self.image()
    }
    fn capture_region(&self, rect: Rect) -> Result<RgbaFrame, CaptureError> {
        rect.validate_within(&self.monitor)?;
        self.image()?.crop(rect)
    }
}

#[derive(Debug, Clone)]
pub struct BlobStore {
    root: PathBuf,
}

impl BlobStore {
    pub fn new(root: impl AsRef<Path>) -> Result<Self, CaptureError> {
        let root = root.as_ref().to_path_buf();
        std::fs::create_dir_all(&root)?;
        Ok(Self { root })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    pub fn write_png(&self, stem: &str, frame: &RgbaFrame) -> Result<PathBuf, CaptureError> {
        if stem.is_empty()
            || stem.contains('/')
            || stem.contains('\\')
            || stem == "."
            || stem == ".."
        {
            return Err(CaptureError::UnsafePath);
        }
        let path = self.root.join(format!("{stem}.png"));
        let image = ImageBuffer::<Rgba<u8>, Vec<u8>>::from_raw(
            frame.width,
            frame.height,
            frame.pixels.clone(),
        )
        .ok_or(CaptureError::InvalidFrame)?;
        image.save(&path)?;
        Ok(path)
    }

    pub fn cleanup_before(&self, cutoff: SystemTime) -> Result<usize, CaptureError> {
        let mut removed = 0;
        for entry in std::fs::read_dir(&self.root)? {
            let entry = entry?;
            let metadata = entry.metadata()?;
            if !metadata.is_file()
                || entry.path().extension().and_then(|ext| ext.to_str()) != Some("png")
            {
                continue;
            }
            if metadata
                .modified()
                .map(|modified| modified < cutoff)
                .unwrap_or(false)
            {
                std::fs::remove_file(entry.path())?;
                removed += 1;
            }
        }
        Ok(removed)
    }
}
